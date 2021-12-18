from __future__ import annotations

import asyncio
from typing import Any

from typing_extensions import ClassVar, Final

from ...abc import BaseUser
from ...client import Client as Client_
from ...game import Game
from ...protobufs import GCMsg, GCMsgProto
from ...trade import Inventory
from .state import GCState

__all__ = ("Client",)


class Client(Client_):
    _connection: GCState
    _GAME: Final[Game] = Any
    _GC_HEART_BEAT: ClassVar = 30.0

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

    async def _handle_ready(self_) -> None:
        async def inventory(self: Any, game: Game) -> Inventory:
            return (
                self._connection.backpack
                if game == self.__class__._GAME and self_._connection._gc_ready.is_set()
                else await BaseUser.inventory(self, game)
            )

        self_._connection._unpatched_inventory = self_.user._inventory_func
        self_.user._inventory_func = inventory

        await super()._handle_ready()

    async def wait_for_gc_ready(self) -> None:
        await self._connection._gc_ready.wait()

    async def buy_item(self, def_id: int, price: int, def_ids: list[int], prices: int) -> None:
        ...
