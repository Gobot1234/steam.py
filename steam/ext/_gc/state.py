from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, ClassVar

from ... import utils
from ...abc import BaseUser
from ...enums import IntEnum
from ...models import register
from ...protobufs import EMsg, GCMsg, GCMsgProto, MsgProto
from ...state import ConnectionState
from ...trade import Inventory

if TYPE_CHECKING:
    from steam.protobufs.client_server_2 import CMsgGcClient

    from ...game import Game
    from .client import Client

log = logging.getLogger(__name__)


class GCState(ConnectionState):
    Language: ClassVar[IntEnum]
    gc_parsers: dict[IntEnum, Callable[..., Any]]
    client: Client

    def __init__(self, client: Client, **kwargs: Any):
        super().__init__(client, **kwargs)
        self._gc_connected = asyncio.Event()
        self._gc_ready = asyncio.Event()
        self.backpack: Inventory = Any
        self._unpatched_inventory: Callable[[BaseUser, Game], Coroutine[Any, Any, Inventory]]

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
