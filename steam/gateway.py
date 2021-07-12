"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz
Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

This is a modified version of
https://github.com/Rapptz/discord.py/blob/master/discord/gateway.py
and https://github.com/ValvePython/steam/blob/master/steam/core/cm.py
"""

from __future__ import annotations

import asyncio
import logging
import random
import struct
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from gzip import FCOMMENT, FEXTRA, FHCRC, FNAME
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar, Union
from zlib import MAX_WBITS, decompress

import aiohttp
import attr
from typing_extensions import Literal

from . import utils
from .enums import PersonaState, Result
from .errors import NoCMsFound
from .iterators import AsyncIterator
from .models import Registerable, register
from .protobufs import EMsg, GCMsg, GCMsgProto, Msg, MsgBase, MsgProto
from .protobufs.steammessages_clientserver_2 import CMsgGcClient

if TYPE_CHECKING:
    from .client import Client
    from .enums import UIMode
    from .game import GameToDict
    from .protobufs.steammessages_base import CMsgMulti
    from .protobufs.steammessages_clientserver_login import CMsgClientLogonResponse
    from .state import ConnectionState, EventParser


__all__ = (
    "ConnectionClosed",
    "CMServerList",
    "SteamWebSocket",
    "return_true",
    "Msgs",
)

log = logging.getLogger(__name__)
Msgs = Union[MsgProto, Msg]
M = TypeVar("M", bound=MsgBase)
READ_U32 = struct.Struct("<I").unpack_from


def return_true(*_, **__) -> Literal[True]:
    return True


@dataclass
class EventListener(Generic[M]):
    __slots__ = ("emsg", "check", "future")

    emsg: EMsg
    check: Callable[[M], bool]
    future: asyncio.Future[M]


if not TYPE_CHECKING:
    EventListener.__class_getitem__ = classmethod(lambda cls, params: cls)


@attr.dataclass(slots=True)
class CMServer:
    url: str
    score: float = 0.0


class ConnectionClosed(Exception):
    def __init__(self, cm: CMServer, cms: CMServerList):
        self.cm = cm
        self.cm_list = cms
        super().__init__(f"Connection to {self.cm.url}, has closed.")


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""


class CMServerList(AsyncIterator[CMServer]):
    __slots__ = ("cms", "cell_id")

    def __init__(self, state: ConnectionState, first_cm_to_try: Optional[CMServer] = None):
        super().__init__(state, None, None, None)
        self.cms: list[CMServer] = []
        self.cell_id = 0
        if first_cm_to_try is not None:
            self.append(first_cm_to_try)

    async def fill(self) -> None:
        if not await self.fetch_servers_from_api():
            raise NoCMsFound("No Community Managers could be found to connect to")

        if not self.cms:
            log.debug("No good servers left. Resetting...")
            self.reset_all()
            return await self.fill()

        for cm in await self.ping():
            self.append(cm)

    def clear(self) -> None:
        if self.cms:
            log.debug("List cleared.")
        self.cms = []

    async def fetch_servers_from_api(self, cell_id: int = 0) -> bool:
        log.debug("Attempting to fetch servers from the WebAPI")
        self.cell_id = cell_id
        try:
            resp = await self._state.http.get_cm_list(cell_id)
        except Exception as e:
            log.error(f"WebAPI fetch request failed with result: {e!r}")
            return False

        resp = resp["response"]
        if resp["result"] != Result.OK:
            log.error(
                f"Fetching the CMList failed with: Result: {Result(resp['result'])!r}. Message: {resp['message']!r}"
            )
            return False

        hosts = resp["serverlist_websockets"]
        log.debug(f"Received {len(hosts)} servers from WebAPI")

        self.cell_id = cell_id
        self.extend(hosts)

        return True

    def reset_all(self) -> None:
        log.debug("Marking all CM servers as good.")
        for cm in self.cms:
            cm.score = 0.0

    def extend(self, hosts: list[str]) -> None:
        total = len(self.cms)
        urls = [cm.url for cm in self.cms]
        for url in hosts:
            if url not in urls:
                self.cms.append(CMServer(url))
        if len(self.cms) > total:
            log.debug(f"Added {len(self.cms) - total} new CM server addresses.")

    async def ping(self) -> list[CMServer]:
        async def ping_cm(cm: CMServer) -> None:
            try:
                start = time.perf_counter()
                resp = await asyncio.wait_for(self._state.http._session.get(f"https://{cm.url}/cmping/"), timeout=5)
                latency = time.perf_counter() - start
                if resp.status != 200:
                    raise aiohttp.ClientError
                load = resp.headers["X-Steam-CMLoad"]
            except (KeyError, asyncio.TimeoutError, aiohttp.ClientError):
                try:
                    self.cms.remove(cm)
                except ValueError:
                    pass
            else:
                cm.score = (int(load) * 2) + latency
                best_cms.append(cm)

        best_cms = []
        await asyncio.gather(*(ping_cm(cm) for cm in self.cms))
        # TODO dynamically make sure we get good ones by doing maths or just check how the client does it
        log.debug("Finished pinging CMs")
        return sorted(best_cms, key=lambda cm: cm.score)


class KeepAliveHandler(threading.Thread):  # ping commands are cool
    def __init__(self, ws: SteamWebSocket, interval: int):
        super().__init__()
        self.ws = ws
        self.interval = interval
        self._main_thread_id = self.ws.thread_id
        self.heartbeat = MsgProto(EMsg.ClientHeartBeat)
        self.msg = "Keeping websocket alive with heartbeat {}."
        self.block_msg = "Heartbeat blocked for more than {} seconds."
        self.behind_msg = "Can't keep up, websocket is {:.1f} behind."
        self._stop_ev = threading.Event()
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self.latency = float("inf")

    def run(self) -> None:
        while not self._stop_ev.wait(self.interval):
            log.debug(self.msg.format(self.heartbeat))
            coro = self.ws.send_as_proto(self.heartbeat)
            f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)
            # block until sending is complete
            total = 0
            while True:
                try:
                    f.result(timeout=10)
                except asyncio.TimeoutError:  # alias to concurrent.futures.TimeoutError
                    total += 10
                    try:
                        frame = sys._current_frames()[self._main_thread_id]
                    except KeyError:
                        msg = self.block_msg
                    else:
                        stack = traceback.format_stack(frame)
                        msg = f'{self.block_msg}\nLoop thread traceback (most recent call last):\n{"".join(stack)}'
                    log.warning(msg.format(total))
                except Exception:
                    self.stop()
                else:
                    self.ack()
                    self._last_send = time.perf_counter()
                    break

    def stop(self) -> None:
        self._stop_ev.set()

    def ack(self) -> None:
        self._last_ack = time.perf_counter()
        self.latency = self._last_ack - self._last_send - self.interval
        if self.latency > 10:
            log.warning(self.behind_msg.format(self.latency))


class SteamWebSocket(Registerable):
    parsers: dict[EMsg, EventParser]

    def __init__(self, socket: aiohttp.ClientWebSocketResponse):
        self.socket = socket

        # state stuff
        self._connection: Optional[ConnectionState] = None
        self.cm_list: Optional[CMServerList] = None
        # the keep alive
        self._keep_alive: Optional[KeepAliveHandler] = None
        # an empty dispatcher to prevent crashes
        self._dispatch: Callable[..., None] = lambda *args, **kwargs: None
        self.cm: Optional[CMServer] = None
        self.thread_id = threading.get_ident()

        # ws related stuff
        self.listeners: list[EventListener[Msgs]] = []

        self.session_id = 0
        self.steam_id = 0
        self._current_job_id = 0
        self._gc_current_job_id = 0

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return self._keep_alive.latency

    def wait_for(self, emsg: EMsg, check: Callable[[M], bool] = return_true) -> asyncio.Future[M]:
        future = self.loop.create_future()
        entry = EventListener[M](emsg=emsg, check=check, future=future)
        self.listeners.append(entry)
        return future

    @classmethod
    async def from_client(
        cls, client: Client, cm: Optional[CMServer] = None, cm_list: Optional[CMServerList] = None
    ) -> SteamWebSocket:
        connection = client._connection
        cm_list = cm_list or CMServerList(connection, cm)
        async for cm in cm_list:
            log.info(f"Attempting to create a websocket connection to: {cm}")
            socket = await client.http.connect_to_cm(cm.url)
            log.debug(f"Connected to {cm}")

            ws = cls(socket)
            # dynamically add attributes needed
            ws._connection = connection
            ws.parsers.update(connection.parsers)
            ws._dispatch = client.dispatch
            ws.steam_id = client.user.id64
            ws.cm = cm
            ws.cm_list = cm_list
            await ws.send_as_proto(
                MsgProto(
                    EMsg.ClientLogon,
                    account_name=client.username,
                    web_logon_nonce=client.token,
                    client_os_type=4294966596,
                    protocol_version=65580,
                    chat_mode=2,
                    ui_mode=4,
                    qos_level=2,
                    client_language="english",
                )
            )
            ws._dispatch("connect")
            return ws

    async def poll_event(self) -> None:
        try:
            message = await self.socket.receive()
            if message.type is aiohttp.WSMsgType.BINARY and message.data:  # it can sometimes be None/empty
                return await self.receive(message.data)
            if message.type is aiohttp.WSMsgType.ERROR:
                log.debug(f"Received {message}")
                raise message.data
            if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                log.debug(f"Received {message}")
                raise WebSocketClosure
            log.debug(f"Dropped unexpected message type: {message}")
        except WebSocketClosure:
            await self.handle_close()

    async def receive(self, message: bytes) -> None:
        (emsg_value,) = READ_U32(message)
        emsg = EMsg(utils.clear_proto_bit(emsg_value))

        try:
            msg = MsgProto(emsg, message) if utils.is_proto(emsg_value) else Msg(emsg, message, extended=True)
        except Exception as exc:
            return log.error(f"Failed to deserialize message: {emsg!r}, {message!r}", exc_info=exc)

        log.debug("Socket has received %r from the websocket.", msg)

        self._dispatch("socket_receive", msg)
        self.run_parser(emsg, msg)

        # remove the dispatched listener
        removed = []
        for idx, entry in enumerate(self.listeners):
            if entry.emsg != emsg:
                continue

            future = entry.future
            if future.cancelled():
                removed.append(idx)
                continue

            try:
                valid = entry.check(msg)
            except Exception as exc:
                future.set_exception(exc)
                removed.append(idx)
            else:
                if valid:
                    future.set_result(msg)
                    removed.append(idx)

        for idx in reversed(removed):
            del self.listeners[idx]

    async def send(self, data: bytes) -> None:
        try:
            await self.socket.send_bytes(data)
        except ConnectionResetError:
            log.info("Connection closed")
            await self.handle_close()

    async def send_as_proto(self, message: Msgs) -> None:
        message.steam_id = self.steam_id
        message.session_id = self.session_id

        self._dispatch("socket_send", message)
        await self.send(bytes(message))

    async def send_gc_message(self, msg: Union[GCMsgProto, GCMsg]) -> int:  # for ext's to send GC messages
        message = MsgProto[CMsgGcClient](
            EMsg.ClientToGC,
            appid=self._connection.client.GAME.id,
            msgtype=utils.set_proto_bit(msg.msg) if isinstance(msg, GCMsgProto) else msg.msg,
        )
        message.body.payload = bytes(msg)
        message.header.body.routing_appid = self._connection.client.GAME.id
        message.header.body.job_id_source = self._gc_current_job_id = (self._gc_current_job_id + 1) % 10000 or 1

        log.debug(f"Sending GC message %r", msg)
        self._dispatch("gc_message_send", msg)
        await self.send_as_proto(message)
        return message.header.body.job_id_source

    async def close(self, code: int = 1000) -> None:
        message = MsgProto(EMsg.ClientLogOff)
        message.steam_id = self.steam_id
        message.session_id = self.session_id
        await self.socket.close(code=code, message=bytes(message))

    @register(EMsg.ClientLoggedOff)
    async def handle_close(self, _=None) -> None:
        if not self.socket.closed:
            await self.close()
            self.cm_list.queue.pop()  # pop the disconnected cm
        if self._keep_alive is not None:
            self._keep_alive.stop()
            self._keep_alive = None
        log.info(f"Websocket closed, cannot reconnect.")
        raise ConnectionClosed(self.cm, self.cm_list)

    @register(EMsg.ClientLogOnResponse)
    async def handle_logon(self, msg: MsgProto[CMsgClientLogonResponse]) -> None:
        if msg.result != Result.OK:
            log.debug(f"Failed to login with result: {msg.result}")
            if msg.result == Result.InvalidPassword:
                http = self._connection.http
                await http.logout()
                await http.login(http.username, http.password, shared_secret=http.shared_secret)
            return await self.handle_close()

        self.session_id = msg.session_id
        self.cm_list.cell_id = msg.body.cell_id

        interval = msg.body.out_of_game_heartbeat_seconds
        self._keep_alive = KeepAliveHandler(ws=self, interval=interval)
        self._keep_alive.start()
        log.debug("Heartbeat started.")

        await self.send_um("ChatRoom.GetMyChatRoomGroups")
        await self.change_presence(
            games=self._connection._games,
            state=self._connection._state,
            flags=self._connection._flags,
            force_kick=self._connection._force_kick,
            ui_mode=self._connection._ui_mode,
        )
        await self.send_as_proto(MsgProto(EMsg.ClientRequestCommentNotifications))

        log.debug("Logon completed")

    @staticmethod
    def unpack_multi(msg: MsgProto[CMsgMulti]) -> Optional[bytes]:
        log.debug(f"Decompressing payload ({len(msg.body.message_body)} -> {msg.body.size_unzipped})")
        data = msg.body.message_body
        if data[:2] != b"\037\213":
            return log.info(f"Received a file that's not GZipped")

        (flag,) = struct.unpack("<B", data[3:4])
        position = 10

        if flag & FEXTRA:
            (extra_len,) = struct.unpack("<H", data[position:2])
            position += 2 + extra_len
        if flag & FNAME:
            while True:
                terminator = data[position:1]
                position += 1
                if not terminator or terminator == b"\000":
                    return None
        if flag & FCOMMENT:
            while True:
                terminator = data[position:1]
                position += 1
                if not terminator or terminator == b"\000":
                    break
        if flag & FHCRC:
            position += 2

        decompressed = decompress(data[position:], wbits=-MAX_WBITS)

        if len(decompressed) != msg.body.size_unzipped:
            return log.info(f"Unzipped size mismatch for multi payload {msg}, discarding")

        return decompressed

    @register(EMsg.Multi)
    async def handle_multi(self, msg: MsgProto[CMsgMulti]) -> None:
        log.debug("Received a multi")
        data = self.unpack_multi(msg) if msg.body.size_unzipped else msg.body.message_body

        while data:
            (size,) = READ_U32(data)
            await self.receive(data[4 : 4 + size])
            data = data[4 + size :]

    async def send_um(self, name: str, **kwargs: Any) -> int:
        msg = MsgProto(EMsg.ServiceMethodCallFromClient, um_name=name, **kwargs)
        msg.header.body.job_id_source = self._current_job_id = (self._current_job_id + 1) % 10000 or 1
        await self.send_as_proto(msg)
        return msg.header.body.job_id_source

    async def send_um_and_wait(
        self,
        name: str,
        check: Optional[Callable[[MsgProto], bool]] = None,
        **kwargs: Any,
    ) -> MsgProto:
        job_id = await self.send_um(name, **kwargs)
        check = check or (lambda msg: msg.header.body.job_id_target == job_id)
        return await self.wait_for(EMsg.ServiceMethodResponse, check=check)

    async def change_presence(
        self,
        *,
        games: list[GameToDict],
        state: Optional[PersonaState],
        flags: int,
        ui_mode: Optional[UIMode],
        force_kick: bool,
    ) -> None:
        self._connection._games = games or self._connection._games
        self._connection._state = state or self._connection._state
        self._connection._ui_mode = ui_mode or self._connection._ui_mode
        self._connection._flags = flags or self._connection._flags
        self._connection._force_kick = force_kick

        if force_kick:
            kick = MsgProto(EMsg.ClientKickPlayingSession)
            log.debug("Kicking any currently playing sessions")
            await self.send_as_proto(kick)
        if games:
            activity = MsgProto(EMsg.ClientGamesPlayedWithDataBlob, games_played=games)
            log.debug(f"Sending {activity} to change activity")
            await self.send_as_proto(activity)
        if state is not None or flags:
            state = MsgProto(EMsg.ClientChangeStatus, persona_state=state, persona_state_flags=flags)
            log.debug(f"Sending {state} to change state")
            await self.send_as_proto(state)
        if ui_mode is not None:
            ui_mode = MsgProto(EMsg.ClientCurrentUIMode, uimode=ui_mode)
            log.debug(f"Sending {ui_mode} to change UI mode")
            await self.send_as_proto(ui_mode)
