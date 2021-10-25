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

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from .abc import Commentable
    from .message import Authors
    from .state import ConnectionState


__all__ = ("Comment",)

C = TypeVar("C", bound="Commentable")


@dataclass(repr=False)
class Comment(Generic[C]):
    """Represents a comment on a Steam profile.

    Attributes
    ----------
    id
        The comment's id.
    content
        The comment's content.
    author
        The author of the comment.
    created_at
        The time the comment was posted at.
    owner
        The comment sections owner.
    """

    __slots__ = ("content", "id", "created_at", "author", "owner", "_state")

    _state: ConnectionState
    id: int
    content: str
    created_at: datetime
    author: Authors
    owner: C

    def __repr__(self) -> str:
        attrs = ("id", "author")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Comment {' '.join(resolved)}>"

    async def report(self) -> None:
        """Reports the comment."""
        await self._state.report_comment(self.owner, self.id)

    async def delete(self) -> None:
        """Deletes the comment."""
        await self._state.delete_comment(self.owner, self.id)
