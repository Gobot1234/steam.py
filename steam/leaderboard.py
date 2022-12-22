"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, cast, overload

from typing_extensions import TypeVar

from . import utils
from ._const import URL
from .enums import (
    LeaderboardDataRequest,
    LeaderboardDisplayType,
    LeaderboardSortMethod,
    LeaderboardUploadScoreMethod,
    Type,
)
from .user import User, WrapsUser

if TYPE_CHECKING:
    from .app import PartialApp
    from .id import ID
    from .state import ConnectionState
    from .types.id import ID64, LeaderboardID


__all__ = (
    "LeaderboardScoreUpdate",
    "LeaderboardUser",
    "Leaderboard",
)


@dataclass(slots=True)
class LeaderboardScoreUpdate:
    global_rank_before: int
    global_rank_after: int
    score_changed: bool


class LeaderboardUser(WrapsUser):
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
        self.score = score
        self.details = details
        self.ugc_id = ugc_id


DisplayNameT = TypeVar("DisplayNameT", bound=str | None, default=None, covariant=True)


@dataclass(slots=True)
class Leaderboard(Generic[DisplayNameT]):
    _state: ConnectionState
    id: LeaderboardID
    """The leaderboard's id."""
    name: str
    """The name of the leaderboard."""
    app: PartialApp
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
        users: Sequence[ID[Literal[Type.Individual]]],
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
        users: Sequence[ID[Literal[Type.Individual]]] = (),
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
        update = await self._state.set_app_leaderboard_score(self.app.id, self.id, score, details, method)
        return LeaderboardScoreUpdate(update.global_rank_previous, update.global_rank_new, update.score_changed)

    async def set_ugc_id(self, ugc_id: int) -> None:
        await self._state.set_app_leaderboard_ugc(self.app.id, self.id, ugc_id)
