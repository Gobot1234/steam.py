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

from datetime import datetime
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .abc import BaseUser
    from .clan import Clan
    from .state import ConnectionState


__all__ = ("Comment",)


class Comment:
    """Represents a comment on a Steam profile.

    Attributes
    ----------
    id: :class:`int`
        The comment's id.
    content: :class:`str`
        The comment's content.
    author: :class:`~steam.User`
        The author of the comment.
    created_at: :class:`datetime.datetime`
        The time the comment was posted at.
    owner: Union[:class:`~steam.Clan`, :class:`~steam.User`]
        The comment sections owner. If the comment section is for a clan
        it will be a :class:`~steam.Clan` instance otherwise it
        will be an :class:`~steam.User` instance.
    """

    __slots__ = ("content", "id", "created_at", "author", "owner", "_state")

    def __init__(
        self,
        state: "ConnectionState",
        id: int,
        content: str,
        timestamp: datetime,
        author: "BaseUser",
        owner: Union["Clan", "BaseUser"],
    ):
        self._state = state
        self.content = content
        self.id = id
        self.created_at = timestamp
        self.author = author
        self.owner = owner

    def __repr__(self):
        attrs = ("id", "author")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Comment {' '.join(resolved)}>"

    async def report(self) -> None:
        """|coro|
        Reports the :class:`Comment`.
        """
        from .abc import BaseUser

        await self._state.http.report_comment(
            id64=self.owner.id64,
            comment_id=self.id,
            comment_type="Profile" if isinstance(self.owner, BaseUser) else "Clan",
        )

    async def delete(self) -> None:
        """|coro|
        Deletes the :class:`Comment`.
        """
        from .abc import BaseUser

        await self._state.http.delete_comment(
            id64=self.owner.id64,
            comment_id=self.id,
            comment_type="Profile" if isinstance(self.owner, BaseUser) else "Clan",
        )
