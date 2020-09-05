# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz
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

import asyncio
import concurrent.futures
import logging
import random
import struct
import sys
import threading
import time
import traceback
from gzip import GzipFile
from io import BytesIO
from typing import TYPE_CHECKING, Callable, Dict, List, NamedTuple, NewType, Optional, Union

import aiohttp
from typing_extensions import Literal

from . import utils
from .enums import EPersonaState, EResult
from .errors import NoCMsFound
from .iterators import AsyncIterator
from .protobufs import EMsg, Msg, MsgProto

if TYPE_CHECKING:
    from .client import Client
    from .enums import EUIMode
    from .game import GameDict
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
GoodType = NewType("GOOD", Literal[True])
BadType = NewType("BAD", Literal[False])


def return_true(*_, **__) -> Literal[True]:
    return True


def check_job_id(job_id: int):
    exec(f"def check(msg): return msg.header.job_id_target == {job_id}")
    return locals()["check"]


class EventListener(NamedTuple):
    emsg: EMsg
    predicate: Callable[[Msgs], bool]
    future: asyncio.Future


class CMServer(NamedTuple):
    url: str
    state: Union["CMServerList.GOOD", "CMServerList.BAD"]
    score: float


class ConnectionClosed(Exception):
    def __init__(self, cm: str, cms: "CMServerList"):
        self.cm = cm
        self.cm_list = cms
        super().__init__(f"Connection to {self.cm}, has closed.")


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""


class CMServerList(AsyncIterator[str]):
    GOOD = GoodType(True)
    BAD = BadType(False)

    __slots__ = ("cms", "cell_id", "_state")

    def __init__(self, state: "ConnectionState", first_cm_to_try: str):
        super().__init__(state, None, None, None)
        self.cms: List[CMServer] = []
        self.cell_id = 0
        if first_cm_to_try is not None:
            self.queue.put_nowait(first_cm_to_try)

    def __len__(self) -> int:
        return len(self.cms)

    @utils.async_property
    async def best_cms(self) -> List[CMServer]:
        good_servers = [cm for cm in self.cms if cm.state]

        if not good_servers:
            log.debug("No good servers left. Resetting...")
            self.reset_all()
            await self.fill()
            return await self.best_cms

        random.shuffle(good_servers)
        return await self.ping_cms(good_servers)

    async def fill(self) -> None:
        if not await self.fetch_servers_from_api():
            raise NoCMsFound("No Community Managers could be found to connect to")

        for cm in await self.best_cms:
            self.queue.put_nowait(cm.url)

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
        if resp["result"] != EResult.OK:
            log.error(f'Fetching the CMList failed with Result: {EResult(resp["result"])} Message: {resp["message"]!r}')
            return False

        websockets_list = resp["serverlist_websockets"]
        log.debug(f"Received {len(websockets_list)} servers from WebAPI")

        self.clear()
        self.cell_id = cell_id
        self.merge_list(websockets_list)

        return True

    def reset_all(self) -> None:
        log.debug("Marking all CM servers as Good.")
        for cm in self.cms:
            self.mark_good(cm.url)

    def mark_good(self, url: str, score: float = 0.0) -> None:
        self.cms.append(CMServer(url, self.GOOD, score))

    def mark_bad(self, url: str) -> None:
        self.cms.append(CMServer(url, self.BAD, 0.0))

    def merge_list(self, hosts: List[str]) -> None:
        total = len(self)
        urls = [cm.url for cm in self.cms]
        for host in hosts:
            if host not in urls:
                self.mark_good(host)
        if len(self) > total:
            log.debug(f"Added {len(self) - total} new CM server addresses.")

    async def ping_cms(self, cms: Optional[List[CMServer]] = None, to_ping: int = 10) -> List[CMServer]:
        cms = self.cms or cms
        best_cms = []
        for cm in cms[:to_ping]:
            # TODO dynamically make sure we get good ones by checking len and stuff
            start = time.perf_counter()
            try:
                resp = await self._state.http._session.get(f"https://{cm.url}/cmping/", timeout=5)
                if resp.status != 200:
                    self.mark_bad(cm.url)
                load = resp.headers["X-Steam-CMLoad"]
            except (KeyError, asyncio.TimeoutError, aiohttp.ClientError):
                self.mark_bad(cm.url)
            else:
                latency = time.perf_counter() - start
                score = (int(load) * 2) + latency
                best_cms.append(cm)
                self.mark_good(cm.url, score)
        log.debug("Finished pinging CMs")
        return sorted(best_cms, key=lambda cm: cm.score)


class KeepAliveHandler(threading.Thread):  # ping commands are cool
    __slots__ = (
        "ws",
        "interval",
        "heartbeat",
        "heartbeat_timeout",
        "msg",
        "block_msg",
        "behind_msg",
        "latency",
        "_stop_ev",
        "_last_ack",
        "_last_send",
        "_main_thread_id",
    )

    def __init__(self, **kwargs):
        super().__init__()
        self.ws: "SteamWebSocket" = kwargs.pop("ws")
        self.interval: int = kwargs.pop("interval")
        self._main_thread_id = self.ws.thread_id
        self.heartbeat = MsgProto(EMsg.ClientHeartBeat)
        self.heartbeat_timeout = 60
        self.msg = "Keeping websocket alive with heartbeat {}."
        self.block_msg = "Heartbeat blocked for more than {} seconds."
        self.behind_msg = "Can't keep up, websocket is {:.1f} behind."
        self._stop_ev = threading.Event()
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self.latency = float("inf")

    def run(self) -> None:
        while not self._stop_ev.wait(self.interval):
            if self._last_ack + self.heartbeat_timeout < time.perf_counter():
                log.warning(f"Server {self.ws.cm} has stopped responding to the gateway. Closing and restarting.")
                coro = self.ws.handle_close()
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                try:
                    f.result()
                except Exception:
                    pass
                finally:
                    return self.stop()

            log.debug(self.msg.format(self.heartbeat))
            coro = self.ws.send_as_proto(self.heartbeat)
            f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)
            try:
                # block until sending is complete
                total = 0
                while 1:
                    try:
                        f.result(10)
                        break
                    except concurrent.futures.TimeoutError:
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

    def stop(self) -> None:
        self._stop_ev.set()

    def ack(self) -> None:
        self._last_ack = time.perf_counter()
        self.latency = self._last_ack - self._last_send - self.interval
        if self.latency > 10:
            log.warning(self.behind_msg.format(self.latency))


class SteamWebSocket:
    __slots__ = (
        "socket",
        "loop",
        "cm_list",
        "cm",
        "session_id",
        "thread_id",
        "listeners",
        "connected",
        "steam_id",
        "handlers",
        "_connection",
        "_dispatch",
        "_current_job_id",
        "_parsers",
        "_keep_alive",
    )

    def __init__(self, socket: aiohttp.ClientWebSocketResponse, *, loop: asyncio.AbstractEventLoop):
        self.socket = socket
        self.loop = loop

        # state stuff
        self._connection: Optional["ConnectionState"] = None
        self.cm_list: Optional[CMServerList] = None
        # the keep alive
        self._keep_alive: Optional[KeepAliveHandler] = None
        # an empty dispatcher to prevent crashes
        self._dispatch = return_true  # in practice this is the same as lambda *args: None
        self.cm: Optional[str] = None
        self.thread_id = threading.get_ident()

        # ws related stuff
        self.listeners: List[EventListener] = []
        self._parsers: Dict[EMsg, EventParser] = dict()

        self.connected = False
        self.session_id = 0
        self.steam_id = 0
        self._current_job_id = 0

        self.handlers = {
            EMsg.Multi: self.handle_multi,
            EMsg.ClientLogOnResponse: self.handle_logon,
        }

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return self._keep_alive.latency

    def wait_for(self, emsg: EMsg, predicate: Optional[Callable[[Msgs], bool]] = None) -> asyncio.Future:
        future = self.loop.create_future()
        entry = EventListener(emsg=emsg, predicate=predicate or return_true, future=future)
        self.listeners.append(entry)
        return future

    @classmethod
    async def from_client(
        cls, client: "Client", cm: Optional[str] = None, cms: Optional[CMServerList] = None
    ) -> "SteamWebSocket":
        connection = client._connection
        cm_list = cms or CMServerList(connection, cm)
        async for cm in cm_list:
            log.info(f"Attempting to create a websocket connection to: {cm}")
            socket: aiohttp.ClientWebSocketResponse = await client.http.connect_to_cm(cm)
            log.debug(f"Connected to {cm}")
            payload = MsgProto(
                EMsg.ClientLogon,
                account_name=client.username,
                web_logon_nonce=client.token,
                client_os_type=4294966596,
                protocol_version=65580,
                chat_mode=2,
                ui_mode=4,
                qos_level=2,
            )
            ws = cls(socket, loop=client.loop)
            # dynamically add attributes needed
            ws._connection = connection
            ws._parsers = connection.parsers
            ws._dispatch = client.dispatch
            ws.steam_id = client.user.id64
            ws.cm = cm
            ws.cm_list = cm_list
            ws.connected = True
            await ws.send_as_proto(payload)  # send the identification message straight away
            ws._dispatch("connect")
            return ws

    async def poll_event(self) -> None:
        try:
            message = await self.socket.receive()
            if message.type is aiohttp.WSMsgType.BINARY:
                if message.data:  # it can sometimes be None/empty
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
        self._dispatch("socket_raw_receive", message)

        emsg_value = struct.unpack_from("<I", message)[0]
        emsg = EMsg(utils.clear_proto_bit(emsg_value))
        if emsg in self.handlers:
            msg = MsgProto(emsg, message)
            self._dispatch("socket_receive", msg)
            return await self.handlers[emsg](msg)

        if not self.connected:
            return log.debug(f"Dropped unexpected message: {emsg} {message}")
        try:
            if utils.is_proto(emsg_value):
                msg = MsgProto(emsg, message)
            else:
                msg = Msg(emsg, message, extended=True)
            log.debug(f"Socket has received {msg!r} from the websocket.")
        except Exception as exc:
            try:
                if msg.msg != EMsg.ServiceMethodResponse:
                    pass
            except Exception:
                log.critical(f"Failed to deserialize message: {emsg!r}, {message}")
                return log.error(exc)

        self._dispatch("socket_receive", msg)

        try:
            func = self._parsers[emsg]
        except KeyError:
            log.debug(f"Ignoring event {msg!r}")
        else:
            await utils.maybe_coroutine(func, self._connection, msg)

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
                valid = entry.predicate(msg)
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
        self._dispatch("socket_raw_send", data)
        await self.socket.send_bytes(data=data)

    async def send_as_proto(self, message: Union[MsgProto, Msg]) -> None:
        message.steam_id = self.steam_id
        message.session_id = self.session_id

        self._dispatch("socket_send", message)
        await self.send(bytes(message))

    async def close(self, code: int = 4000) -> None:
        if self.connected:
            await self.send_as_proto(MsgProto(EMsg.ClientLogOff))
        await self.socket.close(code=code)

    async def handle_close(self):
        if not self.socket.closed:
            await self.close()
            self.cm_list.queue.get_nowait()  # pop the disconnected cm
        if self._keep_alive:
            self._keep_alive.stop()
            self._keep_alive = None
        log.info(f"Websocket closed, cannot reconnect.")
        raise ConnectionClosed(self.cm, self.cm_list)

    async def handle_logon(self, msg: MsgProto["CMsgClientLogonResponse"]) -> None:
        if msg.body.eresult == EResult.OK:
            log.debug("Logon completed")

            self.session_id = msg.session_id
            self.cm_list.cell_id = msg.body.cell_id

            interval = msg.body.out_of_game_heartbeat_seconds
            self._keep_alive = KeepAliveHandler(ws=self, interval=interval)
            self._keep_alive.start()
            log.debug("Heartbeat started.")

            await self.send_um("ChatRoom.GetMyChatRoomGroups#1_Request")
            await self.change_presence(
                games=self._connection._games,
                state=self._connection._state,
                ui_mode=self._connection._ui_mode,
                flags=self._connection._flags,
                force_kick=self._connection._force_kick,
            )
            return await self.send_as_proto(MsgProto(EMsg.ClientRequestCommentNotifications))
        if msg.body.eresult == EResult.InvalidPassword:
            http = self._connection.http
            await http.logout()
            await http.login(http.username, http.password, shared_secret=http.shared_secret)
        await self.handle_close()

    async def handle_multi(self, msg: MsgProto["CMsgMulti"]) -> None:
        log.debug("Received a multi, unpacking")
        if msg.body.size_unzipped:
            log.debug(f"Decompressing payload ({len(msg.body.message_body)} -> {msg.body.size_unzipped})")
            # aiofiles is overrated :P
            bytes_io = await utils.to_thread(BytesIO, msg.body.message_body)
            gzipped = await utils.to_thread(GzipFile, fileobj=bytes_io)
            data = await utils.to_thread(gzipped.read)
            if len(data) != msg.body.size_unzipped:
                return log.info(f"Unzipped size mismatch for multi payload {msg}, discarding")
        else:
            data = msg.body.message_body

        while len(data) > 0:
            size = struct.unpack_from("<I", data)[0]
            await self.receive(data[4 : 4 + size])
            data = data[4 + size :]

    async def send_um(self, name: str, **kwargs) -> int:
        msg = MsgProto(EMsg.ServiceMethodCallFromClient, _um_name=name, **kwargs)
        msg.header.job_id_source = self._current_job_id = (self._current_job_id + 1) % 10000 or 1
        await self.send_as_proto(msg)
        return msg.header.job_id_source

    async def send_um_and_wait(
        self, name: str, check: Optional[Callable[[Msgs], bool]] = None, timeout: float = 5.0, **kwargs
    ) -> Msgs:
        job_id = await self.send_um(name, **kwargs)
        if check is None:
            check = check_job_id(job_id)
        return await asyncio.wait_for(self.wait_for(EMsg.ServiceMethodResponse, predicate=check), timeout=timeout)

    async def change_presence(
        self,
        *,
        games: List["GameDict"],
        state: Optional["EPersonaState"],
        flags: int,
        ui_mode: Optional["EUIMode"],
        force_kick: bool,
    ) -> None:
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
