"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic

from typing_extensions import Never, TypeVar

from ._const import ReadOnly, impl_eq_via_id
from .abc import Awardable, Commentable
from .types.user import AuthorT

if TYPE_CHECKING:
    from datetime import datetime

    from .reaction import Award, AwardReaction
    from .state import ConnectionState
    from .types.id import CommentID


__all__ = ("Comment",)

OwnerT = TypeVar("OwnerT", bound="Commentable", default="Commentable", covariant=True)


@dataclass(repr=False, slots=True)
@impl_eq_via_id
class Comment(Awardable["CommentID"], Generic[OwnerT, AuthorT]):
    """Represents a comment on a Steam profile.

    .. container:: operations

        .. describe:: x == y

            Checks if two comments are equal.

        .. describe:: hash(x)

            Returns the comment's hash.
    """

    _state: ConnectionState
    id: ReadOnly[CommentID]
    """The comment's ID."""
    content: str
    """The comment's content."""
    created_at: datetime
    """The time the comment was posted at."""
    reactions: list[AwardReaction]
    """The comment's reactions."""
    author: AuthorT
    """The author of the comment."""
    owner: OwnerT
    """The comment sections owner."""

    def __repr__(self) -> str:
        attrs = ("id", "author")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    async def report(self) -> None:
        """Reports the comment."""
        await self._state.report_comment(self.owner, self.id)

    async def delete(self) -> None:
        """Deletes the comment."""
        await self._state.delete_comment(self.owner, self.id)

    if TYPE_CHECKING:
        # @overload
        # async def award(self: Comment[Topic], award: Award) -> None: ...
        async def award(self, award: Award) -> Never:
            ...
