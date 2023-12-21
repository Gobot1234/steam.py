"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/Rapptz/discord.py/tree/master/discord/gateway.py
The appropriate license is in LICENSE
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
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from gzip import FCOMMENT, FEXTRA, FHCRC, FNAME
from ipaddress import IPv4Address
from operator import attrgetter
from types import CoroutineType
from typing import TYPE_CHECKING, Any, Final, Generic, TypeAlias, overload
from zlib import MAX_WBITS, decompress

import aiohttp
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from typing_extensions import TypeVar

from . import utils
from ._const import CLEAR_PROTO_BIT, DEFAULT_CMS, IS_PROTO, READ_U32, SET_PROTO_BIT, timeout
from .enums import *
from .errors import AuthenticatorError, HTTPException, NoCMsFound, WSException
from .id import parse_id64
from .models import return_true
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
from .types.id import ID64, AppID
from .user import AnonymousClientUser, ClientUser

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterable

    from .client import Client
    from .enums import UIMode
    from .protobufs.base import CMsgMulti
    from .state import ConnectionState
    from .types.http import Coro, IPAdress


__all__ = (
    "ConnectionClosed",
    "SteamWebSocket",
    "CMServer",
    "Msgs",
    "RAISED_EXCEPTIONS",
)

log = logging.getLogger(__name__)
ProtoMsgs: TypeAlias = ProtobufMessage | Message
GCMsgs: TypeAlias = GCProtobufMessage | GCMessage

GCMsgsT = TypeVar("GCMsgsT", bound=GCMsgs, default=GCMsgs)
ProtoMsgsT = TypeVar("ProtoMsgsT", bound=ProtoMsgs, default=ProtoMsgs)

Msgs: TypeAlias = ProtoMsgs | GCMsgs
MsgsT = TypeVar("MsgsT", bound=Msgs, default=Msgs)

ProtoMsgT = TypeVar("ProtoMsgT", bound=ProtobufMessage, default=ProtobufMessage)
UnifiedMsgT = TypeVar("UnifiedMsgT", bound=UnifiedMessage, default=UnifiedMessage)
MsgT = TypeVar("MsgT", bound=Message, default=Message)
GCMsgT = TypeVar("GCMsgT", bound=GCMessage, default=GCMessage)
GCMsgProtoT = TypeVar("GCMsgProtoT", bound=GCProtobufMessage, default=GCProtobufMessage)

PROTOCOL_VERSION: Final = 65580


@dataclass(slots=True)
class EventListener(Generic[MsgsT]):
    msg: IntEnum | None
    check: Callable[[MsgsT], bool]
    future: asyncio.Future[MsgsT]

    if not TYPE_CHECKING:
        __class_getitem__ = classmethod(lambda cls, params: cls)


@dataclass(slots=True)
class GCEventListener(EventListener[GCMsgsT]):
    app_id: AppID


@dataclass(slots=True)
class CMServer:
    _state: ConnectionState
    url: str
    weighted_load: float

    def connect(self) -> Coro[aiohttp.ClientWebSocketResponse]:
        return self._state.http.connect_to_cm(self.url)

    async def ping(self) -> float:
        try:
            async with timeout(5), self._state.http._session.get(f"https://{self.url}/cmping/") as resp:
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

    if not data["success"]:
        servers = [CMServer(state, url=cm_url, weighted_load=0) for cm_url in DEFAULT_CMS]
        random.shuffle(servers)
        log.debug("Error occurred when fetching CM server list, falling back to internal list", exc_info=True)
        for cm in servers:
            yield cm
        return

    hosts = data["serverlist"]
    log.debug("Received %d servers from WebAPI", len(hosts))
    for cm in sorted(
        (CMServer(state, url=server["endpoint"], weighted_load=server["wtd_load"]) for server in hosts),
        key=attrgetter("weighted_load"),
    ):  # they should already be sorted but oh well
        yield cm


def unpack_multi(msg: CMsgMulti) -> bytes | None:
    data = msg.message_body
    if data[:2] != b"\037\213":
        return log.info("Received a file that's not GZipped")

    position = 10

    if flag := data[3]:  # this isn't ever hit, might as well save a few nanos
        if flag & FEXTRA:
            extra_len = int.from_bytes(data[position : position + 2], "little")
            position += 2 + extra_len
        if flag & FNAME:
            while data[position:]:
                position += 1
        if flag & FCOMMENT:
            while data[position:]:
                position += 1
        if flag & FHCRC:
            position += 2

    decompressed = decompress(data[position:], wbits=-MAX_WBITS)

    if len(decompressed) != msg.size_unzipped:
        return log.info("Unzipped size mismatch for multi payload %r, discarding", msg)

    return decompressed


class ConnectionClosed(Exception):
    def __init__(self, cm: CMServer):
        self.cm = cm
        super().__init__(f"Connection to {self.cm.url}, has closed.")


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""


RAISED_EXCEPTIONS: Final = (
    OSError,
    ConnectionClosed,
    aiohttp.ClientError,
    asyncio.TimeoutError,
    HTTPException,
)


class KeepAliveHandler(threading.Thread):
    def __init__(self, ws: SteamWebSocket, interval: int, loop: asyncio.AbstractEventLoop):
        super().__init__()
        self.ws = ws
        self.loop = loop
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
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.loop)

                try:
                    f.result()
                except Exception:
                    log.exception("An error occurred while stopping the gateway. Ignoring.")
                finally:
                    return self.stop()

            log.debug(self.msg, self.heartbeat)
            if self.loop.is_closed():
                return self.stop()

            coro = self.ws.send_proto(self.heartbeat)
            f = asyncio.run_coroutine_threadsafe(coro, loop=self.loop)
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
                            frame = sys._current_frames()[self._main_thread_id]
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


class SteamWebSocket:
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
        self.gc_listeners: list[GCEventListener[Any]] = []
        self.closed = False
        self._pending_parsers = set[asyncio.Task[Any]]()

        self.session_id = 0
        self.id64 = ID64(0)
        self._current_job_id = 0
        self._gc_current_job_id = 0
        self.server_offset = timedelta()
        self.refresh_token: str
        self._access_token: str
        self.client_id: int

        self.public_ip: IPAdress
        self.connect_time: datetime

    @property
    def latency(self) -> float:
        """Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return self._keep_alive.latency

    @overload
    def wait_for(
        self, /, *, emsg: EMsg | None, check: Callable[[ProtoMsgsT], bool] = return_true
    ) -> asyncio.Future[ProtoMsgsT]:
        ...

    @overload
    def wait_for(self, msg: type[MsgT], /, *, check: Callable[[MsgT], bool] = return_true) -> asyncio.Future[MsgT]:
        ...

    @overload
    def wait_for(
        self, msg: type[ProtoMsgT], /, *, check: Callable[[ProtoMsgT], bool] = return_true
    ) -> asyncio.Future[ProtoMsgT]:
        ...

    def wait_for(
        self,
        msg: type[ProtoMsgsT] | None = None,
        /,
        *,
        emsg: EMsg | None = None,
        check: Callable[[ProtoMsgsT], bool] = return_true,
    ) -> asyncio.Future[ProtoMsgsT]:
        future: asyncio.Future[ProtoMsgsT] = asyncio.get_running_loop().create_future()
        entry = EventListener(msg=msg.MSG if msg else emsg, check=check, future=future)
        self.listeners.append(entry)
        return future

    @overload
    def gc_wait_for(
        self, /, *, emsg: IntEnum | None, app_id: AppID | None = None, check: Callable[[GCMsgsT], bool] = return_true
    ) -> asyncio.Future[GCMsgsT]:
        ...

    @overload
    def gc_wait_for(
        self, msg: type[GCMsgT], /, *, check: Callable[[GCMsgT], bool] = return_true
    ) -> asyncio.Future[GCMsgT]:
        ...

    @overload
    def gc_wait_for(
        self, msg: type[GCMsgProtoT], /, *, check: Callable[[GCMsgProtoT], bool] = return_true
    ) -> asyncio.Future[GCMsgProtoT]:
        ...

    def gc_wait_for(
        self,
        msg: type[GCMsgsT] | None = None,
        /,
        *,
        emsg: IntEnum | None = None,
        app_id: AppID | None = None,
        check: Callable[[GCMsgsT], bool] = return_true,
    ) -> asyncio.Future[GCMsgsT]:
        from ._gc import APP

        future: asyncio.Future[GCMsgsT] = asyncio.get_running_loop().create_future()
        entry: GCEventListener[GCMsgsT] = GCEventListener(
            msg=msg.MSG if msg else emsg,
            check=check,
            future=future,
            app_id=msg.APP_ID if msg else app_id or APP.get().id,
        )
        self.gc_listeners.append(entry)
        return future

    @asynccontextmanager
    async def poll(self) -> AsyncGenerator[None, None]:
        async def inner_poll():
            while True:
                await self.poll_event()

        poll_task = asyncio.create_task(inner_poll())
        poll_task.add_done_callback(self.parser_callback)

        yield

        poll_task.cancel()  # we let Client.connect handle poll_event from here on out
        try:
            await poll_task  # needed to ensure the task is cancelled and socket._waiting is removed
        except asyncio.CancelledError:
            pass

    @classmethod
    async def from_client(
        cls, client: Client, /, refresh_token: str | None = None, cm_list: AsyncGenerator[CMServer, None] | None = None
    ) -> SteamWebSocket:
        state = client._state
        cm_list = cm_list or fetch_cm_list(state)
        async for cm in cm_list:
            log.info("Attempting to create a websocket connection to %s (load: %f)", cm.url, cm.weighted_load)
            try:
                socket = await cm.connect()
            except aiohttp.ClientError:
                continue

            log.debug("Connected to %s", cm.url)

            self = cls(state, socket, cm_list, cm)
            client.ws = self
            self._dispatch("connect")

            async with self.poll():
                await self.send_proto(login.CMsgClientHello(PROTOCOL_VERSION))

                self.refresh_token = refresh_token or await self.fetch_refresh_token()
                self.id64 = parse_id64(utils.decode_jwt(self.refresh_token)["sub"])

                msg: login.CMsgClientLogonResponse = await self.send_proto_and_wait(
                    login.CMsgClientLogon(
                        protocol_version=PROTOCOL_VERSION,
                        client_package_version=1561159470,
                        client_os_type=16,
                        client_language=state.language.api_name,
                        supports_rate_limit_response=True,
                        chat_mode=2,
                        access_token=self.refresh_token,  # lol
                    ),
                    check=lambda msg: isinstance(msg, login.CMsgClientLogonResponse),
                )
                if msg.result != Result.OK:
                    log.debug("Failed to login with result: %r", msg.result)
                    await self._state.handle_close()

                self.public_ip = IPv4Address(msg.public_ip.v4)
                self.connect_time = utils.DateTime.now()
                self.session_id = msg.header.session_id

                us = await anext(self.fetch_users((self.id64,)))
                client.http.user = ClientUser(state, us)
                if hasattr(self._state, "_original_client_user_msg"):
                    self._state._original_client_user_msg = us  # type: ignore
                state._users[client.user.id] = client.user  # type: ignore
                self._state.cell_id = msg.cell_id

                self._keep_alive = KeepAliveHandler(
                    ws=self, interval=msg.heartbeat_seconds, loop=asyncio.get_running_loop()
                )
                self._keep_alive.start()
                log.debug("Heartbeat started.")

                state.login_complete.set()

                await self.send_um(chat.GetMyChatRoomGroupsRequest())
                await self.send_proto(friends.CMsgClientGetEmoticonList())
                await self._state.fetch_notifications()
                await self.send_proto(
                    login.CMsgClientServerTimestampRequest(client_request_timestamp=int(time.time() * 1000))
                )
                await self.change_presence(
                    apps=self._state._apps,
                    state=self._state._state,
                    flags=self._state._flags,
                    force_kick=self._state._force_kick,
                )

                self._dispatch("login")
                log.debug("Logon completed")

                return self
        raise NoCMsFound("No CMs found could be connected to. Steam is likely down")

    async def fetch_refresh_token(self) -> str:
        client = self._state.client
        assert client.username
        assert client.password
        rsa_msg: auth.GetPasswordRsaPublicKeyResponse = await self.send_um_and_wait(
            auth.GetPasswordRsaPublicKeyRequest(client.username)
        )
        if rsa_msg.result != Result.OK:
            raise WSException(rsa_msg)

        begin_resp: auth.BeginAuthSessionViaCredentialsResponse = await self.send_um_and_wait(
            auth.BeginAuthSessionViaCredentialsRequest(
                account_name=client.username,
                encrypted_password=base64.b64encode(
                    rsa.RSAPublicNumbers(int(rsa_msg.publickey_exp, 16), int(rsa_msg.publickey_mod, 16))
                    .public_key()
                    .encrypt(client.password.encode(), padding.PKCS1v15())
                ).decode(),
                encryption_timestamp=rsa_msg.timestamp,
                platform_type=auth.EAuthTokenPlatformType.SteamClient,
                persistence=auth.ESessionPersistence.Persistent,
                website_id="Client",
            )
        )

        if not begin_resp.allowed_confirmations:
            raise AuthenticatorError("No valid auth session guard type was found")

        code_task = email_code_task = asyncio.create_task(asyncio.sleep(float("inf")))
        schedule_poll = False

        for allowed_confirmation in begin_resp.allowed_confirmations:
            match allowed_confirmation.confirmation_type:
                case auth.EAuthSessionGuardType.NONE:
                    poll_resp = await self.try_poll_auth_status(begin_resp)
                    break
                case auth.EAuthSessionGuardType.DeviceCode:
                    if not client.shared_secret:
                        print("Please enter a Steam guard code")
                    code_task = asyncio.create_task(self.update_auth_with_code(begin_resp, allowed_confirmation))
                case auth.EAuthSessionGuardType.EmailCode:
                    print("Please enter a confirmation code from your email")
                    email_code_task = asyncio.create_task(self.update_auth_with_code(begin_resp, allowed_confirmation))
                case auth.EAuthSessionGuardType.DeviceConfirmation:
                    schedule_poll = True
                    print("Confirm login this on your device")
                case auth.EAuthSessionGuardType.EmailConfirmation:
                    schedule_poll = True
                    print("Confirm login this via your email")
                case auth.EAuthSessionGuardType.MachineToken:
                    raise NotImplementedError("Machine tokens are not supported yet")
                case _:
                    raise NotImplementedError(
                        f"Unknown auth session guard type: {allowed_confirmation.confirmation_type}"
                    )
        else:
            (done,), pending = await asyncio.wait(
                (
                    code_task,
                    email_code_task,
                    (
                        asyncio.create_task(self.poll_auth_status(begin_resp))
                        if schedule_poll
                        else asyncio.Future[None]()
                    ),
                ),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            poll_resp = await done
            assert poll_resp is not None

        self.client_id = poll_resp.new_client_id or begin_resp.client_id
        self._access_token = poll_resp.access_token
        return poll_resp.refresh_token

    async def update_auth_with_code(
        self,
        begin_resp: auth.BeginAuthSessionViaCredentialsResponse,
        allowed_confirmation: auth.AllowedConfirmation,
    ) -> auth.PollAuthSessionStatusResponse:
        type = allowed_confirmation.confirmation_type
        count = 0
        while True:
            code = await self._state.client.code()
            try:
                code_msg: auth.UpdateAuthSessionWithSteamGuardCodeResponse = await self.send_proto_and_wait(
                    auth.UpdateAuthSessionWithSteamGuardCodeRequest(
                        client_id=begin_resp.client_id,
                        steamid=begin_resp.steamid,
                        code=code,
                        code_type=type,
                    )
                )
            except ConnectionClosed:
                continue
            if code_msg.result == Result.TwoFactorCodeMismatch:
                count += 1
                if count > 3:
                    exc = WSException(code_msg)
                    if sys.version_info >= (3, 11):
                        msg = (
                            "Your clock is out of sync with the Steam servers or your shared secret is incorrect"
                            if self._state.client.shared_secret is not None
                            else "Your clock is likely out of sync with the Steam servers"
                        )
                        exc.add_note(msg)
                    raise exc
                if self._state.client.shared_secret is not None:
                    await asyncio.sleep(2)
                continue
            elif code_msg.result != Result.OK:
                raise WSException(code_msg)
            return await self.poll_auth_status(begin_resp)

    async def poll_auth_status(
        self, begin_resp: auth.BeginAuthSessionViaCredentialsResponse
    ) -> auth.PollAuthSessionStatusResponse:
        while True:
            resp = await self.try_poll_auth_status(begin_resp)
            if resp.refresh_token:
                return resp
            await asyncio.sleep(begin_resp.interval)

    async def try_poll_auth_status(
        self, begin_resp: auth.BeginAuthSessionViaCredentialsResponse
    ) -> auth.PollAuthSessionStatusResponse:
        poll_resp: auth.PollAuthSessionStatusResponse = await self.send_um_and_wait(
            auth.PollAuthSessionStatusRequest(
                client_id=begin_resp.client_id,
                request_id=begin_resp.request_id,
            )
        )
        if poll_resp.result != Result.OK:
            raise WSException(poll_resp)
        return poll_resp

    @utils.call_once(wait=True)
    async def access_token(self) -> str:
        try:
            return self._access_token
        except AttributeError:
            msg: auth.GenerateAccessTokenForAppResponse = await self.send_um_and_wait(
                auth.GenerateAccessTokenForAppRequest(self.refresh_token, self.id64)
            )
            if msg.result != Result.OK:
                raise WSException(msg) from None
            self._access_token = msg.access_token
            return msg.access_token

    @classmethod
    async def anonymous_login_from_client(
        cls, client: Client, cm_list: AsyncGenerator[CMServer, None] | None = None
    ) -> SteamWebSocket:
        state = client._state
        cm_list = cm_list or fetch_cm_list(state)
        async for cm in cm_list:
            log.info("Attempting to create a websocket connection to %s (load: %f)", cm.url, cm.weighted_load)
            socket = await cm.connect()
            log.debug("Connected to %s", cm.url)

            self = cls(state, socket, cm_list, cm)
            client.ws = self
            self._dispatch("connect")

            self.id64 = parse_id64(0, type=Type.AnonUser, universe=Universe.Public)

            async with self.poll():
                msg: login.CMsgClientLogonResponse = await self.send_proto_and_wait(
                    login.CMsgClientLogon(
                        protocol_version=PROTOCOL_VERSION,
                        client_package_version=1561159470,
                        client_language=state.language.api_name,
                    ),
                    check=lambda msg: isinstance(msg, login.CMsgClientLogonResponse),
                )
                if msg.result != Result.OK:
                    log.debug("Failed to login with result: %r", msg.result)
                    await self._state.handle_close()

                self.session_id = msg.header.session_id
                self.id64 = msg.header.steam_id
                self._state.cell_id = msg.cell_id

                self._keep_alive = KeepAliveHandler(
                    ws=self, interval=msg.heartbeat_seconds, loop=asyncio.get_running_loop()
                )
                self._keep_alive.start()
                log.debug("Heartbeat started.")

                state.login_complete.set()
                state.http.user = AnonymousClientUser(state, self.id64)  # type: ignore

                await self.send_proto(
                    login.CMsgClientServerTimestampRequest(client_request_timestamp=int(time.time() * 1000))
                )

                self._dispatch("login")
                log.debug("Logon completed")

            await client._handle_ready()
            return self
        raise NoCMsFound("No CMs found could be connected to. Steam is likely down")

    async def poll_event(self) -> None:
        try:
            message = await self.socket.receive()
            if message.type is aiohttp.WSMsgType.BINARY:  # type: ignore
                return self.receive(message.data)  # type: ignore
            if message.type is aiohttp.WSMsgType.ERROR:  # type: ignore
                log.debug("Received %r", message)
                raise message.data  # type: ignore
            if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING):  # type: ignore
                log.debug("Received %r", message)
                raise WebSocketClosure
            log.debug("Dropped unexpected message type: %r", message)
        except WebSocketClosure:
            await self._state.handle_close()

    def parser_callback(self, task: asyncio.Task[Any], /) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            pass
        else:
            if isinstance(exc, RAISED_EXCEPTIONS) and not self._state._task_error.done():
                self._state._task_error.set_exception(exc)
        self._pending_parsers.discard(task)

    def receive(self, message: bytes, /) -> None:
        emsg_value = READ_U32(message)
        try:
            msg = (
                ProtobufMessage().parse(message[4:], CLEAR_PROTO_BIT(emsg_value))
                if IS_PROTO(emsg_value)
                else Message().parse(message[4:], emsg_value)
            )
        except Exception as exc:
            return log.error(
                "Failed to deserialize message: %r, %r", EMsg(CLEAR_PROTO_BIT(emsg_value)), message, exc_info=exc
            )

        log.debug("Socket has received %r from the websocket.", msg)

        if hasattr(self, "_keep_alive"):
            self._keep_alive.tick()

        try:
            event_parser = self._state.parsers[msg.MSG]
        except (KeyError, TypeError):
            log.debug("Ignoring %r, no event handler", msg)
        else:
            try:
                result = event_parser(self._state, msg)
            except Exception:
                return traceback.print_exc()

            if isinstance(result, CoroutineType):
                task = asyncio.create_task(result, name=f"steam.py: {event_parser.__name__}")
                self._pending_parsers.add(task)
                task.add_done_callback(self.parser_callback)
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

    async def send(self, data: bytes, /) -> None:
        try:
            await self.socket.send_bytes(data)
        except ConnectionResetError:
            await self._state.handle_close()

    async def send_proto(self, message: ProtoMsgs, /) -> None:
        message.header.steam_id = self.id64
        message.header.session_id = self.session_id

        await self.send(bytes(message))

    async def send_gc_message(self, msg: GCMsgs, /) -> int:  # for ext's to send GC messages
        app_id = msg.APP_ID
        message = client_server_2.CMsgGcClientToGC(
            appid=app_id,
            msgtype=SET_PROTO_BIT(msg.MSG) if isinstance(msg, GCProtobufMessage) else msg.MSG,
            payload=bytes(msg),
        )
        message.header.routing_app_id = app_id
        message.header.job_id_source = self.next_gc_job_id

        log.debug("Sending GC message %r", msg)
        await self.send_proto(message)
        return message.header.job_id_source

    async def close(self, code: int = 1000) -> None:
        message = login.CMsgClientLogOff()
        message.header.steam_id = self.id64
        message.header.session_id = self.session_id
        await self.socket.close(code=code, message=bytes(message))

    @property
    def next_job_id(self) -> int:
        self._current_job_id = (self._current_job_id + 1) % 10000 or 1
        return self._current_job_id

    @property
    def next_gc_job_id(self) -> int:
        self._gc_current_job_id = (self._gc_current_job_id + 1) % 10000 or 1
        return self._gc_current_job_id

    async def send_um(self, um: UnifiedMessage, /) -> int:
        um.header.job_id_source = job_id = self.next_job_id
        await self.send_proto(um)
        return job_id

    async def send_um_and_wait(
        self,
        um: UnifiedMessage,
        /,
        check: Callable[[UnifiedMsgT], bool] | None = None,
    ) -> UnifiedMsgT:
        um.header.job_id_source = job_id = self.next_job_id
        check = check if check is not None else (lambda um: um.header.job_id_target == job_id)
        future = self.wait_for(emsg=EMsg.ServiceMethodSendToClient, check=check)
        await self.send_proto(um)
        return await future

    async def send_proto_and_wait(
        self, msg: ProtoMsgs, /, check: Callable[[ProtoMsgsT], bool] | None = None
    ) -> ProtoMsgsT:
        msg.header.job_id_source = job_id = self.next_job_id
        future = self.wait_for(
            emsg=None, check=check if check is not None else (lambda msg: msg.header.job_id_target == job_id)
        )
        await self.send_proto(msg)
        return await future

    async def send_gc_message_and_wait(
        self, msg: GCMsgs, /, check: Callable[[GCMsgProtoT], bool] | None = None
    ) -> GCMsgProtoT:
        msg.header.job_id_source = job_id = self.next_gc_job_id
        future = self.gc_wait_for(
            emsg=None,
            app_id=msg.APP_ID,
            check=check if check is not None else (lambda msg: msg.header.job_id_target == job_id),
        )
        await self.send_gc_message(msg)
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
        if apps is not None:
            apps_msg = client_server.CMsgClientGamesPlayed(games_played=apps)
            log.debug("Sending %r to change activity", apps_msg)
            await self.send_proto(apps_msg)
        if state is not None or flags is not None:
            state_msg = friends.CMsgClientChangeStatus(
                persona_state=state or self._state._state, persona_state_flags=flags or self._state._flags
            )
            log.debug("Sending %r to change state", state_msg)
            await self.send_proto(state_msg)
        if ui_mode is not None:
            ui_mode_msg = client_server_2.CMsgClientUiMode(uimode=ui_mode)
            log.debug("Sending %r to change UI mode", ui_mode_msg)
            await self.send_proto(ui_mode_msg)

    async def fetch_users(
        self, user_id64s: Iterable[ID64]
    ) -> AsyncGenerator[friends.CMsgClientPersonaStateFriend, None]:
        futs: list[asyncio.Future[friends.CMsgClientPersonaState]] = []
        user_id64s = dict.fromkeys(user_id64s)

        def callback(msg: friends.CMsgClientPersonaState, user_id64: ID64) -> bool:
            return any(friend.friendid == user_id64 for friend in msg.friends)

        for user_id64_chunk in utils.as_chunks(user_id64s, 100):
            futs += [
                self.wait_for(friends.CMsgClientPersonaState, check=partial(callback, user_id64=user_id64))
                for user_id64 in user_id64_chunk
            ]
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
                    friends=list(user_id64_chunk),
                ),
            )

        for msg in await asyncio.wait_for(asyncio.gather(*futs), timeout=60):
            if msg.result not in (Result.OK, Result.Invalid):  # not sure if checking this is even useful
                raise WSException(msg)

            for user in msg.friends:
                if user.friendid in user_id64s:
                    yield user
