"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/ValvePython/steam/blob/master/steam/core/cm.py
https://github.com/Rapptz/discord.py/tree/master/discord/gateway.py
The appropriate licenses are in LICENSE
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import logging
import random
import sys
import threading
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from gzip import FCOMMENT, FEXTRA, FHCRC, FNAME  # type: ignore
from hashlib import sha1
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Final, Generic, TypeAlias, TypeVar, overload
from zlib import MAX_WBITS, decompress

import aiohttp
import async_timeout
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from . import utils
from ._const import CLEAR_PROTO_BIT, DEFAULT_CMS, IS_PROTO, MISSING, READ_U32, SET_PROTO_BIT
from .enums import *
from .errors import NoCMsFound, WSException
from .guard import generate_one_time_code
from .models import Registerable, register, return_true
from .protobufs import (
    EMsg,
    GCMessage,
    GCProtobufMessage,
    Message,
    ProtobufMessage,
    UnifiedMessage,
    auth,
    chat,
    client_server,
    client_server_2,
    friends,
    login,
)
from .user import ClientUser

if TYPE_CHECKING:
    from .client import Client
    from .enums import UIMode
    from .protobufs.base import CMsgMulti
    from .state import ConnectionState
    from .types.http import Coro


__all__ = (
    "ConnectionClosed",
    "SteamWebSocket",
    "CMServer",
    "Msgs",
)

log = logging.getLogger(__name__)
ProtoMsgs: TypeAlias = ProtobufMessage | Message
GCMsgs: TypeAlias = GCProtobufMessage | GCMessage
GCMsgsT = TypeVar("GCMsgsT", GCProtobufMessage, GCMessage)
ProtoMsgsT = TypeVar("ProtoMsgsT", ProtobufMessage, Message)
Msgs: TypeAlias = "ProtoMsgs | GCMsgs"
MsgsT = TypeVar("MsgsT", ProtobufMessage, Message, GCProtobufMessage, GCMessage)
ProtoMsgT = TypeVar("ProtoMsgT", bound=ProtobufMessage)
UnifiedMsgT = TypeVar("UnifiedMsgT", bound=UnifiedMessage)
MsgT = TypeVar("MsgT", bound=Message)
GCMsgT = TypeVar("GCMsgT", bound=GCMessage)
GCMsgProtoT = TypeVar("GCMsgProtoT", bound=GCProtobufMessage)


@dataclass(slots=True)
class EventListener(Generic[MsgsT]):
    msg: IntEnum | None
    check: Callable[[MsgsT], bool]
    future: asyncio.Future[MsgsT]

    if not TYPE_CHECKING:
        __class_getitem__ = classmethod(lambda cls, params: cls)


@dataclass(slots=True)
class CMServer:
    _state: ConnectionState
    url: str
    weighted_load: float

    def connect(self) -> Coro[aiohttp.ClientWebSocketResponse]:
        return self._state.http.connect_to_cm(self.url)

    async def ping(self) -> float:
        try:
            async with async_timeout.timeout(5):
                async with self._state.http._session.get(f"https://{self.url}/cmping/") as resp:
                    if resp.status != 200:
                        raise KeyError
                    return int(resp.headers["X-Steam-CMLoad"])
        except (KeyError, asyncio.TimeoutError, aiohttp.ClientError):
            return float("inf")


async def fetch_cm_list(state: ConnectionState, cell_id: int = 0) -> AsyncGenerator[CMServer, None]:
    if state._connected_cm is not None:
        yield state._connected_cm
    log.debug("Attempting to fetch servers from the WebAPI")
    state.cell_id = cell_id
    try:
        data = await state.http.get_cm_list(cell_id)
    except Exception:
        servers = [CMServer(state, url=cm_url, weighted_load=0) for cm_url in DEFAULT_CMS]
        random.shuffle(servers)
        log.debug("Error occurred when fetching CM server list, falling back to internal list", exc_info=True)
        for cm in servers:
            yield cm
        return

    resp = data["response"]
    if not resp["success"]:
        servers = [CMServer(state, url=cm_url, weighted_load=0) for cm_url in DEFAULT_CMS]
        random.shuffle(servers)
        log.debug("Error occurred when fetching CM server list, falling back to internal list", exc_info=True)
        for cm in servers:
            yield cm
        return

    hosts: list[dict[str, Any]] = resp["serverlist"]
    log.debug(f"Received {len(hosts)} servers from WebAPI")
    for cm in sorted(
        (CMServer(state, url=server["endpoint"], weighted_load=server["wtd_load"]) for server in hosts),
        key=attrgetter("weighted_load"),
    ):  # they should already be sorted but oh well
        yield cm


class ConnectionClosed(Exception):
    def __init__(self, cm: CMServer):
        self.cm = cm
        super().__init__(f"Connection to {self.cm.url}, has closed.")


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""


class KeepAliveHandler(threading.Thread):
    def __init__(self, ws: SteamWebSocket, interval: int):
        super().__init__()
        self.ws = ws
        self.interval = interval
        self._main_thread_id = self.ws.thread_id
        self.heartbeat = login.CMsgClientHeartBeat(send_reply=True)
        self.msg = "Keeping websocket alive with heartbeat %s."
        self.block_msg = "Heartbeat blocked for more than {total} seconds."
        self.behind_msg = "Can't keep up, websocket is {total:.1f}s behind."
        self._stop_ev = threading.Event()
        self._last_recv = float("-inf")
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self.latency = float("inf")

    def run(self) -> None:
        while not self._stop_ev.wait(self.interval):
            if self._last_recv + 60 < time.perf_counter():
                log.warning("CM %r has stopped responding to the gateway. Closing and restarting.", self.ws.cm)
                coro = self.ws.close(4000)
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                try:
                    f.result()
                except Exception:
                    log.exception("An error occurred while stopping the gateway. Ignoring.")
                finally:
                    return self.stop()

            log.debug(self.msg, self.heartbeat)
            coro = self.ws.send_proto(self.heartbeat)
            f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)
            # block until sending is complete
            total = 0
            try:
                while True:
                    try:
                        f.result(timeout=10)
                        break
                    except concurrent.futures.TimeoutError:
                        total += 10
                        try:
                            frame = sys._current_frames()[self._main_thread_id]  # noqa
                        except KeyError:
                            msg = self.block_msg
                        else:
                            stack = "".join(traceback.format_stack(frame))
                            msg = f"{self.block_msg}\nLoop thread traceback (most recent call last):\n{stack}"
                        log.warning(msg.format(total=total))

            except Exception:
                self.stop()
            else:
                self._last_send = time.perf_counter()

    def stop(self) -> None:
        self._stop_ev.set()

    def tick(self) -> None:
        self._last_recv = time.perf_counter()

    def ack(self) -> None:
        ack_time = time.perf_counter()
        self._last_ack = ack_time
        self.latency = ack_time - self._last_send
        if self.latency > 10:
            log.warning(self.behind_msg.format(total=self.latency))


class SteamWebSocket(Registerable):
    parsers: dict[EMsg, Callable[..., Any]]

    def __init__(
        self,
        state: ConnectionState,
        socket: aiohttp.ClientWebSocketResponse,
        cm_list: AsyncGenerator[CMServer, None],
        cm: CMServer,
    ):
        self.socket = socket

        # state stuff
        self._state = state
        self.cm_list = cm_list
        self.cm = cm
        # the keep alive
        self._keep_alive: KeepAliveHandler
        self._dispatch = state.dispatch
        self.thread_id = threading.get_ident()

        # ws related stuff
        self.listeners: list[EventListener[Any]] = []
        self.parsers.update(state.parsers)
        self.closed = False

        self.session_id = 0
        self.steam_id = 76561197960265728
        self._current_job_id = 0
        self._gc_current_job_id = 0
        self.refresh_token: str
        self.access_token: str
        self.client_id: int

    @property
    def latency(self) -> float:
        """Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return self._keep_alive.latency

    @overload
    def wait_for(
        self, *, emsg: EMsg | None, check: Callable[[ProtoMsgsT], bool] = return_true
    ) -> asyncio.Future[ProtoMsgsT]:
        ...

    @overload
    def wait_for(self, msg: type[MsgT], check: Callable[[MsgT], bool] = return_true) -> asyncio.Future[MsgT]:
        ...

    @overload
    def wait_for(
        self, msg: type[ProtoMsgT], check: Callable[[ProtoMsgT], bool] = return_true
    ) -> asyncio.Future[ProtoMsgT]:
        ...

    def wait_for(  # type: ignore
        self,
        msg: type[ProtoMsgs] | None = None,
        *,
        emsg: EMsg | None = None,
        check: Callable[[ProtoMsgsT], bool] = return_true,
    ) -> asyncio.Future[ProtoMsgsT]:
        future: asyncio.Future[ProtoMsgsT] = self.loop.create_future()
        entry = EventListener(msg=msg.MSG if msg else emsg, check=check, future=future)
        self.listeners.append(entry)
        return future

    @classmethod
    async def from_client(cls, client: Client) -> SteamWebSocket:
        state = client._state
        token = await client.token()
        cm_list = fetch_cm_list(state)
        async for cm in cm_list:
            log.info(f"Attempting to create a websocket connection to: {cm}")
            socket = await cm.connect()
            log.debug(f"Connected to {cm}")

            self = cls(state, socket, cm_list, cm)
            await self.send_proto(
                MsgProto(
                    EMsg.ClientLogon,
                    account_name=client.username,
                    web_logon_nonce=token,
                    client_os_type=4294966596,
                    client_language=self._state.http.language.api_name,
                    protocol_version=65580,
                    chat_mode=2,
                    ui_mode=self._state._ui_mode,
                    qos_level=2,
                )
            )
            self._dispatch("connect")
            return self
        raise NoCMsFound("No CMs found could be connected to. Steam is likely down")

    async def poll_event(self) -> None:
        try:
            message = await self.socket.receive()
            if message.type is aiohttp.WSMsgType.BINARY:
                return self.receive(bytearray(message.data))
            if message.type is aiohttp.WSMsgType.ERROR:
                log.debug(f"Received {message}")
                raise message.data
            if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):
                log.debug(f"Received {message}")
                raise WebSocketClosure
            log.debug(f"Dropped unexpected message type: {message}")
        except WebSocketClosure:
            await self.handle_close()

    def receive(self, message: bytearray) -> None:
        emsg_value = READ_U32(message)
        try:
            msg = (
                ProtobufMessage().parse(message[4:], CLEAR_PROTO_BIT(emsg_value))
                if IS_PROTO(emsg_value)
                else Message().parse(message[4:], emsg_value)
            )
        except Exception as exc:
            return log.error(
                f"Failed to deserialize message: {EMsg(CLEAR_PROTO_BIT(emsg_value))!r}, {message!r}", exc_info=exc
            )

        log.debug("Socket has received %r from the websocket.", msg)

        if hasattr(self, "_keep_alive"):
            self._keep_alive.tick()

        self._dispatch("socket_receive", msg)
        self.run_parser(msg)

        # remove the dispatched listener
        removed: list[int] = []
        for idx, entry in enumerate(self.listeners):
            if entry.msg != msg.MSG and entry.msg is not None:
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

    async def send_proto(self, message: ProtoMsgs) -> None:
        message.header.steam_id = self.steam_id
        message.header.session_id = self.session_id

        self._dispatch("socket_send", message)
        await self.send(bytes(message))

    async def send_gc_message(self, msg: GCMsgs) -> int:  # for ext's to send GC messages
        client = self._state.client
        if __debug__ or TYPE_CHECKING:
            from .ext._gc import Client as GCClient

            assert isinstance(client, GCClient), "Attempting to send a GC message without a GC client"

        app_id = client._APP.id
        message = client_server_2.CMsgGcClientToGC(
            appid=app_id,
            msgtype=SET_PROTO_BIT(msg.MSG) if isinstance(msg, GCProtobufMessage) else msg.MSG,
            payload=bytes(msg),
        )
        message.header.routing_app_id = app_id
        message.header.job_id_source = self._gc_current_job_id = (self._gc_current_job_id + 1) % 10000 or 1

        log.debug("Sending GC message %r", msg)
        self._dispatch("gc_message_send", msg)
        await self.send_proto(message)
        return message.header.job_id_source

    async def close(self, code: int = 1000) -> None:
        message = login.CMsgClientLogOff()
        message.header.steam_id = self.steam_id
        message.header.session_id = self.session_id
        await self.socket.close(code=code, message=bytes(message))

    @register(EMsg.ClientLoggedOff)
    async def handle_close(self, _: Any = None) -> None:
        if self.closed:  # don't want ConnectionClosed to be raised multiple times
            return
        if not self.socket.closed:
            await self.close()
        if hasattr(self, "_keep_alive"):
            self._keep_alive.stop()
            del self._keep_alive
        log.info("Websocket closed, cannot reconnect.")
        self.closed = True
        raise ConnectionClosed(self.cm)

    @register(EMsg.ClientLogOnResponse)
    async def handle_logon(self, msg: MsgProto[login.CMsgClientLogonResponse]) -> None:
        if msg.result != Result.OK:
            log.debug(f"Failed to login with result: {msg.result}")
            if msg.result == Result.InvalidPassword:
                http = self._state.http
                await http.logout()
                await http.login(http.username, http.password, shared_secret=http.shared_secret)
            return await self.handle_close()

        self.session_id = msg.session_id
        self._state.cell_id = msg.body.cell_id

        interval = msg.body.out_of_game_heartbeat_seconds
        self._keep_alive = KeepAliveHandler(ws=self, interval=interval)
        self._keep_alive.start()
        log.debug("Heartbeat started.")

        await self.send_um("ChatRoom.GetMyChatRoomGroups")
        await self.change_presence(
            apps=self._state._apps,
            state=self._state._state,
            flags=self._state._flags,
            force_kick=self._state._force_kick,
        )
        await self.send_proto(MsgProto(EMsg.ClientGetEmoticonList))
        await self.send_proto(MsgProto(EMsg.ClientRequestCommentNotifications))
        await self.send_proto(MsgProto(EMsg.ClientServerTimestampRequest, client_request_timestamp=time.time() * 1000))

        log.debug("Logon completed")

    @register(EMsg.ClientHeartBeat)
    def ack_heartbeat(self, msg: MsgProto[login.CMsgClientHeartBeat]) -> None:
        self._keep_alive.ack()

    @register(EMsg.ClientServerTimestampResponse)
    def set_steam_time(self, msg: MsgProto[login.CMsgClientServerTimestampResponse]) -> None:
        self.server_offset = timedelta(milliseconds=msg.body.server_timestamp_ms - msg.body.client_request_timestamp)

    @staticmethod
    def unpack_multi(msg: MsgProto[CMsgMulti]) -> bytes | None:
        data = msg.body.message_body
        log.debug(f"Decompressing payload ({len(data)} -> {msg.body.size_unzipped})")
        if data[:2] != b"\037\213":
            return log.info("Received a file that's not GZipped")

        flag = int.from_bytes(data[3:4], byteorder="little")
        position = 10

        if flag:  # this isn't ever hit, might as well save a few nanos
            if flag & FEXTRA:
                extra_len = int.from_bytes(data[position:2], byteorder="little")
                position += 2 + extra_len
            if flag & FNAME:
                while True:
                    terminator = data[position:1]
                    position += 1
                    if not terminator or terminator == b"\000":
                        break
            if flag & FCOMMENT:
                while True:
                    terminator = data[position:1]
                    position += 1
                    if not terminator or terminator == b"\000":
                        break
            if flag & FHCRC:
                position += 2

        decompressed = decompress(data[position:], wbits=-MAX_WBITS)

        if len(decompressed) != msg.size_unzipped:
            return log.info(f"Unzipped size mismatch for multi payload {msg}, discarding")

        return bytearray(decompressed)

    @register(EMsg.Multi)
    def handle_multi(self, msg: CMsgMulti) -> None:
        log.debug("Received a multi")
        data: bytearray = self.unpack_multi(msg) if msg.size_unzipped else msg.message_body  # type: ignore

        while data:
            size = READ_U32(data)
            self.receive(data[4 : 4 + size])
            data = data[4 + size :]

    @register(EMsg.ClientLoggedOff)
    async def handle_logoff(self, msg: login.CMsgClientLoggedOff):
        await self.handle_close()

    @property
    def next_job_id(self) -> int:
        self._current_job_id = (self._current_job_id + 1) % 10000 or 1
        return self._current_job_id

    async def send_um(self, um: UnifiedMessage) -> int:
        um.header.job_id_source = job_id = self.next_job_id
        await self.send_proto(um)
        return job_id

    # desperately needs TypeVar defaults
    async def send_um_and_wait(
        self,
        um: UnifiedMessage,
        check: Callable[[UnifiedMsgT], bool] = MISSING,
    ) -> UnifiedMsgT:
        job_id = await self.send_um(um)
        check = check or (lambda um: um.header.job_id_target == job_id)
        return await self.wait_for(emsg=EMsg.ServiceMethodSendToClient, check=check)

    # TypeVar defaults would be nice here too
    @overload
    async def send_proto_and_wait(self, msg: Message, check: Callable[[MsgT], bool] = ...) -> MsgT:
        ...

    @overload
    async def send_proto_and_wait(self, msg: ProtobufMessage, check: Callable[[ProtoMsgT], bool] = ...) -> ProtoMsgT:
        ...

    async def send_proto_and_wait(self, msg: ProtoMsgs, check: Callable[[ProtoMsgsT], bool] = MISSING) -> ProtoMsgsT:
        msg.header.job_id_source = job_id = self.next_job_id
        future = self.wait_for(emsg=None, check=check or (lambda msg: msg.header.job_id_target == job_id))
        await self.send_proto(msg)
        return await future

    async def change_presence(
        self,
        *,
        apps: list[client_server.CMsgClientGamesPlayedGamePlayed] | None = None,
        state: PersonaState | None = None,
        flags: PersonaStateFlag | None = None,
        ui_mode: UIMode | None = None,
        force_kick: bool = False,
    ) -> None:
        self._state._apps = apps or self._state._apps
        self._state._state = state or self._state._state
        self._state._ui_mode = ui_mode or self._state._ui_mode
        self._state._flags = flags or self._state._flags
        self._state._force_kick = force_kick

        if force_kick:
            log.debug("Kicking any currently playing sessions")
            await self.send_proto(client_server_2.CMsgClientKickPlayingSession())
        if apps:
            apps_msg = client_server.CMsgClientGamesPlayed(games_played=apps)
            log.debug("Sending %r to change activity", apps_msg)
            await self.send_proto(apps_msg)
        if state is not None or flags is not None:
            state_msg = friends.CMsgClientChangeStatus(
                persona_state=state or self._state._state, persona_state_flags=flags or self._state._flags
            )  # TODO what does need_persona_response do?
            log.debug("Sending %r to change state", state_msg)
            await self.send_proto(state_msg)
        if ui_mode is not None:
            ui_mode_msg = client_server_2.CMsgClientUiMode(uimode=ui_mode)
            log.debug("Sending %r to change UI mode", ui_mode_msg)
            await self.send_proto(ui_mode_msg)

    async def fetch_users(self, user_id64s: Iterable[int]) -> list[friends.CMsgClientPersonaStateFriend]:
        futs: list[asyncio.Future[friends.CMsgClientPersonaState]] = []
        users: list[friends.CMsgClientPersonaStateFriend] = []
        user_id64s = tuple(user_id64s)

        def callback(msg: friends.CMsgClientPersonaState) -> bool:
            nonlocal user_id64_chunk
            for friend in msg.friends:
                try:
                    user_id64_chunk.remove(friend.friendid)
                    return True
                except ValueError:
                    pass
            return False

        for user_id64_chunk in utils.as_chunks(user_id64s, 100):
            futs.extend(self.wait_for(friends.CMsgClientPersonaState, check=callback) for _ in user_id64_chunk)
            await self.send_proto(
                friends.CMsgClientRequestFriendData(
                    # enum EClientPersonaStateFlag {
                    #     Status = 1;
                    #     PlayerName = 2;
                    #     QueryPort = 4;
                    #     SourceID = 8;
                    #     Presence = 16;
                    #     LastSeen = 64;
                    #     UserClanRank = 128;
                    #     ExtraInfo = 256;
                    #     DataBlob = 512;
                    #     ClanData = 1024;
                    #     Facebook = 2048;
                    #     RichPresence = 4096;
                    #     Broadcast = 8192;
                    #     Watching = 16384;
                    # };
                    persona_state_requested=0b1111111011111,  # all except watching and broadcast (for now)
                    friends=user_id64_chunk,
                ),
            )

        for msg in await asyncio.wait_for(asyncio.gather(*futs), timeout=60):
            if msg.result not in (Result.OK, Result.Invalid):  # not sure if checking this is even useful
                raise WSException(msg)

            users += [user for user in msg.friends if user.friendid in user_id64s]

        return users
