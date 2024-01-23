"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from typing import Final, Literal

from ..._const import timeout
from ..._gc import Client as Client_
from ...app import DOTA2
from ...ext import commands
from ...utils import MISSING
from .protobufs.dota_gcmessages_client_watch import (
    CMsgClientToGCFindTopSourceTVGames,
    CMsgGCToClientFindTopSourceTVGamesResponse,
)
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

    async def top_source_tv_games(
        self,
        *,
        search_key: str = MISSING,
        league_id: int = MISSING,
        hero_id: int = MISSING,
        start_game: Literal[0, 10, 20, 30, 40, 50, 60, 70, 80, 90] = 0,
        game_list_index: int = MISSING,
        lobby_ids: list[int] = MISSING,
    ) -> list[CMsgGCToClientFindTopSourceTVGamesResponse]:
        """Fetch Top Source TV Games.

        This functionality is similar to game list in the Watch Tab of Dota 2 game application.
        It fetches summary data for the currently on-going Dota 2 matches from the following categories:

        * tournament games
        * highest average mmr games
        * specific lobbies, like friends' games by their lobby_ids

        Note
        -------
        Note that the following documentation for keyword arguments to query against is rather observant
        than from official. So, please, if you know more or description is incorrect, contact us.

        Parameters
        ----------
        search_key : :class: `str`, optional
            Unknown purpose.
        league_id : :class: `int`, optional
            `league_id` for the professional tournament.
        hero_id : :class: `int`, optional
            `hero_id` to filter results by, just like in-client Watch Tab feature.
        start_game : :class: `Literal[0, 10, 20, 30, 40, 50, 60, 70, 80, 90]`, optional, by default 0
            This argument controls how many responses the game coordinator should return.
            For example, `start_game=0` returns a list with 1 Response,
            `start_game=90` returns a list of 10 Responses.
            Game coordinator fills each response in consequent manner with games that satisfy keyword arguments
            or with currently live highest average MMR games in case no other argument was given.
        game_list_index : :class: `int`, optional
            Only get responses matching `game_list_index`. Responses from Game Coordinator change
            from time to time. The `game_list_index` indicates that those responses belong to the same chunk.
        lobby_ids : :class: `list[int]`, optional
            Lobby ids to query against.

        Returns
        -------
        list[dota_gcmessages_client_watch.CMsgGCToClientFindTopSourceTVGamesResponse]
            The list of responses from Dota 2 Coordinator.
            Those are grouped into grouped into chunks of 10 games.

        Raises
        ------
        asyncio.TimeoutError
            Request time-outed. The reason for this might be inappropriate combination of keyword arguments,
            inappropriate argument values or simply Dota 2 Game Coordinator being down.
        """
        kwargs = locals()
        kwargs.pop("self")
        kwargs = {key: value for key, value in kwargs.items() if value is not MISSING}

        def start_game_check(start_game: int):
            def predicate(msg: CMsgGCToClientFindTopSourceTVGamesResponse) -> bool:
                return msg.start_game == start_game

            return predicate

        futures = [
            self._state.ws.gc_wait_for(
                CMsgGCToClientFindTopSourceTVGamesResponse,
                check=partial(lambda start_game, msg: msg.start_game == start_game, start_game),
            )
            for start_game in range(0, start_game + 1, 10)
        ]

        await self._state.ws.send_gc_message(CMsgClientToGCFindTopSourceTVGames(**kwargs))

        async with timeout(30.0):
            return await asyncio.gather(*futures)


class Bot(commands.Bot, Client):
    """Represents a Steam bot.

    :class:`Bot` is a subclass of :class:`~steam.ext.commands.Bot`, so whatever you can do with
    :class:`~steam.ext.commands.Bot` you can do with :class:`Bot`.
    """
