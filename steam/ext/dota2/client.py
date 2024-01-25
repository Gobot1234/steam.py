"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Final

from ..._const import timeout
from ..._gc import Client as Client_
from ...app import DOTA2
from ...ext import commands
from ...utils import MISSING
from .enums import Hero
from .models import LiveMatch
from .protobufs import watch
from .state import GCState  # noqa: TCH001

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
    _state: GCState  # type: ignore  # PEP 705

    async def top_live_matches(
        self,
        *,
        hero: Hero = MISSING,
        limit: int = 100,
    ) -> list[LiveMatch]:
        """Fetch top live matches

        This is similar to game list in the Watch Tab of Dota 2 game app.
        "Top matches" in this context means

        * tournament matches
        * highest average MMR matches

        Parameters
        ----------
        hero
            Filter matches by Hero. Note, in this case Game Coordinator will still use only current top100 live matches,
            i.e. requesting "filter by Muerta" will return only subset of those matches in which
            Muerta is currently being played. It will not look into lower MMR match than top100 to extend the return
            list to number of games from `limit` argument. This behavior is consistent with how Watch Tab works.
        limit
            Maximum amount of matches to be fetched.

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

        # mini-math: limit 100 -> start_game 90, 91 -> 90, 90 -> 80
        start_game = (limit - 1) // 10 * 10

        def callback(start_game: int, msg: watch.GCToClientFindTopSourceTVGamesResponse) -> bool:
            return msg.start_game == start_game

        futures = [
            self._state.ws.gc_wait_for(
                watch.GCToClientFindTopSourceTVGamesResponse,
                check=partial(callback, start_game),
            )
            for start_game in range(0, start_game + 1, 10)
        ]

        if hero is MISSING:
            await self._state.ws.send_gc_message(watch.ClientToGCFindTopSourceTVGames(start_game=start_game))
        else:
            await self._state.ws.send_gc_message(
                watch.ClientToGCFindTopSourceTVGames(start_game=start_game, hero_id=hero.value)
            )

        async with timeout(30.0):
            responses = await asyncio.gather(*futures)
        live_matches = [
            LiveMatch(self._state, match_info) for response in responses for match_info in response.game_list
        ]
        # still need to slice the list, i.e. in case user asks for 85 games, but live_matches above will have 90 matches
        return live_matches[:limit]

    async def tournament_live_games(
        self,
        # todo: league_id as integer is not human-readable/gettable thing, introduce methods to easily find those
        league_id: int,
    ) -> list[LiveMatch]:
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

        async with timeout(30.0):
            response = await future
        return [LiveMatch(self._state, match_info) for match_info in response.game_list]

    async def live_matches(
        self,
        # todo: lobby_ids is not easy to get by the user. Introduce methods to get it, i.e. from Rich Presence
        lobby_ids: list[int],
    ) -> list[LiveMatch]:
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
        future = self._state.ws.gc_wait_for(
            watch.GCToClientFindTopSourceTVGamesResponse,
            check=lambda msg: msg.specific_games == True,
        )
        await self._state.ws.send_gc_message(watch.ClientToGCFindTopSourceTVGames(lobby_ids=lobby_ids))

        async with timeout(30.0):
            response = await future
        # todo: test with more than 10 lobby_ids, Game Coordinator will probably chunk it wrongly or fail at all
        return [LiveMatch(self._state, match_info) for match_info in response.game_list]


class Bot(commands.Bot, Client):
    """Represents a Steam bot.

    :class:`Bot` is a subclass of :class:`~steam.ext.commands.Bot`, so whatever you can do with
    :class:`~steam.ext.commands.Bot` you can do with :class:`Bot`.
    """
