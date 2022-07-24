"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, overload

from ... import utils
from ...abc import BaseUser
from ...enums import IntEnum
from ...gateway import EventListener, GCMsgsT
from ...models import register, return_true
from ...protobufs import EMsg, GCMsg, GCMsgProto, MsgProto
from ...state import ConnectionState
from ...trade import BaseInventory, Inventory

if TYPE_CHECKING:
    from ...game import Game
    from ...gateway import GCMsgsT
    from ...protobufs.client_server_2 import CMsgGcClient
    from .client import Client

log = logging.getLogger(__name__)
Inv = TypeVar("Inv", bound=BaseInventory[Any])
GCMsgProtoT = TypeVar("GCMsgProtoT", bound=GCMsgProto)
GCMsgT = TypeVar("GCMsgT", bound=GCMsg)


class GCState(ConnectionState):
    Language: ClassVar[type[IntEnum]]
    gc_parsers: dict[IntEnum, Callable[..., Any]]
    client: Client

    def __init__(self, client: Client, **kwargs: Any):
        super().__init__(client, **kwargs)
        self._gc_connected = asyncio.Event()
        self._gc_ready = asyncio.Event()
        self.backpack: Inventory = None  # type: ignore
        self._unpatched_inventory: Callable[[BaseUser, Game], Coroutine[Any, Any, Inventory]]
        self.gc_listeners: list[EventListener[Any]] = []

    @register(EMsg.ClientFromGC)
    async def parse_gc_message(self, msg: MsgProto[CMsgGcClient]) -> None:
        if msg.body.appid != self.client._GAME.id:
            return

        try:
            language = self.__class__.Language(utils.clear_proto_bit(msg.body.msgtype))
        except ValueError:
            return log.info(
                f"Ignoring unknown msg type: {msg.body.msgtype} ({utils.clear_proto_bit(msg.body.msgtype)})"
            )

        try:
            gc_msg = (
                GCMsgProto(language, msg.body.payload)
                if utils.is_proto(msg.body.msgtype)
                else GCMsg(language, msg.body.payload)
            )
        except Exception as exc:
            return log.error("Failed to deserialize message: %r, %r", language, msg.body.payload, exc_info=exc)
        else:
            log.debug("Socket has received GC message %r from the websocket.", gc_msg)

        self.dispatch("gc_message_receive", gc_msg)
        self.run_parser(language, gc_msg)

        # remove the dispatched listener
        removed = []
        for idx, entry in enumerate(self.gc_listeners):
            if entry.emsg != language:
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
    def gc_wait_for(self, emsg: IntEnum | None, check: Callable[[GCMsgT], bool]) -> asyncio.Future[GCMsgT]:
        ...

    @overload
    def gc_wait_for(self, emsg: IntEnum | None, check: Callable[[GCMsgProtoT], bool]) -> asyncio.Future[GCMsgProtoT]:
        ...

    def gc_wait_for(
        self, emsg: IntEnum | None, check: Callable[[GCMsgsT], bool] = return_true
    ) -> asyncio.Future[GCMsgsT]:
        future: asyncio.Future[GCMsgsT] = self.loop.create_future()
        entry = EventListener(emsg=emsg, check=check, future=future)
        self.gc_listeners.append(entry)
        return future

    async def fetch_backpack(self, backpack_cls: type[Inv]) -> Inv:
        resp = await self.http.get_client_user_inventory(
            self.client._GAME.id, self.client._GAME.context_id, self.http.language
        )
        return backpack_cls(
            state=self, data=resp, owner=self.client.user, game=self.client._GAME, language=self.http.language
        )
