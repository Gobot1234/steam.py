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
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from typing_extensions import Self

from . import utils
from .abc import Awardable, BaseUser, Commentable, _CommentableKwargs
from .enums import Language
from .game import StatefulGame
from .reaction import AwardReaction
from .user import ClientUser, User

if TYPE_CHECKING:
    from .protobufs.reviews import RecommendationDetails as ReviewProto
    from .state import ConnectionState

__all__ = (
    "Review",
    "ReviewUser",
    "ClientReviewUser",
)


class BaseReviewUser(BaseUser):
    __slots__ = (
        "number_of_games_owned",
        "number_of_reviews",
        "playtime_forever",
        "playtime_last_two_weeks",
        "playtime_at_review",
        "last_played",
    )

    number_of_games_owned: int | None
    number_of_reviews: int | None
    playtime_forever: timedelta
    playtime_last_two_weeks: timedelta
    playtime_at_review: timedelta
    last_played: datetime

    @staticmethod
    def _make(user: BaseUser) -> BaseReviewUser:
        cls = ReviewUser if isinstance(user, User) else ClientReviewUser
        return utils.update_class(user, cls.__new__(cls))  # type: ignore

    @classmethod
    def _from_proto(cls, user: BaseUser, review: ReviewProto) -> BaseReviewUser:
        review_user = cls._make(user)
        review_user.number_of_reviews = None
        review_user.number_of_games_owned = None
        review_user.playtime_forever = timedelta(seconds=review.playtime_forever)
        review_user.playtime_last_two_weeks = timedelta(seconds=review.playtime_2weeks)
        review_user.playtime_at_review = timedelta(seconds=review.playtime_at_review)
        review_user.last_played = datetime.utcfromtimestamp(review.last_playtime)
        return review_user

    @classmethod
    def _from_data(cls, user: BaseUser, data: dict[str, Any]) -> BaseReviewUser:
        review_user = cls._make(user)
        review_user.number_of_reviews = data["num_games_owned"]
        review_user.number_of_games_owned = data["num_reviews"]
        review_user.playtime_forever = timedelta(seconds=data["playtime_forever"])
        review_user.playtime_last_two_weeks = timedelta(seconds=data["playtime_last_two_weeks"])
        review_user.playtime_at_review = timedelta(seconds=data["playtime_at_review"])
        review_user.last_played = datetime.utcfromtimestamp(data["last_played"])
        return review_user


if TYPE_CHECKING:

    class ReviewUser(BaseReviewUser, User):
        __slots__ = ()

    class ClientReviewUser(BaseReviewUser, ClientUser):
        __slots__ = ()

else:

    @BaseReviewUser.register
    class ReviewUser(User):
        __slots__ = BaseReviewUser.__slots__

    @BaseReviewUser.register
    class ClientReviewUser(ClientUser):
        __slots__ = BaseReviewUser.__slots__


@dataclass(repr=False, eq=False)
class Review(Commentable, Awardable):
    """Represents a review for a game."""

    _AWARDABLE_TYPE = 1
    __slots__ = (
        "_state",
        "id",
        "author",
        "game",
        "language",
        "content",
        "created_at",
        "updated_at",
        "upvoted",
        "upvotes",
        "votes_funny",
        "weighted_vote_score",
        "commentable",
        "comment_count",
        "steam_purchase",
        "received_compensation",
        "written_during_early_access",
        "developer_response",
        "developer_responded_at",
        "reactions",
    )

    _state: ConnectionState
    id: int
    """The ID of the review."""
    author: BaseReviewUser  # ideally UserT & BaseReviewUser
    """The author of the review."""
    game: StatefulGame
    """The game being reviewed."""
    language: Language
    """The language the review is written in."""
    content: str
    """The contents of the review."""
    created_at: datetime
    """The time the review was created at."""
    updated_at: datetime
    """The time the review was last updated at."""
    upvoted: bool
    """Whether the :class:`.ClientUser` upvoted this review."""
    upvotes: int
    """The amount of people that marked the review as helpful."""
    votes_funny: int
    """The amount of people that marked this review as funny."""
    weighted_vote_score: float
    """The weighted score from Steam."""
    commentable: bool | None
    """Whether the author has allowed comments on the review."""
    comment_count: int
    """The amount of comments this review has."""
    steam_purchase: bool | None
    """Whether the game was purchased through Steam."""
    received_compensation: bool
    """Whether the reviewer received compensation for this review."""
    written_during_early_access: bool
    """Whether the reviewer played the game the game during """
    developer_response: str | None
    """The developer's response to the review."""
    developer_responded_at: datetime | None
    """The time the developer responded to the review."""
    reactions: list[AwardReaction] | None
    """The review's reactions."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} game={self.game!r} author={self.author!r}>"

    def __eq__(self, other: object) -> bool:
        return self.id == other.id if isinstance(other, self.__class__) else NotImplemented

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "thread_type": 8,
            "id64": self.author.id64,
            "gidfeature": self.game.id,
        }

    @classmethod
    def _from_proto(cls, state: ConnectionState, review: ReviewProto, user: BaseUser) -> Self:
        return cls(
            state,
            id=review.recommendationid,
            author=BaseReviewUser._from_proto(user, review),
            game=StatefulGame(state, id=review.appid),
            language=Language.from_str(review.language),
            content=review.review,
            created_at=datetime.utcfromtimestamp(review.time_created),
            updated_at=datetime.utcfromtimestamp(review.time_updated),
            upvoted=review.voted_up,
            votes_funny=review.votes_funny,
            upvotes=review.votes_up,
            weighted_vote_score=review.weighted_vote_score,
            commentable=not review.comments_disabled,
            comment_count=review.comment_count,
            steam_purchase=not review.unverified_purchase,
            received_compensation=review.received_compensation,
            written_during_early_access=review.written_during_early_access,
            developer_response=review.developer_response or None,
            developer_responded_at=(
                datetime.utcfromtimestamp(review.time_developer_responded)
                if review.time_developer_responded
                else None  # TODO add the rest of the developer attrs
            ),
            reactions=[AwardReaction(state, reaction) for reaction in review.reactions],
        )

    @classmethod
    def _from_data(cls, state: ConnectionState, data: dict[str, Any], game: StatefulGame, user: BaseUser) -> Self:
        return cls(
            state,
            id=data["recommendationid"],
            author=BaseReviewUser._from_data(user, data["author"]),
            game=game,
            language=Language.from_str(data["language"]),
            content=data["review"],
            created_at=datetime.utcfromtimestamp(data["timestamp_created"]),
            updated_at=datetime.utcfromtimestamp(data["timestamp_updated"]),
            upvoted=data["voted_up"],
            votes_funny=data["votes_funny"],
            upvotes=data["votes_up"],
            weighted_vote_score=data["weighted_vote_score"],
            commentable=None,
            comment_count=data["comment_count"],
            steam_purchase=data["steam_purchase"],
            received_compensation=data["received_for_free"],
            written_during_early_access=data["written_during_early_access"],
            developer_response=data.get("developer_response"),
            developer_responded_at=(
                datetime.utcfromtimestamp(data["timestamp_dev_responded"])
                if "timestamp_dev_responded" in data
                else None
            ),
            reactions=None,
        )

    async def upvote(self) -> None:
        """Mark this review as helpful."""
        await self._state.http.mark_review_as_helpful(self.id, True)

    async def downvote(self) -> None:
        """Mark this review as not helpful."""
        await self._state.http.mark_review_as_helpful(self.id, False)

    async def mark_funny(self) -> None:
        """Mark this review as funny."""
        await self._state.http.mark_review_as_funny(self.id)

    async def edit(
        self,
        content: str,
        *,
        public: bool = True,
        commentable: bool | None = None,
        language: Language | None = None,
        written_during_early_access: bool | None = None,
        received_compensation: bool | None = None,
    ) -> None:
        """Edit this review.

        Parameters
        ----------
        content
            The content of the review.
        public
            Whether the review should be shown publicly on your profile.
        commentable
            Whether the review should be commentable.
        language
            The language of the review. Defaults to the current value.
        written_during_early_access
            Whether the review was written during early access. Defaults to the current value.
        received_compensation
            Whether the user received compensation for this review. Defaults to the current value.
        """
        if self.commentable is None and commentable is None:
            raise ValueError(
                "Pass an argument for commentable or use fetch_review to determine its current comment-ability."
            )
        await self._state.edit_review(
            self.id,
            content,
            public,
            self.commentable if commentable is None else commentable,  # type: ignore
            (self.language if language is None else language).api_name,  # TODO check
            self.written_during_early_access if written_during_early_access is None else written_during_early_access,
            self.received_compensation if received_compensation is None else received_compensation,
        )

    async def delete(self) -> None:
        """Delete this review."""
        await self._state.http.delete_review(self.id)
