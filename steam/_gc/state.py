"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import inspect
import logging
from contextvars import ContextVar
from types import CoroutineType
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar, cast, get_args

from .._const import CLEAR_PROTO_BIT, IS_PROTO
from ..app import App
from ..protobufs import GCMessage, GCProtobufMessage, friends
from ..protobufs.emsg import EMsg
from ..state import ConnectionState, ParserCallback
from ..trade import Inventory, Item
from ..types.id import AppID, AssetID, ContextID

if TYPE_CHECKING:
    from collections.abc import Mapping

    from typing_extensions import Self

    from ..gateway import GCMsgs
    from ..protobufs.client_server_2 import CMsgGcClientFromGC
    from ..utils import cached_property
    from .client import Client, ClientUser

log = logging.getLogger(__name__)
Inv = TypeVar("Inv", bound=Inventory[Item["ClientUser"], "ClientUser"])

APP = ContextVar[App]("APP")


class MultiEvent:
    def __init__(self, count: int):
        self.count = count
        self.ready = asyncio.Event()
        self._orig_count = self.count

    async def wait(self) -> None:
        await self.ready.wait()

    def set(self) -> None:
        self.count -= 1
        if self.count == 0:
            self.ready.set()

    def is_set(self) -> bool:
        return self.ready.is_set()

    def clear(self) -> None:
        self.count = self._orig_count
        self.ready.clear()


class GCState(ConnectionState, Generic[Inv]):
    gc_parsers: dict[
        type[GCMsgs], ParserCallback[Self, GCMsgs]
    ]  # different to parsers to save on dict lookups 1 vs 2 (1 for app, 1 for msg)
    client: Client
    _APP: Final[App]  # type: ignore
    if TYPE_CHECKING:

        @cached_property
        def user(self) -> ClientUser:
            ...

    def __init__(self, client: Client, **kwargs: Any):
        self._gc_connected = MultiEvent(len(client._GC_APPS))
        self._gc_ready = MultiEvent(len(client._GC_APPS))
        self.backpacks: Mapping[AppID, Inventory[Item[ClientUser], ClientUser]] = {}
        self.items_waiting: dict[tuple[AppID, AssetID], asyncio.Future[Item[ClientUser]]] = {}

        app = kwargs.pop("app", None)
        if app is not None:  # don't let them overwrite the main app
            try:
                kwargs["apps"].append(app)
            except (TypeError, KeyError):
                kwargs["apps"] = [app]
        kwargs["app"] = self._APP
        self._original_apps = [app for app in kwargs.get("apps", ()) if app.id not in self.client._GC_APPS]
        super().__init__(client, **kwargs)
        self._original_client_user_msg: friends.CMsgClientPersonaStateFriend | None = None

    def __init_subclass__(cls) -> None:
        cls.gc_parsers = {}
        for _, func in inspect.getmembers(cls, lambda x: inspect.isfunction(x) and hasattr(x, "__parser__")):
            try:
                params = list(inspect.get_annotations(func, eval_str=True).values())
            except NameError:
                continue
            msg = (
                args[0] if (args := get_args(params[0])) else params[0]
            )  # if it's a union only use the first type (Message | None or Message | Any)
            cls.gc_parsers[msg] = func

    @property
    def backpack(self) -> Inv | None:
        try:
            return cast(Inv, self.backpacks[APP.get().id])
        except KeyError:
            return None

    @backpack.setter
    def backpack(self, value: Inv) -> None:
        self.backpacks[APP.get().id] = value  # type: ignore

    def _get_gc_message(self) -> GCProtobufMessage | GCMessage | None:
        raise NotImplementedError()

    def parse_gc_message(self, msg: CMsgGcClientFromGC) -> None:
        app_id = AppID(msg.appid)
        emsg_value = CLEAR_PROTO_BIT(msg.msgtype)

        try:
            gc_msg = (GCProtobufMessage if IS_PROTO(msg.msgtype) else GCMessage)().parse(
                msg.payload[4:], emsg_value, app_id
            )
        except Exception as exc:
            return log.error("Failed to deserialize message: %r, %r", emsg_value, msg.payload, exc_info=exc)

        log.debug("Socket has received GC message %r from the websocket.", gc_msg)
        APP.set(self.client._GC_APPS[app_id])

        try:
            event_parser = self.gc_parsers[gc_msg.__class__]
        except (KeyError, TypeError):
            try:
                log.debug("Ignoring event %r", gc_msg, exc_info=True)
            except Exception:
                log.debug("Ignoring event with %r", gc_msg.__class__)
        else:
            try:
                result = event_parser(self, gc_msg)
            except Exception:
                return log.exception("Failed to execute %r", event_parser.__name__)

            if isinstance(result, CoroutineType):
                task = asyncio.create_task(result, name=f"steam.py GC {app_id}: {event_parser.__name__}")
                self.ws._pending_parsers.add(task)
                task.add_done_callback(self.ws._pending_parsers.remove)

        # remove the dispatched listener
        removed: list[int] = []
        for idx, entry in enumerate(self.ws.gc_listeners):
            if entry.msg != emsg_value or entry.app_id != app_id:
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
            del self.ws.gc_listeners[idx]

    async def fetch_backpack(self, backpack_cls: type[Inv]) -> Inv:
        app = APP.get()
        try:
            lock = self.user._inventory_locks[app.id]
        except KeyError:
            lock = self.user._inventory_locks[app.id] = asyncio.Lock()

        async with lock:  # requires a per-app lock to avoid Result.DuplicateRequest
            resp = await self.fetch_user_inventory(self.user.id64, app.id, ContextID(2), self.language)
        backpack = backpack_cls(
            state=self, proto=resp, owner=self.user, app=app, context_id=ContextID(2), language=self.language
        )
        self.backpacks[app] = backpack  # type: ignore
        return backpack

    def add_item_to_backpack(self, item: Item[ClientUser]) -> None:
        backpack = self.backpacks[item.app.id]
        backpack.items.append(item)  # type: ignore
        if future := self.items_waiting.get((item.app.id, item.id)):
            future.set_result(item)

    async def wait_for_item(self, id: AssetID) -> Item[ClientUser]:  # No intersection :( Item[ClientUser] & Any
        self.items_waiting[
            (APP.get().id, id)
        ] = future = asyncio.get_running_loop().create_future()  # TODO does this need to use ContextID as well?
        return await future


GCState.parsers = ConnectionState.parsers | {EMsg.ClientFromGC: GCState.parse_gc_message}  # type: ignore
