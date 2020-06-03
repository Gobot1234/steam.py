# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
Copyright (c) 2015-2020 Rapptz
Copyright (c) 2020 Gobot1234

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

This is a modified version of
https://github.com/Rapptz/discord.py/blob/master/discord/gateway.py
and https://github.com/ValvePython/steam/blob/master/steam/core/cm.py
"""

import asyncio
import binascii
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
from typing import TYPE_CHECKING, List, Optional, Union

import aiohttp

from . import utils
from .abc import SteamID
from .enums import EResult, EUniverse
from .errors import NoCMsFound
from .protobufs import EMsg, Msg, MsgProto, get_um

if TYPE_CHECKING:
    from .client import Client
    from .state import ConnectionState


__all__ = (
    'SteamWebSocket',
    'ConnectionClosed',
    'WebSocketClosure',
    'ReconnectWebSocket',
)

log = logging.getLogger(__name__)


class ReconnectWebSocket(Exception):
    """Signals to safely reconnect the websocket."""

    def __init__(self, cm: str, *, resume: bool = True):
        self.cm = cm
        self.resume = resume


class ConnectionClosed(Exception):
    def __init__(self, socket: aiohttp.ClientWebSocketResponse, cm: str, cms: 'CMServerList'):
        self.code = socket.close_code
        # aiohttp doesn't seem to consistently provide close reason
        self.reason = ''
        self.cm = cm
        self.cm_list = cms
        super().__init__(f'Connection to {self.cm}, has closed with code: {self.code}')


class WebSocketClosure(Exception):
    """An exception to make up for the fact that aiohttp doesn't signal closure."""
    pass


class CMServerList:
    """A class to represent the severs the user can connect to."""
    GOOD = 1
    BAD = 2

    def __init__(self, state: 'ConnectionState', first_cm_to_try: str):
        self.state = state
        self.dict = dict()
        self.last_updated = 0
        self.cell_id = 0
        self._current_iteration = 0
        self.queue = asyncio.Queue()
        if first_cm_to_try is not None:
            self.queue.put_nowait(first_cm_to_try)

    def __len__(self):
        return len(self.dict)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if self.queue.qsize() in (0, 1):
            self._current_iteration += 1
            if self._current_iteration == 2:
                raise StopAsyncIteration
            await self.fill()
        return self.queue.get_nowait()

    async def fill(self) -> None:
        if not await self.fetch_servers_from_api():  # TODO bootstrap from internal list?
            raise NoCMsFound('No Community Managers could be found to connect to')

        good_servers = list(filter(lambda x: x[1]['quality'] == self.GOOD, self.dict.items()))

        if len(good_servers) == 0:
            log.debug('No good servers left. Resetting...')
            self.reset_all()
            return

        ordered = sorted(good_servers, key=lambda x: x[1]['score'])
        if ordered[0][1]['score'] == 0:  # check if CMs have been pinged yet
            random.shuffle(ordered)
        for server_address, _ in ordered:
            self.queue.put_nowait(server_address)

    def clear(self) -> None:
        if self.dict:
            log.debug('List cleared.')
        self.dict.clear()

    async def fetch_servers_from_api(self, cell_id: int = 0) -> bool:
        log.debug("Attempting to fetch servers from the WebAPI")
        self.cell_id = cell_id
        try:
            resp = await self.state.http.get_cm_list(cell_id)
        except Exception as e:
            log.error(f'WebAPI fetch request failed with result: {repr(e)}')
            return False
        if resp['response']['result'] != EResult.OK:
            log.error(f'Fetching the CMList failed with '
                      f'Result: {EResult(resp["response"]["result"])} '
                      f'Message: {repr(resp["response"]["message"])}')
            return False

        websockets_list = resp['response']['serverlist_websockets']
        log.debug(f'Received {len(websockets_list)} servers from WebAPI')

        self.clear()
        self.cell_id = cell_id
        self.merge_list(websockets_list)

        # this way we can have the benefits of not connecting
        # to borked cms whilst maintaining initial speed
        self.state.loop.create_task(self.ping_cms())

        return True

    def reset_all(self) -> None:
        log.debug('Marking all CM servers as Good.')
        for server in self.dict:
            self.mark_good(server)

    def mark_good(self, server: str, score: float = 0) -> None:
        self.dict[server] = {"quality": self.GOOD, "timestamp": time.time(), "score": score}

    def mark_bad(self, server: str) -> None:
        self.dict[server] = {"quality": self.BAD, "timestamp": time.time(), "score": 0}

    def merge_list(self, hosts: List[str]) -> None:
        total = len(self.dict)
        for host in hosts:
            if host not in self.dict:
                self.mark_good(f'wss://{host}/cmsocket/')
        if len(self.dict) > total:
            log.debug(f'Added {len(self.dict) - total} new CM server addresses.')
        self.last_updated = int(time.time())

    async def ping_cms(self) -> None:
        log.debug(f'Pinging {len(self.dict)} CMs')
        for host in self.dict:
            start = time.perf_counter()
            try:
                resp = await self.state.http._session.get(f'https://{host[6:-10]}/cmping', timeout=5)
                if resp.status != 200:
                    self.mark_bad(host)
                load = resp.headers['X-Steam-CMLoad']
            except (KeyError, asyncio.TimeoutError):
                self.mark_bad(host)
            else:
                latency = time.perf_counter() - start
                score = (int(load) * 2) + latency
                self.mark_good(host, score)

        log.debug('Finished pinging CMs')


class KeepAliveHandler(threading.Thread):  # ping commands are cool
    def __init__(self, *args, **kwargs):
        self.ws = kwargs.pop('ws')
        self.interval = kwargs.pop('interval')
        super().__init__(*args, **kwargs)
        self._main_thread_id = self.ws.thread_id
        self.heartbeat = MsgProto(EMsg.ClientHeartBeat)
        self.heartbeat_timeout = 60
        self.msg = "Keeping websocket alive with sequence {}."
        self.block_msg = "Heartbeat blocked for more than {} seconds."
        self.behind_msg = "Can't keep up, websocket is {:.1f} behind."
        self._stop_ev = threading.Event()
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self.latency = float('inf')

    def run(self) -> None:
        while not self._stop_ev.wait(self.interval):
            if self._last_ack + self.heartbeat_timeout < time.perf_counter():
                log.warning(f"Server {self.ws.cm} has stopped responding to the gateway. Closing and restarting.")
                coro = self.ws.close(4000)
                f = asyncio.run_coroutine_threadsafe(coro, loop=self.ws.loop)

                try:
                    f.result()
                except Exception:
                    pass
                finally:
                    self.stop()
                    return

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
                            msg = f'{self.block_msg}\n' \
                                  f'Loop thread traceback (most recent call last):\n' \
                                  f'{"".join(stack)}'
                        log.warning(msg, total)

            except Exception:
                self.stop()
            else:
                self._last_send = time.perf_counter()

            if self._last_send - time.perf_counter() > self.interval:
                self.ack()

    def stop(self) -> None:
        self._stop_ev.set()

    def ack(self) -> None:
        ack_time = time.perf_counter()
        self._last_ack = ack_time
        self.latency = ack_time - self._last_send
        if self.latency > 10:
            log.warning(self.behind_msg.format(self.latency))


class SteamWebSocket:
    def __init__(self, socket: aiohttp.ClientWebSocketResponse, *, loop: asyncio.AbstractEventLoop):
        self.socket = socket
        self.loop = loop
        self._dispatch = lambda *args: None
        self.cm = None
        self.cm_list = None
        self.connected = False
        self.channel_key = None
        self.channel_hmac = None
        self.session_id = None
        self.steam_id = None
        self.cell_id = 0
        self._current_job_id = 0
        self._keep_alive = None
        self.thread_id = threading.get_ident()

        self.handlers = {
            EMsg.Multi: self.handle_multi,
            EMsg.ClientCMList: self.handle_cm_list,
            EMsg.ClientLogOnResponse: self.handle_logon,
            EMsg.ChannelEncryptRequest: self.handle_encrypt_request,
        }

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds."""
        return self._keep_alive.latency

    @property
    def open(self) -> bool:
        return not self.socket.closed

    @classmethod
    async def from_client(cls, client: 'Client', cm: str = None,
                          cms: CMServerList = None) -> 'SteamWebSocket':
        connection = client._connection
        cm_list = cms or CMServerList(connection, cm)
        async for cm in cm_list:
            log.info(f'Creating a websocket connection to: {cm}')
            socket = await client.http.connect_to_cm(cm)
            log.debug(f'Connected to {cm}')
            payload = MsgProto(
                EMsg.ClientLogon, account_name=client.username,
                web_logon_nonce=client.token, client_os_type=4294966596,
                protocol_version=65580, chat_mode=2, ui_mode=4, qos_level=2,
            )
            payload.header.steam_id = client.user.id64

            ws = cls(socket, loop=client.loop)
            # dynamically add attributes needed
            ws._connection = connection
            # ws._parsers = connection.parsers
            ws._dispatch = client.dispatch
            ws.cm = cm
            ws.cm_list = cm_list
            ws.connected = True
            await ws.send_as_proto(payload)  # send the identification message straight away
            ws._dispatch('connect')
            return ws

    async def poll_event(self) -> None:
        try:
            message = await self.socket.receive()
            if message.type is aiohttp.WSMsgType.ERROR:
                log.debug(f'Received {message}')
                raise message.data
            if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                log.debug(f'Received {message}')
                raise WebSocketClosure

            message = message.data
            if self.channel_key:
                if self.channel_hmac:
                    try:
                        message = utils.symmetric_decrypt_HMAC(message.data, self.channel_key, self.channel_hmac)
                    except RuntimeError as e:
                        return log.exception(e)
                else:
                    message = utils.symmetric_decrypt(message.data, self.channel_key)
            await self.receive(message)
        except WebSocketClosure:
            self.handle_close()

    async def receive(self, message: bytes) -> None:
        self._dispatch('socket_raw_receive', message)

        emsg_value, = struct.unpack_from("<I", message)
        emsg = EMsg(utils.clear_proto_bit(emsg_value))
        if emsg in self.handlers:
            return await self.handlers[emsg](emsg, message)

        if not self.connected:
            return log.debug(f"Dropped unexpected message: {repr(emsg)}")
        if emsg in (EMsg.ChannelEncryptRequest, EMsg.ChannelEncryptResponse):
            msg = Msg(emsg, message)
        else:
            try:
                if utils.is_proto(emsg_value):
                    msg = MsgProto(emsg, message)
                else:
                    msg = Msg(emsg, message, extended=True)
            except Exception as e:
                log.fatal(f"Failed to deserialize message: {repr(emsg)}")
                return log.exception(e)

        log.debug(f'Socket has received {repr(msg)} from the websocket.')
        self._dispatch('socket_receive', msg)

    async def send(self, data: bytes) -> None:
        self._dispatch('socket_raw_send', data)
        await self.socket.send_bytes(data=data)

    async def send_as_proto(self, message: Union[MsgProto, Msg]) -> None:
        if self.steam_id:
            message.steam_id = self.steam_id
        if self.session_id:
            message.session_id = self.session_id

        self._dispatch('socket_send', message)
        data = message.serialize()

        if self.channel_key:
            if self.channel_hmac:
                data = utils.symmetric_encrypt_HMAC(data, self.channel_key, self.channel_hmac)
            else:
                data = utils.symmetric_encrypt(data, self.channel_key)
        await self.send(data)

    async def close(self, code: int = 4000) -> None:
        if self._keep_alive:
            self._keep_alive.stop()
        if self.connected:
            await self.send_as_proto(MsgProto(EMsg.ClientLogOff))
        await self.socket.close(code=code)

    def handle_close(self) -> None:
        if self.socket.close_code not in {1000, 4004, 4010, 4011}:
            log.info(f'Websocket closed with {self.socket.close_code}, attempting a reconnect.')
            raise ReconnectWebSocket(self.cm)
        log.info(f'Websocket closed with {self.socket.close_code}, cannot reconnect.')
        raise ConnectionClosed(self.socket, self.cm, self.cm_list)

    async def handle_logon(self, emsg: EMsg, message: bytes) -> None:
        msg = Msg(emsg, message, extended=True)
        result = msg.body.eresult

        if result == EResult.OK:
            log.debug('Logon completed')

            self.steam_id = SteamID(msg.header.steamid).id64
            self.session_id = msg.header.client_sessionid
            self.cell_id = self.cm_list.cell_id = msg.body.cell_id

            interval = msg.body.out_of_game_heartbeat_seconds
            self._keep_alive = KeepAliveHandler(ws=self, interval=interval)
            self._keep_alive.start()
            log.debug('Heartbeat started.')

            self._dispatch('ready')
        else:
            raise ConnectionClosed(self.socket, self.cm, self.cm_list)

    async def handle_encrypt_request(self, msg: MsgProto) -> None:
        log.debug("Securing channel")

        if msg.body.protocolVersion != 1:
            msg = 'Unsupported protocol version'
            log.exception(msg)
            raise RuntimeError(msg)
        if msg.body.universe != EUniverse.Public:
            msg = 'Unsupported universe'
            log.exception(msg)
            raise RuntimeError(msg)

        challenge = msg.body.challenge
        key, body_key = utils.generate_session_key(challenge)
        resp = Msg(
            EMsg.ChannelEncryptResponse, key=body_key,
            crc=binascii.crc32(msg.body.key) & 0xffffffff
        )
        await self.send_as_proto(resp)
        self.channel_key = key
        self.channel_hmac = key[:16]
        log.debug('Channel secured')

    async def handle_multi(self, msg: MsgProto) -> None:
        log.debug('Recieved a multi, unpacking')

        if msg.body.size_unzipped:
            log.debug(f'Multi: Decompressing payload ({len(msg.body.message_body)} -> {msg.body.size_unzipped})')
            data = await self.loop.run_in_executor(None, GzipFile(BytesIO(msg.body.message_body)).read)
            if len(data) != msg.body.size_unzipped:
                return log.info(f'Unzipped size mismatch for multi payload {msg}, discarding')
        else:
            data = msg.body.message_body

        while len(data) > 0:
            size = struct.unpack_from("<I", data)[0]
            await self.receive(data[4:4 + size])
            data = data[4 + size:]

    def handle_cm_list(self, msg: MsgProto) -> None:
        log.debug("Updating CM list")
        self.cm_list.clear()
        self.cm_list.merge_list(msg.body.cm_websocket_addresses)
        self.cm_list.cell_id = self.cell_id

    async def send_um(self, name: str, params: Optional[dict] = None) -> None:
        proto = get_um(name)
        if proto is None:
            raise ValueError(f'Failed to find method named: {name}')

        message = MsgProto(EMsg.ServiceMethodCallFromClient, **params)
        message.header.target_job_name = name
        message.header.job_id_source = self._current_job_id = ((self._current_job_id + 1) % 10000) or 1
        await self.send_as_proto(message)

    async def send_job(self, message: MsgProto, body_params: dict = None) -> None:
        job_id = self._current_job_id = ((self._current_job_id + 1) % 10000) or 1
        message.header.job_id_source = job_id
        if body_params is not None:
            message.body.from_dict(body_params)

        await self.send_as_proto(message)

    async def change_presence(self, *, games=None, status=None, ui_mode=None) -> None:
        games = [game.to_dict() for game in games]  # TODO these should already be to_dict'ed
        activity = MsgProto(EMsg.ClientGamesPlayedWithDataBlob, games_played=games)
        status = MsgProto(EMsg.ClientPersonaState, status_flags=status.value)
        ui_mode = MsgProto(EMsg.ClientCurrentUIMode, uimode=ui_mode)
        log.debug(f'Sending {activity} to change activity')
        await self.send_as_proto(activity)
        log.debug(f'Sending {status} to change status')
        await self.send_as_proto(status)
        log.debug(f'Sending {ui_mode} to change UI mode')
        await self.send_as_proto(ui_mode)
