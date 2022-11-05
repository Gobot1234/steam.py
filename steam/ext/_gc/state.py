"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, overload

from ..._const import CLEAR_PROTO_BIT, IS_PROTO
from ...abc import BaseUser
from ...enums import IntEnum
from ...gateway import EventListener, GCMsgProtoT, GCMsgsT, GCMsgT
from ...models import register, return_true
from ...protobufs import EMsg, GCMessage, GCProtobufMessage
from ...state import ConnectionState
from ...trade import BaseInventory, Inventory

if TYPE_CHECKING:
    from ...app import App
    from ...gateway import GCMsgsT
    from ...protobufs.client_server_2 import CMsgGcClientFromGC
    from .client import Client

log = logging.getLogger(__name__)
Inv = TypeVar("Inv", bound=BaseInventory[Any])


class GCState(ConnectionState):
    Language: ClassVar[type[IntEnum]]
    gc_parsers: dict[IntEnum, Callable[..., Any]]
    client: Client

    def __init__(self, client: Client, **kwargs: Any):
        super().__init__(client, **kwargs)
        self._gc_connected = asyncio.Event()
        self._gc_ready = asyncio.Event()
        self.backpack: Inventory = None  # type: ignore
        self._unpatched_inventory: Callable[[BaseUser, App], Coroutine[Any, Any, Inventory]]
        self.gc_listeners: list[EventListener[Any]] = []

    @register(EMsg.ClientFromGC)
    async def parse_gc_message(self, msg: CMsgGcClientFromGC) -> None:
        if msg.appid != self.client._APP.id:
            return

        try:
            language = self.__class__.Language(CLEAR_PROTO_BIT(msg.msgtype))
        except ValueError:
            return log.info(f"Ignoring unknown msg type: {msg.msgtype} ({CLEAR_PROTO_BIT(msg.msgtype)})")

        try:
            gc_msg = (
                GCProtobufMessage().parse(msg.payload, language)
                if IS_PROTO(msg.msgtype)
                else GCMessage().parse(msg.payload, language)
            )
        except Exception as exc:
            return log.error("Failed to deserialize message: %r, %r", language, msg.payload, exc_info=exc)
        else:
            log.debug("Socket has received GC message %r from the websocket.", gc_msg)

        self.dispatch("gc_message_receive", gc_msg)
        self.run_parser(gc_msg)

        # remove the dispatched listener
        removed: list[int] = []
        for idx, entry in enumerate(self.gc_listeners):
            if entry.msg != language:
                continue

            future = entry.future
            if future.cancelled():
                removed.append(idx)
                continue

            try:
                valid = entry.check(gc_msg)
            except Exception as exc:
                future.set_exception(exc)
                removed.append(idx)
            else:
                if valid:
                    future.set_result(gc_msg)
                    removed.append(idx)

        for idx in reversed(removed):
            del self.gc_listeners[idx]

    @overload
    def gc_wait_for(
        self, *, emsg: IntEnum | None, check: Callable[[GCMsgsT], bool] = return_true
    ) -> asyncio.Future[GCMsgsT]:
        ...

    @overload
    def gc_wait_for(
        self, msg: type[GCMsgT], *, check: Callable[[GCMsgT], bool] = return_true
    ) -> asyncio.Future[GCMsgT]:
        ...

    @overload
    def gc_wait_for(
        self, msg: type[GCMsgProtoT], *, check: Callable[[GCMsgProtoT], bool] = return_true
    ) -> asyncio.Future[GCMsgProtoT]:
        ...

    def gc_wait_for(
        self,
        msg: type[GCMsgsT] | None = None,
        *,
        emsg: IntEnum | None = None,
        check: Callable[[GCMsgsT], bool] = return_true,
    ) -> asyncio.Future[GCMsgsT]:
        future: asyncio.Future[GCMsgsT] = self.loop.create_future()
        entry = EventListener(msg=msg.MSG if msg else emsg, check=check, future=future)
        self.gc_listeners.append(entry)
        return future

    async def fetch_backpack(self, backpack_cls: type[Inv]) -> Inv:
        try:
            lock = self.user._inventory_locks[self.client._APP.id]
        except KeyError:
            lock = self.user._inventory_locks[self.client._APP.id] = asyncio.Lock()

        async with lock:  # requires a per-app lock to avoid Result.DuplicateRequest
            resp = await self.fetch_user_inventory(
                self.user.id64, self.client._APP.id, self.client._APP.context_id, self.language
            )
        return backpack_cls(state=self, data=resp, owner=self.user, app=self.client._APP, language=self.language)
