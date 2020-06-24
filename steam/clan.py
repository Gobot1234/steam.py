# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import re
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from bs4 import BeautifulSoup

from . import utils
from .abc import SteamID
from .channel import ClanChannel
from .comment import Comment
from .errors import HTTPException
from .iterators import CommentsIterator
from .models import URL, Role

if TYPE_CHECKING:
    from .user import User, BaseUser
    from .protobufs.steammessages_chat import CChatRoom_GetChatRoomGroupSummary_Response \
        as ClanProto
    from .state import ConnectionState


__all__ = (
    'Clan',
)


class Clan(SteamID):
    """Represents a Steam clan.

    .. container:: operations

        .. describe:: x == y

            Checks if two clans are equal.

        .. describe:: x != y

            Checks if two clans are not equal.

        .. describe:: str(x)

            Returns the clan's name.

        .. describe:: len(x)

            Returns the number of members in the clan.


    Attributes
    ------------
    name: :class:`str`
        The name of the clan.
    url: :class:`str`
        The url of the clan.
    icon_url: :class:`str`
        The icon url of the clan. Uses the large (184x184 px) image url.
    description: :class:`str`
        The description of the clan.
    count: :class:`int`
        The amount of users in the clan.
    online_count: :class:`int`
        The amount of users currently online.
    active_member_count: :class:`int`
        The amount of currently users in the clan's chat room.
    in_game_count: :class:`int`
        The amount of user's currently in game.
    """
    # TODO more docs

    __slots__ = ('url', '_state', 'name', 'description', 'icon_url', 'created_at',
                 'language', 'location', 'count', 'in_game_count', 'online_count',
                 'admins', 'mods', 'chat_id', 'active_member_count', 'owner',
                 'default_role', 'tagline', 'top_members', 'roles', 'channels', 'default_channel')

    # TODO more to implement https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/clans.js

    def __init__(self, state: 'ConnectionState', id: int):
        self.url = f'{URL.COMMUNITY}/gid/{id}'
        self._state = state

        # don't break for fetched clans
        self.chat_id = 0
        self.active_member_count = 0
        self.channels: List['ClanChannel'] = []
        self.top_members: List['BaseUser'] = []
        self.roles: List['Role'] = []
        self.owner: Optional['BaseUser'] = None
        self.tagline: Optional[str] = None
        self.default_role: Optional['Role'] = None
        self.default_channel: Optional['ClanChannel'] = None

    async def __ainit__(self) -> None:
        resp = await self._state.request('GET', self.url)
        search = re.search(r"OpenGroupChat\(\s*'(\d+)'\s*\)", resp)
        if search is None:
            return
        super().__init__(search.group(1))

        soup = BeautifulSoup(resp, 'html.parser')
        self.name = soup.find('title').text.replace('Steam Community :: Group :: ', '', 1)
        self.description = soup.find('meta', attrs={"property": 'og:description'})['content']
        self.icon_url = soup.find('link', attrs={"rel": 'image_src'})['href']
        stats = soup.find('div', attrs={"class": 'grouppage_resp_stats'})
        for stat in stats.find_all('div', attrs={"class": 'groupstat'}):
            if 'Founded' in stat.text:
                text = stat.text.split('Founded')[1].strip()
                if ', ' not in stat.text:
                    text = f'{text}, {datetime.utcnow().year}'
                self.created_at = datetime.strptime(text, '%d %B, %Y')
            if 'Language' in stat.text:
                self.language = stat.text.split('Language')[1].strip()
            if 'Location' in stat.text:
                self.location = stat.text.split('Location')[1].strip()

        for count in stats.find_all('div', attrs={"class": 'membercount'}):
            if 'MEMBERS' in count.text:
                self.count = int(count.text.split('MEMBERS')[0].strip().replace(',', ''))
            if 'IN-GAME' in count.text:
                self.in_game_count = int(count.text.split('IN-GAME')[0].strip().replace(',', ''))
            if 'ONLINE' in count.text:
                self.online_count = int(count.text.split('ONLINE')[0].strip().replace(',', ''))

        admins = []
        mods = []
        is_admins = True
        for fields in soup.find_all('div', attrs={"class": 'membergrid'}):
            for idx, field in enumerate(fields.find_all('div')):
                if 'Members' in field.text:
                    if mods:
                        mods.pop()
                    break
                if 'Moderators' in field.text:
                    officer = admins.pop()
                    mods.append(officer)
                    is_admins = False
                try:
                    account_id = fields.find_all('div', attrs={"class": 'playerAvatar'})[idx]['data-miniprofile']
                except IndexError:
                    break
                else:
                    if is_admins:
                        admins.append(account_id)
                    else:
                        mods.append(account_id)

        self.admins = await self._state.client.fetch_users(*admins)
        self.mods = await self._state.client.fetch_users(*mods)

    def __repr__(self):
        attrs = (
            'name', 'id', 'type', 'universe', 'instance'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f"<Clan {' '.join(resolved)}>"

    def __str__(self):
        return self.name

    def __len__(self):
        return self.count

    async def fetch_members(self) -> List['SteamID']:
        """|coro|
        Fetches a clan's member list.

        Returns
        --------
        List[:class:`~steam.SteamID`]
            A basic list of the clan's members.
            This can be a very slow operation due to
            the rate limits on this endpoint.
        """
        ret = []
        resp = await self._state.request('GET', f'{self.url}/members?p=1&content_only=true')
        soup = BeautifulSoup(resp, 'html.parser')
        pages = int(soup.find_all('a', attrs={"class": 'pagelink'}).pop().text)

        async def getter(i) -> None:
            try:
                resp = await self._state.request('GET', f'{self.url}/members?p={i + 1}')
            except HTTPException:
                await asyncio.sleep(20)
                await getter(i)
            else:
                soup = BeautifulSoup(resp, 'html.parser')
                for s in soup.find_all('div', attrs={"id": 'memberList'}):
                    for user in s.find_all('div', attrs={"class": 'member_block'}):
                        ret.append(SteamID(user['data-miniprofile']))

        for i in range(pages):
            await getter(i)

        return ret

    async def join(self) -> None:
        """|coro|
        Joins the :class:`Clan`.
        """
        await self._state.http.join_clan(self.id64)

    async def leave(self) -> None:
        """|coro|
        Leaves the :class:`Clan`.
        """
        await self._state.http.leave_clan(self.id64)

    async def invite(self, user: 'User'):
        """|coro|
        Invites a :class:`~steam.User` to the :class:`Clan`.

        Parameters
        -----------
        user: :class:`~steam.User`
            The user to invite to the clan.
        """
        await self._state.http.invite_user_to_clan(user_id64=user.id64, clan_id=self.id64)

    async def comment(self, content: str) -> Comment:
        """|coro|
        Post a comment to an :class:`Clan`'s comment section.

        Parameters
        -----------
        content: :class:`str`
            The message to add to the clan's profile.

        Returns
        -------
        :class:`~steam.Comment`
            The created comment.
        """
        resp = await self._state.http.post_comment(self.id64, 'Clan', content)
        id = int(re.findall(r'id="comment_(\d+)"', resp['comments_html'])[0])
        timestamp = datetime.utcfromtimestamp(resp['timelastpost'])
        comment = Comment(
            state=self._state, id=id, owner=self,
            timestamp=timestamp, content=content,
            author=self._state.client.user
        )
        self._state.dispatch('comment', comment)
        return comment

    def comments(self, limit=None, before: datetime = None, after: datetime = None) -> CommentsIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a
        :class:`~steam.Clan`'s :class:`~steam.Comment` objects.

        Examples
        -----------

        Usage: ::

            async for comment in clan.comments(limit=10):
                print('Author:', comment.author, 'Said:', comment.content)

        Flattening into a list: ::

            comments = await clan.comments(limit=50).flatten()
            # comments is now a list of Comment

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of comments to search through.
            Default is ``None`` which will fetch the clan's entire comments section.
        before: Optional[:class:`datetime.datetime`]
            A time to search for comments before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for comments after.

        Yields
        ---------
        :class:`~steam.Comment`
            The comment with the comment information parsed.
        """
        return CommentsIterator(state=self._state, owner=self, limit=limit, before=before, after=after)

    @classmethod
    async def _from_proto(cls, state: 'ConnectionState', proto: 'ClanProto'):
        clan = cls(state=state, id=proto.clanid)
        await clan.__ainit__()
        clan.owner = await state.fetch_user(utils.make_steam64(proto.accountid_owner))
        clan.tagline = proto.chat_group_tagline or None

        clan.chat_id = proto.chat_group_id
        clan.active_member_count = proto.active_member_count

        clan.top_members = await state.client.fetch_users(proto.top_members)
        clan.roles = []

        for role in proto.role_actions:
            clan.roles.append(Role(role))

        clan.default_role = [r for r in clan.roles if r.id == int(proto.default_role_id)][0]
        clan.default_channel = int(proto.default_chat_id)
        clan.channels = []
        for channel in proto.chat_rooms:
            clan.channels.append(ClanChannel(state=state, clan=clan, channel=channel))
        clan.default_channel = [c for c in clan.channels if c.id == int(proto.default_chat_id)][0]

        return clan
