"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from typing import Any

from typing_extensions import ClassVar

from ...client import Client as Client_
from ...game import Game
from ...protobufs import GCMsg, GCMsgProto
from ...trade import Inventory
from ...user import ClientUser as ClientUser_
from .enums import Language
from .state import GCState

__all__ = ("Client",)


class ClientUser(ClientUser_):
    _state: GCState

    async def inventory(self, game: Game, *, language: Language | None = None) -> Inventory:
        return (
            self._state.backpack
            if game == self._state.client.__class__._GAME and self._state._gc_ready.is_set()
            else await super().inventory(game, language=language)
        )


class Client(Client_):
    _connection: GCState
    _GAME: ClassVar[Game]
    _GC_HEART_BEAT: ClassVar = 30.0

    _ClientUserCls: ClassVar[type[ClientUser]] = ClientUser
    user: ClientUser

    def __init__(self, **options: Any):
        game = options.pop("game", None)
        if game is not None:  # don't let them overwrite the main game
            try:
                options["games"].append(game)
            except (TypeError, KeyError):
                options["games"] = [game]
        options["game"] = self._GAME
        self._original_games: list[Game] | None = options.get("games")
        super().__init__(**options)

    # things to override
    def _get_gc_message(self) -> GCMsgProto[Any] | GCMsg[Any]:
        raise NotImplementedError()

    def _get_state(self, **options: Any) -> None:
        raise NotImplementedError("cannot instantiate Client without a state")

    async def connect(self) -> None:
        if self._get_gc_message():

            async def ping_gc() -> None:
                await self.wait_until_ready()
                while not self.is_closed():
                    await self.ws.send_gc_message(self._get_gc_message())
                    await asyncio.sleep(self._GC_HEART_BEAT)

            await asyncio.gather(
                super().connect(),
                ping_gc(),
            )
        else:
            await super().connect()

    async def _handle_ready(self) -> None:
        data = await self.http.get_user(self.user.id64)
        assert data is not None
        self.http.user = self.__class__._ClientUserCls(self._connection, data)
        await super()._handle_ready()

    async def wait_for_gc_ready(self) -> None:
        await self._connection._gc_ready.wait()

    # async def buy_item(self, def_id: int, price: int, def_ids: list[int], prices: int) -> None:
    #     ...
