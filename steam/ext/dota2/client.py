"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, overload

from ..._const import DOCS_BUILDING, timeout
from ..._gc import Client as Client_
from ...app import DOTA2
from ...ext import commands
from ...utils import (
    MISSING,
    cached_property,
)
from .models import ClientUser, LiveMatch, MatchMinimal, PartialMatch, PartialUser
from .protobufs import client_messages
from .state import GCState  # noqa: TCH001

if TYPE_CHECKING:
    from ...types.id import Intable
    from .enums import Hero
    from .models import User

__all__ = (
    "Client",
    "Bot",
)


class Client(Client_):
    """Represents a client connection that connects to Steam. This class is used to interact with the Steam API, CMs
    and the Dota 2 Game Coordinator.

    :class:`Client` is a subclass of :class:`steam.Client`, so whatever you can do with :class:`steam.Client` you can
    do with :class:`Client`.
    """

    _APP: Final = DOTA2
    _ClientUserCls = ClientUser
    _state: GCState  # type: ignore  # PEP 705

    if TYPE_CHECKING:

        @cached_property
        def user(self) -> ClientUser: ...

    # TODO: maybe this should exist as a part of the whole lib (?)
    def instantiate_partial_user(self, id: Intable) -> PartialUser:
        return self._state.get_partial_user(id)

    def instantiate_partial_match(self, id: int) -> PartialMatch:
        """Instantiate partial match.

        Convenience method, allows using match related requests to gc like `match.details`
        for any match.
        """
        return PartialMatch(self._state, id)

    async def top_live_matches(self, *, hero: Hero = MISSING, limit: int = 100) -> list[LiveMatch]:
        """Fetch top live matches.

        This is similar to game list in the Watch Tab of Dota 2 game app.
        "Top matches" in this context means
            * featured tournament matches
            * highest average MMR matches

        Parameters
        ----------
        hero
            Filter matches by Hero. Note, in this case Game Coordinator still only uses current top100 live matches,
            i.e. requesting "filter by Muerta" results only in subset of those matches in which
            Muerta is currently being played. It does not look into lower MMR match than top100 to extend the return
            list to number of games from `limit` argument. This behavior is consistent with how Watch Tab works.
        limit
            Maximum amount of matches to fetch. This works rather as a boundary limit than "number of matches" to
            fetch, i.e. Dota 2 will sometimes give 90 matches when `limit` is 100.
            Or even "successfully" return 0 matches.

        Returns
        -------
        List of currently live top matches.

        Raises
        ------
        ValueError
            `limit` value should be between 1 and 100 inclusively.
        asyncio.TimeoutError
            Request time-outed. The reason is usually Dota 2 Game Coordinator lagging or being down.
        """
        if limit < 1 or limit > 100:
            raise ValueError("limit value should be between 1 and 100 inclusively.")

        protos = await self._state.fetch_top_source_tv_games(
            start_game=(limit - 1) // 10 * 10,  # mini-math: limit 100 -> start_game 90, 91 -> 90, 90 -> 80
            hero_id=hero.value if hero else 0,
        )
        live_matches = [LiveMatch(self._state, match) for proto in protos for match in proto.game_list]
        # still need to slice the list, i.e. limit = 85, but live_matches above will have 90 matches
        return live_matches[:limit]

    async def tournament_live_matches(self, league_id: int) -> list[LiveMatch]:
        """Fetch currently live tournament matches

        Parameters
        ----------
        league_id
            Tournament league_id

        Returns
        -------
        List of currently live tournament matches.

        Raises
        ------
        asyncio.TimeoutError
            Request time-outed. The reason is usually Dota 2 Game Coordinator lagging or being down.
        """

        protos = await self._state.fetch_top_source_tv_games(league_id=league_id)
        # TODO: ^ this will only fetch 10 games because of implementation...
        # but does any tournament play more than 10 games at once? :x
        return [LiveMatch(self._state, match) for proto in protos for match in proto.game_list]

    @overload
    async def live_matches(self, *, lobby_id: int = ...) -> LiveMatch: ...

    @overload
    async def live_matches(self, *, lobby_ids: list[int] = ...) -> list[LiveMatch]: ...

    async def live_matches(self, *, lobby_id: int = MISSING, lobby_ids: list[int] = MISSING):
        """Fetch currently live matches by lobby_ids

        Parameters
        ----------
        lobby_ids
            Lobby IDs

        Returns
        -------
        List of live matches.

        Raises
        ------
        asyncio.TimeoutError
            Request time-outed. The reason is usually Dota 2 Game Coordinator lagging or being down.
        """
        if lobby_id is not MISSING and lobby_ids is not MISSING:
            raise TypeError("Cannot mix lobby_id and lobby_ids keyword arguments.")

        lobby_ids = [lobby_id] if lobby_id else lobby_ids

        protos = await self._state.fetch_top_source_tv_games(
            start_game=(len(lobby_ids) - 1) // 10 * 10,
            lobby_ids=lobby_ids,
        )
        live_matches = [LiveMatch(self._state, match) for proto in protos for match in proto.game_list]
        # ig live_matches[0] is IndexError safe because if lobby_id is not valid then TimeoutError occurs above;
        if lobby_id:
            try:
                return live_matches[0]
            except IndexError:
                raise RuntimeError(f"Failed to fetch match with {lobby_id=}")
        else:
            return live_matches

    async def matches_minimal(self, match_id: int) -> list[MatchMinimal]:
        proto = await self._state.fetch_matches_minimal(match_ids=[match_id])
        return [MatchMinimal(self._state, match) for match in proto.matches]

    async def matchmaking_stats(self):
        future = self._state.ws.gc_wait_for(client_messages.MatchmakingStatsResponse)
        await self._state.ws.send_gc_message(client_messages.MatchmakingStatsRequest())
        async with timeout(15.0):
            return await future

    if TYPE_CHECKING or DOCS_BUILDING:

        def get_user(self, id: Intable) -> User | None: ...

        async def fetch_user(self, id: Intable) -> User: ...


class Bot(commands.Bot, Client):
    """Represents a Steam bot.

    :class:`Bot` is a subclass of :class:`~steam.ext.commands.Bot`, so whatever you can do with
    :class:`~steam.ext.commands.Bot` you can do with :class:`Bot`.
    """
