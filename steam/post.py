"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic

from .abc import Awardable, Commentable, _CommentableKwargs
from .types.user import UserT
from .utils import DateTime

if TYPE_CHECKING:
    from datetime import datetime

    from ._const import ReadOnly
    from .app import PartialApp
    from .state import ConnectionState
    from .types.id import PostID


@dataclass(repr=False, slots=True, unsafe_hash=True)
class Post(Awardable["PostID"], Commentable, Generic[UserT]):
    """Represents a post on Steam Community."""

    _state: ConnectionState = field(compare=False, hash=False)
    id: ReadOnly[PostID]
    """The ID of this post."""
    content: str = field(compare=False, hash=False)
    """The content of this post."""
    author: UserT
    """The author of this post."""
    app: PartialApp | None = field(compare=False, hash=False)
    """The app this post is for, if any."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} author={self.author!r} app={self.app!r}>"

    async def delete(self) -> None:
        """Delete this post."""
        await self._state.delete_user_post(self.id)

    async def upvote(self) -> None:
        """Upvote this post."""
        await self._state.http.vote_on_user_post(self.author.id64, self.id, 1)

    async def downvote(self) -> None:
        """Un-upvote this post (this is different from other downvoting systems)."""
        await self._state.http.vote_on_user_post(self.author.id64, self.id, 0)

    @property
    def created_at(self) -> datetime:
        """The time this post was created."""
        return DateTime.from_timestamp(self.id)  # yes, really

    @property
    def url(self) -> str:
        """The URL of this post."""
        return f"{self.author.community_url}/status/{self.id}"

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.author.id64,
            "forum_id": self.id,
        }
