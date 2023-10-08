"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from ._const import ReadOnly, impl_eq_via_id
from .abc import Awardable, Commentable, _CommentableKwargs
from .app import PartialApp
from .enums import Language, ReviewType
from .reaction import AwardReaction
from .user import ClientUser, User, WrapsUser
from .utils import DateTime

if TYPE_CHECKING:
    from typing_extensions import Self

    from .protobufs.reviews import RecommendationDetails as ReviewProto
    from .state import ConnectionState

__all__ = (
    "Review",
    "ReviewUser",
)


class ReviewUser(WrapsUser):
    __slots__ = (
        "number_of_apps_owned",
        "number_of_reviews",
        "playtime_forever",
        "playtime_last_two_weeks",
        "playtime_at_review",
        "last_played",
    )

    number_of_apps_owned: int | None
    number_of_reviews: int | None
    playtime_forever: timedelta
    playtime_last_two_weeks: timedelta
    playtime_at_review: timedelta
    last_played: datetime

    @classmethod
    def _from_proto(cls, state: ConnectionState, user: User | ClientUser, review: ReviewProto) -> Self:
        review_user = cls(state, user)
        review_user.number_of_reviews = None
        review_user.number_of_apps_owned = None
        review_user.playtime_forever = timedelta(seconds=review.playtime_forever)
        review_user.playtime_last_two_weeks = timedelta(seconds=review.playtime_2weeks)
        review_user.playtime_at_review = timedelta(seconds=review.playtime_at_review)
        review_user.last_played = DateTime.from_timestamp(review.last_playtime)
        return review_user

    @classmethod
    def _from_data(cls, state: ConnectionState, user: User | ClientUser, data: dict[str, Any]) -> Self:
        review_user = cls(state, user)
        review_user.number_of_reviews = data["num_reviews"]
        review_user.number_of_apps_owned = data["num_games_owned"]
        review_user.playtime_forever = timedelta(seconds=data["playtime_forever"])
        review_user.playtime_last_two_weeks = timedelta(seconds=data["playtime_last_two_weeks"])
        review_user.playtime_at_review = timedelta(seconds=data["playtime_at_review"])
        review_user.last_played = DateTime.from_timestamp(data["last_played"])
        return review_user


class ReviewApp(PartialApp):
    __slots__ = ("review_status",)

    def __init__(self, state: ConnectionState, id: int, review_status: int):
        super().__init__(state, id=id)
        self.review_status = ReviewType.try_value(review_status)


@dataclass(repr=False, eq=False)
@impl_eq_via_id
class Review(Commentable, Awardable):
    """Represents a review for an app."""

    __slots__ = (
        "_state",
        "id",
        "author",
        "app",
        "language",
        "content",
        "created_at",
        "updated_at",
        "recommended",
        "votes_helpful",
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
    id: ReadOnly[int]
    """The ID of the review."""
    author: ReviewUser
    """The author of the review."""
    app: ReviewApp
    """The app being reviewed."""
    recommended: bool
    """Whether the reviewer recommends the app."""
    language: Language
    """The language the review is written in."""
    content: str
    """The contents of the review."""
    created_at: datetime
    """The time the review was created at."""
    updated_at: datetime
    """The time the review was last updated at."""
    votes_helpful: int
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
    """Whether the app was purchased through Steam."""
    received_compensation: bool
    """Whether the reviewer received compensation for this review."""
    written_during_early_access: bool
    """Whether the reviewer played the app the app during early access."""
    developer_response: str | None
    """The developer's response to the review."""
    developer_responded_at: datetime | None
    """The time the developer responded to the review."""
    reactions: list[AwardReaction] | None
    """The review's reactions."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} app={self.app!r} author={self.author!r}>"

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.author.id64,
            "forum_id": self.app.id,
        }

    @classmethod
    def _from_proto(cls, state: ConnectionState, review: ReviewProto, user: User | ClientUser) -> Self:
        return cls(
            state,
            id=review.recommendationid,
            author=ReviewUser._from_proto(state, user, review),
            app=ReviewApp(state, review.appid, review.review_quality),
            language=Language.from_str(review.language),
            content=review.review,
            created_at=DateTime.from_timestamp(review.time_created),
            updated_at=DateTime.from_timestamp(review.time_updated),
            recommended=review.voted_up,
            votes_funny=review.votes_funny,
            votes_helpful=review.votes_up,
            weighted_vote_score=review.weighted_vote_score,
            commentable=not review.comments_disabled,
            comment_count=review.comment_count,
            steam_purchase=not review.unverified_purchase,
            received_compensation=review.received_compensation,
            written_during_early_access=review.written_during_early_access,
            developer_response=review.developer_response or None,
            developer_responded_at=(
                DateTime.from_timestamp(review.time_developer_responded)
                if review.time_developer_responded
                else None  # TODO add the rest of the developer attrs
            ),
            reactions=[AwardReaction(state, reaction) for reaction in review.reactions],
        )

    @classmethod
    def _from_data(cls, state: ConnectionState, data: dict[str, Any], app: ReviewApp, user: User) -> Self:
        return cls(
            state,
            id=data["recommendationid"],
            author=ReviewUser._from_data(state, user, data["author"]),
            app=app,
            language=Language.from_str(data["language"]),
            content=data["review"],
            created_at=DateTime.from_timestamp(data["timestamp_created"]),
            updated_at=DateTime.from_timestamp(data["timestamp_updated"]),
            recommended=data["voted_up"],
            votes_funny=data["votes_funny"],
            votes_helpful=data["votes_up"],
            weighted_vote_score=data["weighted_vote_score"],
            commentable=None,
            comment_count=data["comment_count"],
            steam_purchase=data["steam_purchase"],
            received_compensation=data["received_for_free"],
            written_during_early_access=data["written_during_early_access"],
            developer_response=data.get("developer_response"),
            developer_responded_at=(
                DateTime.from_timestamp(data["timestamp_dev_responded"]) if "timestamp_dev_responded" in data else None
            ),
            reactions=None,
        )

    async def mark_helpful(self) -> None:
        """Mark this review as helpful."""
        await self._state.http.mark_review_as_helpful(self.id, True)

    async def mark_not_helpful(self) -> None:
        """Mark this review as not helpful."""
        await self._state.http.mark_review_as_helpful(self.id, False)

    async def mark_funny(self) -> None:
        """Mark this review as funny."""
        await self._state.http.mark_review_as_funny(self.id)

    async def edit(
        self,
        content: str,
        /,
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
            review = await self.author.fetch_review(self.app)
            commentable = review.commentable
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
        await self._state.http.delete_review(self.app.id)
