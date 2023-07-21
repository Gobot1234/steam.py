"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, cast, overload

from typing_extensions import TypeVar

from . import utils
from ._const import URL
from .enums import LeaderboardDataRequest, LeaderboardDisplayType, LeaderboardSortMethod, LeaderboardUploadScoreMethod
from .user import User, WrapsUser

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from .app import App
    from .state import ConnectionState
    from .types.id import ID64, LeaderboardID
    from .types.user import IndividualID


__all__ = (
    "LeaderboardScoreUpdate",
    "LeaderboardUser",
    "Leaderboard",
)


@dataclass(slots=True)
class LeaderboardScoreUpdate:
    """Represents a score update on a leaderboard."""

    global_rank_before: int
    """The global rank of the user before the score update."""
    global_rank_after: int
    """The global rank of the user after the score update."""
    score_changed: bool
    """Whether the score changed."""


class LeaderboardUser(WrapsUser):
    """Represents a user on an app's leaderboard."""

    __slots__ = ("global_rank", "score", "details", "ugc_id")

    def __init__(
        self,
        state: ConnectionState,
        user: User,
        global_rank: int,
        score: int,
        details: bytes,
        ugc_id: int,
    ):
        super().__init__(state, user)
        self.global_rank = global_rank
        """The global rank of the user."""
        self.score = score
        """The score of the user."""
        self.details = details
        """The details of the user."""
        self.ugc_id = ugc_id
        """The UGC ID of the user."""


AppT = TypeVar("AppT", bound="App", covariant=True)
DisplayNameT = TypeVar("DisplayNameT", bound=str | None, default=None, covariant=True)


@dataclass(slots=True)
class Leaderboard(Generic[AppT, DisplayNameT]):
    """Represents a leaderboard for an app."""

    _state: ConnectionState
    id: LeaderboardID
    """The leaderboard's id."""
    name: str
    """The name of the leaderboard."""
    app: AppT
    """The app this leaderboard is for."""
    sort_method: LeaderboardSortMethod
    """The sort method of the leaderboard."""
    display_type: LeaderboardDisplayType
    """The display type of the leaderboard."""
    entry_count: int
    """The number of entries in the leaderboard."""
    display_name: DisplayNameT = cast(DisplayNameT, None)
    """The display name of the leaderboard. This is only set if the leaderboard is fetched using :meth:`PartialApp.leaderboards`."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id} display_name={self.display_name!r} app={self.app!r}>"

    @property
    def url(self) -> str:
        """The URL of the leaderboard."""
        return f"{URL.COMMUNITY}/stats/{self.app.id}/leaderboards/{self.id}"

    @overload
    async def entries(
        self,
        *,
        limit: int | None = None,
        type: Literal[LeaderboardDataRequest.Users],
        users: Sequence[IndividualID],
    ) -> AsyncGenerator[LeaderboardUser, None]:
        ...

    @overload
    async def entries(
        self, *, limit: int | None = None, type: LeaderboardDataRequest = LeaderboardDataRequest.Global
    ) -> AsyncGenerator[LeaderboardUser, None]:
        ...

    async def entries(
        self,
        *,
        limit: int | None = None,
        type: LeaderboardDataRequest = LeaderboardDataRequest.Global,
        users: Sequence[IndividualID] = (),
    ) -> AsyncGenerator[LeaderboardUser, None]:
        """Fetch the entries of the leaderboard.

        Parameters
        ----------
        limit
            The maximum number of entries to fetch. If `None` is passed, all entries will be fetched.
        type
            The type of entries to fetch.
        users
            The users to fetch. Only used if `type` is :attr:`LeaderboardDataRequest.Users`.
        """
        id64s = [user.id64 for user in users]
        for start, stop in utils._int_chunks(min(self.entry_count, limit or self.entry_count), 100):
            entries = await self._state.fetch_app_leaderboard_entries(self.app.id, self.id, start, stop, type, id64s)
            for entry, user in zip(
                entries,
                await self._state._maybe_users(cast("list[ID64]", [entry.steam_id_user for entry in entries])),
            ):
                yield LeaderboardUser(
                    self._state,
                    user,
                    entry.global_rank,
                    entry.score,
                    entry.details,
                    entry.ugc_id,
                )

    async def set_score(
        self, score: int, *, details: bytes, method: LeaderboardUploadScoreMethod = LeaderboardUploadScoreMethod.NONE
    ) -> LeaderboardScoreUpdate:
        """Set the score of the current user on the leaderboard.

        Parameters
        ----------
        score
            The score to set.
        details
            The details to set.
        method
            The method to use to upload the score.
        """
        update = await self._state.set_app_leaderboard_score(self.app.id, self.id, score, details, method)
        return LeaderboardScoreUpdate(update.global_rank_previous, update.global_rank_new, update.score_changed)

    async def set_ugc_id(self, ugc_id: int) -> None:
        """Set the UGC ID of the current user on the leaderboard."""
        await self._state.set_app_leaderboard_ugc(self.app.id, self.id, ugc_id)
