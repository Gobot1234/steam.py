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

from __future__ import annotations

import asyncio
import inspect
import re
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Union

from bs4 import BeautifulSoup

from . import utils
from .abc import Commentable, SteamID
from .channel import ClanChannel
from .errors import HTTPException
from .game import Game
from .protobufs.steammessages_chat import (
    CChatRoomSummaryPair as ReceivedResponse,
    CClanChatRoomsGetClanChatRoomInfoResponse as FetchedResponse,
)
from .role import Role

if TYPE_CHECKING:
    from .state import ConnectionState
    from .user import User

__all__ = ("Clan",)


class Clan(Commentable, comment_path="Clan"):
    """Represents a Steam clan.

    .. container:: operations

        .. describe:: x == y

            Checks if two clans are equal.

        .. describe:: str(x)

            Returns the clan's name.

    Attributes
    ------------
    name: :class:`str`
        The name of the clan.
    chat_id: Optional[:class:`int`]
        The clan's chat_id.
    icon_url: :class:`str`
        The icon url of the clan. Uses the large (184x184 px) image url.
    description: :class:`str`
        The description of the clan.
    tagline: Optional[:class:`str`]
        The clan's tagline.
    member_count: :class:`int`
        The amount of users in the clan.
    online_count: :class:`int`
        The amount of users currently online.
    active_member_count: :class:`int`
        The amount of currently users in the clan's chat room.
    in_game_count: :class:`int`
        The amount of user's currently in game.
    created_at: :class:`datetime.datetime`
        The time the clan was created_at.
    language: :class:`str`
        The language set for the clan.
    location: :class:`str`
        The location set for the clan.
    game: :class:`.Game`
        The clan's associated game.
    owner: :class:`~steam.User`
        The clan's owner.
    admins: list[:class:`~steam.User`]
        A list of the clan's administrators.
    mods: list[:class:`~steam.User`]
        A list of the clan's moderators.
    top_members: list[:class:`~steam.User`]
        A list of the clan's top_members.
    roles: list[:class:`.Role`]
        A list of the clan's roles.
    default_role: :class:`.Role`
        The clan's default_role.
    channels: list[:class:`.ClanChannel`]
        A list of the clan's channels.
    default_channel: :class:`.ClanChannel`
        The clan's default_channel.
    """

    __slots__ = (
        "name",
        "description",
        "icon_url",
        "created_at",
        "language",
        "location",
        "member_count",
        "in_game_count",
        "online_count",
        "admins",
        "mods",
        "chat_id",
        "active_member_count",
        "owner",
        "default_role",
        "tagline",
        "top_members",
        "roles",
        "channels",
        "default_channel",
        "game",
    )

    # TODO more to implement https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/groups.js

    def __init__(self, state: ConnectionState, id: int):
        super().__init__(id, type="Clan")
        self._state = state
        self.name: Optional[str] = None
        self.chat_id: Optional[int] = None
        self.tagline: Optional[str] = None
        self.game: Optional[Game] = None
        self.owner: Optional[User] = None
        self.active_member_count: Optional[int] = None
        self.top_members: list[User] = []
        self.roles: list[Role] = []
        self.default_role: Optional[Role] = None
        self.channels: list[ClanChannel] = []
        self.default_channel: Optional[ClanChannel] = None

    async def __ainit__(self) -> None:
        resp = await self._state.http.get(self.community_url)
        if not self.id:
            search = re.search(r"OpenGroupChat\(\s*'(\d+)'\s*\)", resp)
            if search is None:
                return
            super().__init__(search.group(1), type="Clan")

        soup = BeautifulSoup(resp, "html.parser")
        self.name = soup.find("title").text[28:]
        self.description = soup.find("meta", attrs={"property": "og:description"})["content"]
        self.icon_url = soup.find("link", attrs={"rel": "image_src"})["href"]
        stats = soup.find("div", attrs={"class": "grouppage_resp_stats"})
        for stat in stats.find_all("div", attrs={"class": "groupstat"}):
            if "Founded" in stat.text:
                text = stat.text.split("Founded")[1].strip()
                if ", " not in stat.text:
                    text = f"{text}, {datetime.utcnow().year}"
                try:
                    self.created_at = datetime.strptime(text, "%d %B, %Y" if text.split()[0].isdigit() else "%B %d, %Y")
                except ValueError:  # why do other countries have to exist
                    self.created_at = None
            if "Language" in stat.text:
                self.language = stat.text.split("Language")[1].strip()
            if "Location" in stat.text:
                self.location = stat.text.split("Location")[1].strip()

        for count in stats.find_all("div", attrs={"class": "membercount"}):
            if "MEMBERS" in count.text:
                self.member_count = int(count.text.split("MEMBERS")[0].strip().replace(",", ""))
            if "IN-GAME" in count.text:
                self.in_game_count = int(count.text.split("IN-GAME")[0].strip().replace(",", ""))
            if "ONLINE" in count.text:
                self.online_count = int(count.text.split("ONLINE")[0].strip().replace(",", ""))

        admins = []
        mods = []
        is_admins = True
        for fields in soup.find_all("div", attrs={"class": "membergrid"}):
            for idx, field in enumerate(fields.find_all("div")):
                if "Members" in field.text:
                    if mods:
                        mods.pop()
                    break
                if "Moderators" in field.text:
                    officer = admins.pop()
                    mods.append(officer)
                    is_admins = False
                try:
                    account_id = fields.find_all("div", attrs={"class": "playerAvatar"})[idx]["data-miniprofile"]
                except IndexError:
                    break
                else:
                    if is_admins:
                        admins.append(account_id)
                    else:
                        mods.append(account_id)

        self.admins = await self._state.client.fetch_users(*admins)
        self.mods = await self._state.client.fetch_users(*mods)

    @classmethod
    async def _from_proto(cls, state: ConnectionState, clan_proto: Union[ReceivedResponse, FetchedResponse]) -> Clan:
        if isinstance(clan_proto, ReceivedResponse):
            id = clan_proto.group_summary.clanid
        else:
            id = clan_proto.chat_group_summary.clanid
        self = cls(state, id)
        await self.__ainit__()
        if isinstance(clan_proto, ReceivedResponse):
            proto = clan_proto.group_summary
        else:
            proto = clan_proto.chat_group_summary

        self.chat_id = proto.chat_group_id
        self.tagline = proto.chat_group_tagline or None
        self.active_member_count = proto.active_member_count
        self.game = Game(id=proto.appid) if proto.appid else None

        self.owner = await self._state.fetch_user(utils.make_id64(proto.accountid_owner))
        self.top_members = await self._state.fetch_users([utils.make_id64(u) for u in proto.top_members])

        self.roles = [Role(self._state, self, role) for role in proto.role_actions]
        self.default_role = utils.find(lambda r: r.id == int(proto.default_role_id), self.roles)

        self.channels = []
        self.default_channel = None
        if isinstance(clan_proto, ReceivedResponse):
            channels = clan_proto.user_chat_group_state.user_chat_room_state
        else:
            return self
        for channel in channels:
            channel = ClanChannel(state=self._state, clan=self, channel=channel)
            if channel not in self.channels:
                self.channels.append(channel)
            else:  # update the old instance
                idx = self.channels.index(channel)
                old_channel = self.channels[idx]
                for name, attr in inspect.getmembers(channel):
                    if attr:
                        setattr(old_channel, name, attr)

        self.default_channel = utils.find(lambda c: c.id == int(proto.default_chat_id), self.channels)
        return self

    def __repr__(self) -> str:
        attrs = ("name", "id", "chat_id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Clan {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    async def fetch_members(self) -> list[SteamID]:
        """|coro|
        Fetches a clan's member list.

        Returns
        --------
        list[:class:`~steam.SteamID`]
            A basic list of the clan's members. This can be a very slow operation due to the rate limits on this
            endpoint.
        """
        ret = []
        resp = await self._state.http.get(f"{self.community_url}/members?p=1&content_only=true")
        soup = BeautifulSoup(resp, "html.parser")
        number_of_pages = int(re.findall(r"\d* - (\d*)", soup.find("div", attrs={"class": "group_paging"}).text)[0])

        async def getter(i: int) -> None:
            try:
                resp = await self._state.http.get(f"{self.community_url}/members?p={i + 1}")
            except HTTPException:
                await asyncio.sleep(20)
                await getter(i)
            else:
                soup = BeautifulSoup(resp, "html.parser")
                for s in soup.find_all("div", attrs={"id": "memberList"}):
                    for user in s.find_all("div", attrs={"class": "member_block"}):
                        ret.append(SteamID(user["data-miniprofile"]))

        await asyncio.gather(*(getter(i) for i in range(number_of_pages)))
        return ret

    async def join(self) -> None:
        """|coro|
        Joins the :class:`Clan`. This will also join the clan's chat.
        """
        await self._state.http.join_clan(self.id64)
        await self._state.join_chat(self.chat_id)

    async def leave(self) -> None:
        """|coro|
        Leaves the :class:`Clan`.
        """
        await self._state.http.leave_clan(self.id64)

    async def invite(self, user: User) -> None:
        """|coro|
        Invites a :class:`~steam.User` to the :class:`Clan`.

        Parameters
        -----------
        user: :class:`~steam.User`
            The user to invite to the clan.
        """
        await self._state.http.invite_user_to_clan(user_id64=user.id64, clan_id=self.id64)
