"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic

from ._const import impl_eq_via_id
from .abc import Awardable, Commentable, _CommentableKwargs
from .types.user import UserT

if TYPE_CHECKING:
    from .app import PartialApp
    from .state import ConnectionState
    from .types.id import PostID


@dataclass(repr=False, slots=True, eq=False)
@impl_eq_via_id
class Post(Awardable, Commentable, Generic[UserT]):
    """Represents a post on Steam Community."""

    _state: ConnectionState
    id: PostID
    """The ID of this post."""
    content: str
    """The content of this post."""
    author: UserT
    """The author of this post."""
    app: PartialApp | None
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
    def url(self) -> str:
        """The URL of this post."""
        return f"{self.author.community_url}/status/{self.id}"

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.author.id64,
            "forum_id": self.id,
        }
