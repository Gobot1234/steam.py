"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any, Final, overload

from ..._const import DOCS_BUILDING, timeout
from ..._gc import Client as Client_
from ...app import DOTA2
from ...ext import commands
from ...utils import (
    MISSING,
    cached_property,
)
from .models import ClientUser, LiveMatch, MatchMinimal, PartialMatch, PartialUser
from .protobufs import client_messages, watch
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

    async def _fetch_find_top_source_tv_games(self, *, limit: int = 100, **kwargs: Any) -> list[LiveMatch]:
        """Private helper method to use `watch.ClientToGCFindTopSourceTVGames` requests.

        Valid kwargs are fields from `watch.ClientToGCFindTopSourceTVGames` definition.
        Some combinations are not working together.
        This is why `Client` offers three methods below with offered prepared kwargs options that make sense.
        """
        if limit < 1 or limit > 100:
            raise ValueError("limit value should be between 1 and 100 inclusively.")

        # mini-math: limit 100 -> start_game 90, 91 -> 90, 90 -> 80
        start_game = (limit - 1) // 10 * 10

        def check(start_game: int, msg: watch.GCToClientFindTopSourceTVGamesResponse) -> bool:
            return msg.start_game == start_game

        futures = [
            self._state.ws.gc_wait_for(
                watch.GCToClientFindTopSourceTVGamesResponse,
                check=partial(check, start_game),
            )
            for start_game in range(0, start_game + 1, 10)
        ]
        await self._state.ws.send_gc_message(watch.ClientToGCFindTopSourceTVGames(start_game=start_game, **kwargs))
        async with timeout(15.0):
            responses = await asyncio.gather(*futures)
        # each response.game_list is 10 games (except possibly last one if filtered by hero)
        live_matches = [LiveMatch(self._state, match) for response in responses for match in response.game_list]
        # still need to slice the list, i.e. limit = 85, but live_matches above will have 90 matches
        return live_matches[:limit]

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

        hero_id = hero.value if hero else 0
        return await self._fetch_find_top_source_tv_games(limit=limit, hero_id=hero_id)

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

        future = self._state.ws.gc_wait_for(
            watch.GCToClientFindTopSourceTVGamesResponse,
            check=lambda msg: msg.league_id == league_id,
        )
        await self._state.ws.send_gc_message(watch.ClientToGCFindTopSourceTVGames(league_id=league_id))

        async with timeout(15.0):
            response = await future
        return [LiveMatch(self._state, match) for match in response.game_list]

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
        live_matches = await self._fetch_find_top_source_tv_games(limit=len(lobby_ids), lobby_ids=[lobby_ids])
        # ig live_matches[0] is IndexError safe because if lobby_id is not valid then TimeoutError occurs above;
        return live_matches[0] if lobby_id else live_matches

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
