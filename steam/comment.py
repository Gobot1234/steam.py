"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Generic, TypeVar

from typing_extensions import Never

from .abc import Awardable

if TYPE_CHECKING:
    from .abc import Commentable
    from .message import Authors
    from .reaction import Award, AwardReaction
    from .state import ConnectionState


__all__ = ("Comment",)

OwnerT = TypeVar("OwnerT", bound="Commentable")


@dataclass(repr=False)
class Comment(Awardable, Generic[OwnerT]):
    """Represents a comment on a Steam profile.

    .. container:: operations

        .. describe:: x == y

            Checks if two comments are equal.

        .. describe:: hash(x)

            Returns the comment's hash.

    Attributes
    ----------
    id
        The comment's ID.
    content
        The comment's content.
    author
        The author of the comment.
    created_at
        The time the comment was posted at.
    owner
        The comment sections owner.
    reactions
        The comment's reactions.
    """

    _AWARDABLE_TYPE = 5
    __slots__ = ("_state", "content", "id", "created_at", "reactions", "author", "owner")

    _state: ConnectionState
    id: int
    content: str
    created_at: datetime
    reactions: list[AwardReaction]
    author: Authors
    owner: OwnerT

    def __repr__(self) -> str:
        attrs = ("id", "author")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Comment {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return self.id == other.id if isinstance(other, Comment) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

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
