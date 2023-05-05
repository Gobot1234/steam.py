"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Mapping
from inspect import get_annotations
from typing import Any, ClassVar, Final, cast, overload

from typing_extensions import Self

from ..app import App
from ..client import Client as Client_
from ..enums import Language
from ..state import ConnectionState
from ..trade import Inventory, Item
from ..types.id import AppID
from ..user import ClientUser as ClientUser_
from ..utils import cached_property
from .state import GCState

__all__ = ("Client",)


class ClientUser(ClientUser_):
    _state: GCState

    async def inventory(self, app: App, *, language: Language | None = None) -> Inventory[Item[Self], Self]:
        return (
            self._state.backpacks[app.id]
            if app.id in self._state.backpacks and self._state._gc_ready.is_set()
            else await super().inventory(app, language=language)
        )


class Client(Client_):
    _state: GCState
    _GC_HEART_BEAT: ClassVar = 30.0

    _ClientUserCls: ClassVar[type[ClientUser]] = ClientUser  # ideally one day this will be a generic
    _GC_BASES: Final[tuple[type[GCState], ...]] = ()
    _GC_APPS: Final[Mapping[AppID, App]] = {}
    user: cached_property[Self, ClientUser]  # type: ignore

    def __init_subclass__(cls) -> None:
        bases = [base for base in cls.__mro__ if issubclass(base, Client) and base is not Client]
        previous_state = None
        cls._GC_BASES = cast(  # type: ignore
            tuple[type[GCState], ...],
            tuple(
                dict.fromkeys(
                    previous_state := get_annotations(base, eval_str=True).get("_state", previous_state)
                    for base in reversed(bases)
                )
            ),
        )
        cls._GC_APPS = {  # type: ignore
            base._APP.id: base._APP for base in cls._GC_BASES
        }  # fmt: skip

        seen_methods = set[str]()
        for base in cls._GC_BASES:
            if (
                overridden_methods := seen_methods & base.__dict__.keys()
            ):  # How do we deal with subclasses of the same state overriding the method? Is anyone even going to do that?
                raise TypeError(f"Method(s) {', '.join(overridden_methods)} conflict inside of the state subclasses")
            seen_methods |= base.__dict__.keys()

    def _get_state(self, **options: Any) -> GCState:
        return type("GCState", self._GC_BASES, {})(self, **options)

    async def _ping_gc(self) -> None:
        await self._state.login_complete.wait()
        while not self.is_closed():
            for base in self._GC_BASES:
                await self._state.ws.send_gc_message(base._get_gc_message(self._state))
            await asyncio.sleep(self._GC_HEART_BEAT)

    @overload
    async def login(
        self,
        username: str,
        password: str,
        *,
        shared_secret: str = ...,
        identity_secret: str = ...,
    ) -> None:
        ...

    @overload
    async def login(
        self,
        *,
        refresh_token: str,
        shared_secret: str = ...,
        identity_secret: str = ...,
    ) -> None:
        ...

    async def login(self, *args: Any, **kwargs: Any) -> None:
        await asyncio.gather(super().login(*args, **kwargs), self._ping_gc())

    async def _handle_ready(self) -> None:
        us = self._state._original_client_user_msg
        assert us is not None
        self.http.user = self.__class__._ClientUserCls(self._state, us)
        await super()._handle_ready()

    async def wait_for_gc_ready(self) -> None:
        """Wait for the :meth:`on_gc_ready` method to be dispatched.

        See Also
        --------
        :meth:`wait_for_ready`
        """
        await self._state._gc_ready.wait()

    # async def buy_item(self, def_id: int, price: int, def_ids: list[int], prices: int) -> None:
    #     ...
