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
and
https://github.com/ValvePython/steam/blob/master/steam/core/cm.py
"""

import asyncio
import binascii
import concurrent.futures
import logging
import random
import socket
import struct
import threading
import time
from gzip import GzipFile
from io import BytesIO

import websockets

from . import utils
from .enums import EResult, EUniverse
from .errors import SteamException
from .models import URL
from .protobufs import Msg, MsgProto, EMsg
from .user import SteamID

log = logging.getLogger(__name__)


class ResumeSocket(SteamException):
    def __init__(self, server):
        self.server = server


class KeepAliveHandler(threading.Thread):  # Ping commands are cool
    def __init__(self, *args, **kwargs):

        ws = kwargs.get('ws')
        interval = kwargs.get('interval')

        threading.Thread.__init__(self, *args, **kwargs)

        self.ws = ws
        self.interval = interval
        self.heartbeat = MsgProto(EMsg.ClientHeartBeat)
        self.heartbeat_timeout = 60
        self.msg = "Keeping websocket alive with sequence {}."
        self.block_msg = "Heartbeat blocked for more than {} seconds."
        self.behind_msg = "Can't keep up, websocket is {:.1f} behind."
        self._stop_ev = threading.Event()
        self._last_ack = time.perf_counter()
        self._last_send = time.perf_counter()
        self.latency = float('inf')

    def run(self):
        while not self._stop_ev.wait(self.interval):
            if self._last_ack + self.heartbeat_timeout < time.perf_counter():
                log.warning(f"Server {self.ws.server} has stopped responding to the gateway. Closing and restarting.")
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
                        f.result(5)
                        break
                    except concurrent.futures.TimeoutError:
                        total += 5
                        log.warning(self.block_msg.format(total))

            except Exception:
                self.stop()
            else:
                self._last_send = time.perf_counter()

            if self._last_send - time.perf_counter() > self.interval:
                self.ack()

    def stop(self):
        self._stop_ev.set()

    def ack(self):
        ack_time = time.perf_counter()
        self._last_ack = ack_time
        self.latency = ack_time - self._last_send
        if self.latency > 10:
            log.warning(self.behind_msg.format(self.latency))


class CMServerList:
    """A class to represent the severs the user can connect to."""
    GOOD = 1
    BAD = 2

    def __init__(self, state):
        self.state = state
        self.dict = dict()
        self.last_updated = 0
        self.cell_id = 0

    def __len__(self):
        return len(self.dict)

    def __iter__(self):
        if not self.dict:
            return log.error("Server list is empty.")

        good_servers = list(filter(lambda x: x[1]['quality'] == self.GOOD, self.dict.items()))

        if len(good_servers) == 0:
            log.debug("No good servers left. Resetting...")
            return self.reset_all()

        random.shuffle(good_servers)
        for server_address, _ in good_servers:
            yield server_address

    def clear(self):
        if len(self.dict):
            log.debug("List cleared.")
        self.dict.clear()

    def bootstrap_from_dns(self):
        log.debug("Attempting bootstrap via DNS")

        try:
            answer = socket.getaddrinfo("cm0.steampowered.com", 27017, socket.AF_INET, proto=socket.IPPROTO_TCP)
        except Exception as e:
            log.error(f"DNS boot-strap failed: {e}")
            return False

        servers = list(map(lambda addr: addr[4], answer))

        if servers:
            self.clear()
            self.merge_list(servers)
            return True
        else:
            log.error("DNS boot-strap cm0.steampowered.com no records resolved")
            return False

    async def fetch_servers_from_api(self, cell_id=0):
        log.debug("Attempting to fetch servers from the WebAPI")
        self.cell_id = cell_id

        try:
            resp = await self.state.http.fetch_cm_list(cell_id)
        except Exception as e:
            log.error(f'WebAPI fetch request failed with result: {repr(e)}')
            return False

        if resp['response']['result'] != 1:
            log.error(f'Fetching the CMList failed with '
                      f'Result: {resp["response"]["result"]} '
                      f'Message: {repr(resp["message"])}')
            return False

        websockets_list = resp['response']['serverlist_websockets']
        log.debug(f'Received {len(websockets_list)} servers from WebAPI')

        self.clear()
        self.cell_id = cell_id
        self.merge_list(websockets_list)

        return True

    def reset_all(self):
        log.debug('Marking all CM servers as Good.')
        for server in self.dict:
            self.mark_good(server)

    def mark_good(self, server):
        self.dict[server] = {'quality': self.GOOD, 'timestamp': time.time()}

    def mark_bad(self, server):
        log.debug(f'Marking {repr(server)} as bad.')
        self.dict[server] = {'quality': self.BAD, 'timestamp': time.time()}

    def merge_list(self, hosts):
        total = len(self.dict)

        for host in hosts:
            if host not in self.dict:
                self.mark_good(f'wss://{host}/cmsocket/')

        if len(self.dict) > total:
            log.debug(f'Added {len(self.dict) - total} new CM server addresses.')
        self.last_updated = int(time.time())


class SteamWebSocket:

    def __init__(self):
        self.loop = None
        self._state = None
        self._dispatch = None
        self.servers = None
        self.client = None

        self.ws = None
        self.server = None
        self.connected = False

        self.channel_key = None
        self.channel_hmac = None
        self.session_id = None
        self.cell_id = 0
        self._keep_alive = None
        self._recv_loop = None

        self.handlers = {
            EMsg.ChannelEncryptRequest: self.handle_encrypt_request,
            EMsg.ClientLogOnResponse: self.handle_logon,
            EMsg.ClientCMList: self.handle_cm_list,
            EMsg.Multi: self.handle_multi
        }

    def handle_cm_list(self, msg):
        log.debug("Updating CM list")

        new_servers = zip(map(utils.ip_from_int, msg.body.cm_addresses), msg.body.cm_ports)
        self.servers.clear()
        self.servers.merge_list(new_servers)
        self.servers.cell_id = self.cell_id

    @staticmethod
    def can_handle_close(code):
        return code not in {1000, 4004, 4010, 4011}

    @property
    def latency(self):
        """:class:`float`: Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds."""
        heartbeat = self._keep_alive
        return float('inf') if heartbeat is None else heartbeat.latency

    async def from_client(self, client):
        self.client = client
        self._state = client._connection
        self._dispatch = client.dispatch
        self.loop = client.loop
        self.servers = CMServerList(self._state)

        if not await self.servers.fetch_servers_from_api():
            self.servers.bootstrap_from_dns()
        for server in self.servers:
            start = time.time()
            log.info(f'Creating a websocket connection to: {server}')
            try:
                self.ws = await websockets.connect(server, loop=self.loop)
            except websockets.WebSocketException:
                diff = time.time() - start
                log.debug("Failed to connect. Trying another CM")
                self.servers.mark_bad(server)
                if diff < 5:
                    await asyncio.sleep(5 - diff)
            else:
                log.debug(f'Connected to {server}')
                resp = await self._state.http.request('GET', f'{URL.COMMUNITY}/chat/clientjstoken')
                ping = f'.........:.A.........8.................{client.username}.....{resp["token"]}'
                try:
                    await self.send(ping)
                except websockets.ConnectionClosed:
                    log.info(f'Websocket connection to {server} failed, retrying.')
                    return await self.from_client(client)
                else:
                    self._dispatch('connect')
                    self.server = server
                    self.connected = True
                    return

    async def receive(self, message):
        self._dispatch('socket_raw_receive', message)

        emsg_id, = struct.unpack_from("<I", message)
        emsg = EMsg(utils.clear_proto_bit(emsg_id))
        if emsg in self.handlers:
            return await self.handlers[emsg](emsg, message)

        if not self.connected and emsg != EMsg.ClientLogOnResponse:
            return log.debug(f"Dropped unexpected message: {repr(emsg)} (is_proto: {utils.is_proto(emsg_id)})")

        if emsg in (EMsg.ChannelEncryptRequest, EMsg.ChannelEncryptResponse):
            msg = Msg(emsg, message, parse=False)
        else:
            try:
                if utils.is_proto(emsg_id):
                    msg = MsgProto(emsg, message, parse=False)
                else:
                    msg = Msg(emsg, message, extended=True, parse=False)
            except Exception as e:
                log.fatal(f"Failed to deserialize message: {repr(emsg)} (is_proto: {utils.is_proto(emsg_id)})")
                return log.exception(e)

        log.debug(f'Socket has received {repr(msg)} from the websocket.')
        self._dispatch('socket_response', msg)
        return emsg, msg

    async def send(self, data):
        self._dispatch('socket_raw_send', data)
        await self.ws.send(data)

    async def send_as_proto(self, message):
        try:
            if self.steam_id:
                message.steamID = self.steam_id
            if self.session_id:
                message.sessionID = self.session_id

            log.debug(f'Outgoing: {repr(message)}')

            data = message.serialize()

            if self.channel_key:
                if self.channel_hmac:
                    data = utils.symmetric_encrypt_HMAC(data, self.channel_key, self.channel_hmac)
                else:
                    data = utils.symmetric_encrypt(data, self.channel_key)
            await self.send(data)
        except websockets.exceptions.ConnectionClosed as exc:
            if not self.can_handle_close(exc.code):
                raise

    async def close(self, code=1000, reason=''):
        if self._keep_alive:
            self._keep_alive.stop()
            self._recv_loop.cancel()

        await self.ws.close(code, reason)

    async def close_connection(self):
        await self.close()
        await self.ws.close_connection()

    async def handle_logon(self, emsg, message):
        msg = Msg(emsg.value, message, parse=True, extended=True)
        result = msg.body.eresult

        if result in (EResult.TryAnotherCM, EResult.ServiceUnavailable):
            raise ResumeSocket(self.server)
        elif result == EResult.OK:
            log.debug("Logon completed")

            self.steam_id = SteamID(msg.header.steamid)
            self.session_id = msg.header.client_sessionid
            self.cell_id = msg.body.cell_id

            log.debug("Heartbeat started.")

            interval = msg.body.out_of_game_heartbeat_seconds
            self._keep_alive = KeepAliveHandler(ws=self, interval=interval)
            self._keep_alive.start()
            self._dispatch('ready')
        else:
            raise ResumeSocket(self.server)

    async def poll_event(self):
        try:
            await self.ws.ensure_open()
            async for message in self.ws:
                if self.channel_key:
                    if self.channel_hmac:
                        try:
                            message = utils.symmetric_decrypt_HMAC(message, self.channel_key, self.channel_hmac)
                        except RuntimeError as e:
                            log.exception(e)
                            continue
                    else:
                        message = utils.symmetric_decrypt(message, self.channel_key)
                await self.receive(message)
        except websockets.exceptions.ConnectionClosed as exc:
            if self.can_handle_close(exc.code):
                log.info(f'Websocket closed with {exc.code} ({exc.reason}), attempting a reconnect.')
                raise ResumeSocket(self.server) from exc
            else:
                log.info(f'Websocket closed with {exc.code} ({exc.reason}), cannot reconnect.')
                raise

    async def handle_encrypt_request(self, req):
        log.debug("Securing channel")

        try:
            if req.body.protocolVersion != 1:
                raise RuntimeError('Unsupported protocol version')
            if req.body.universe != EUniverse.Public:
                raise RuntimeError('Unsupported universe')
        except RuntimeError as e:
            log.exception(e)
            await self.from_client(self.client)
            return

        resp = Msg(EMsg.ChannelEncryptResponse)

        challenge = req.body.challenge
        key, resp.body.key = utils.generate_session_key(challenge)
        resp.body.crc = binascii.crc32(resp.body.key) & 0xffffffff

        await self.send_as_proto(resp)
        self.channel_key = key
        log.debug("Channel secured")
        self.channel_hmac = key[:16]

    async def handle_multi(self, msg):
        log.debug('Multi: Unpacking')

        if msg.body.size_unzipped:
            log.debug(f'Multi: Decompressing payload ({len(msg.body.message_body)} -> {msg.body.size_unzipped})')

            data = await self.loop.run_in_executor(None, GzipFile(fileobj=BytesIO(msg.body.message_body)).read())

            if len(data) != msg.body.size_unzipped:
                log.fatal('Unzipped size mismatch')
                return
        else:
            data = msg.body.message_body

        while len(data) > 0:
            size, = struct.unpack_from("<I", data)
            await self.receive(data[4:4 + size])
            data = data[4 + size:]
