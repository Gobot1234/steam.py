"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from typing import Any

from typing_extensions import ClassVar, Never

from ...app import App
from ...client import Client as Client_
from ...enums import Language
from ...protobufs import GCMessage, GCProtobufMessage
from ...trade import Inventory
from ...user import ClientUser as ClientUser_
from .state import GCState

__all__ = ("Client",)


class ClientUser(ClientUser_):
    _state: GCState

    async def inventory(self, app: App, *, language: Language | None = None) -> Inventory:
        return (
            self._state.backpack
            if app == self._state.client.__class__._APP and self._state._gc_ready.is_set()
            else await super().inventory(app, language=language)
        )


class Client(Client_):
    _state: GCState
    _APP: ClassVar[App]
    _GC_HEART_BEAT: ClassVar = 30.0

    _ClientUserCls: ClassVar[type[ClientUser]] = ClientUser
    user: ClientUser

    def __init__(self, **options: Any):
        app = options.pop("app", None)
        if app is not None:  # don't let them overwrite the main app
            try:
                options["apps"].append(app)
            except (TypeError, KeyError):
                options["apps"] = [app]
        options["app"] = self._APP
        self._original_apps: list[App] | None = options.get("apps")
        super().__init__(**options)

    # things to override
    def _get_gc_message(self) -> GCProtobufMessage | GCMessage:
        raise NotImplementedError()

    def _get_state(self, **options: Any) -> Never:
        raise NotImplementedError("cannot instantiate Client without a state")

    async def login(self) -> None:
        if self._get_gc_message():

            async def ping_gc() -> None:
                await self._state.login_complete.wait()
                while not self.is_closed():
                    await self._state.ws.send_gc_message(self._get_gc_message())
                    await asyncio.sleep(self._GC_HEART_BEAT)

            await asyncio.gather(
                super().login(),
                ping_gc(),
            )
        else:
            await super().login()

    async def _handle_ready(self) -> None:
        (us,) = await self._state.ws.fetch_users((self.user.id64,))
        self.http.user = self.__class__._ClientUserCls(self._state, us)
        await super()._handle_ready()

    async def wait_for_gc_ready(self) -> None:
        await self._state._gc_ready.wait()

    # async def buy_item(self, def_id: int, price: int, def_ids: list[int], prices: int) -> None:
    #     ...
