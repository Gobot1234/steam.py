# -*- coding: utf-8 -*-

"""
MIT License

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
import re
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User
    from .group import Group


class URL:
    API = 'https://api.steampowered.com'
    COMMUNITY = 'https://steamcommunity.com'
    STORE = 'https://store.steampowered.com'


class Comment:
    """Represents a comment on a Steam profile.

    Attributes
    -----------
    id: :class:`int`
        The comment's id.
    content: :class:`str`
        The comment's content.
    author: :class:`~steam.User`
        The author of the comment.
    created_at: :class:`datetime.datetime`
        The time the comment was posted at.
    owner: :class:`~steam.User`
        The comment sections owner.
    """

    __slots__ = ('content', 'id', 'created_at', 'author', 'owner', '_state')

    def __init__(self, state, comment_id: int, content: str, timestamp: datetime, author: 'User', owner: 'User'):
        self._state = state
        self.content = content
        self.id = comment_id
        self.created_at = timestamp
        self.author: User = author
        self.owner: User = owner

    def __repr__(self):
        attrs = (
            'id', 'author'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Comment {' '.join(resolved)}>"

    async def report(self) -> None:
        """|coro|
        Reports the :class:`Comment`.
        """
        params = {
            "gidcomment": self.id,
            "hide": 1
        }
        await self._state.request('POST', f'{URL.COMMUNITY}/comment/Profile/hideandreport/{self.owner.id64}',
                                  params=params)

    async def delete(self) -> None:
        """|coro|
        Deletes the :class:`Comment`.
        """
        params = {
            "gidcomment": self.id,
        }
        await self._state.request('POST', f'{URL.COMMUNITY}/comment/Profile/delete/{self.owner.id64}', params=params)


class Invite:
    """Represents a invite from a Steam user.

    Attributes
    -----------
    type: :class:`str`
        The type of invite either 'Friend'
        or 'Group'.
    invitee: :class:`~steam.User`
        The user who sent the invite. For type
        'Friend', this is the user you would end up adding.
    group: Optional[:class:`~steam.Group`]
        The group the invite proteins to,
        only relevant if type is 'Group'.
    """

    def __init__(self, state, data):
        self._state = state
        self._search = re.search(r"href=\"javascript:OpenGroupChat\( '(\d+)' \)\"", str(data))
        self.type = 'Group' if self._search is not None else 'Friend'
        self.invitee = re.search(r'data-miniprofile="(\d+)"', str(data)).group(1)

    async def __ainit__(self):
        client = self._state.client
        self.invitee: User = await client.fetch_user(self.invitee)
        self.group: Group = await client.fetch_group(self._search.group(1)) if self.type == 'Group' else None

    def __repr__(self):
        attrs = (
            'type', 'invitee', 'group'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Invite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """|coro|
        Accepts the invite request.
        """
        if self.type is 'Friend':
            await self._state.http.accept_user_invite(self.invitee.id64)
        else:
            await self._state.http.accept_group_invite(self.group.id)

    async def decline(self) -> None:
        """|coro|
        Declines the invite request.
        """
        if self.type is 'Friend':
            await self._state.http.decline_user_invite(self.invitee.id64)
        else:
            await self._state.http.decline_group_invite(self.group.id)