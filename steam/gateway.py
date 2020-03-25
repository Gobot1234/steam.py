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
import logging
import struct
import time
from collections import defaultdict

import websockets

from . import utils
from .enums import EResult, EUniverse
from .errors import SteamException
from .protobufs import Msg, MsgProto, EMsg
from .user import SteamID

log = logging.getLogger(__name__)


class ResumeSocket(SteamException):
    def __init__(self, server):
        self.server = server


class CMServerList:
    """A class to represent the severs the user can connect to."""
    GOOD = 1
    BAD = 2

    def __init__(self, state):
        self.state = state
        self.dict = defaultdict(dict)
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

        for server_address, _ in good_servers:
            yield server_address

    def clear(self):
        """Clears the server list"""
        if len(self.dict):
            log.debug("List cleared.")
        self.dict.clear()

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

        websocket_list = resp['response']['serverlist_websockets']
        log.debug(f'Received {len(websocket_list)} servers from WebAPI')

        self.clear()
        self.merge_list(websocket_list)

        return True

    def reset_all(self):
        log.debug('Marking all CM servers as Good.')
        for server in self.dict:
            self.mark_good(server)

    def mark_good(self, server):
        log.debug(f'Marking {repr(server)} as good.')
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


class SteamWebsocket(websockets.client.WebSocketClientProtocol):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dispatch = lambda *args: None
        self.ws = None
        self.client = None
        self.servers = None
        self.state = None
        self.session = None

        self.servers = None
        self.server = None
        self.connected = False
        self._seen_logon = False

        self.auto_discovery = True  #: enables automatic CM discovery

        self.channel_secured = False  #: :class:`True` once secure channel handshake is complete
        self.channel_key = None  #: channel encryption key
        self.channel_hmac = None  #: HMAC secret

        self.session_id = None  #: session id when logged in
        self.cell_id = 0  #: cell id provided by CM

        self._recv_loop = None
        self._heartbeat_loop = None
        self.handlers = {
            EMsg.ChannelEncryptRequest: self.handle_encrypt_request,
            EMsg.ClientLogOnResponse: self.handle_logon,
            EMsg.ClientCMList: self.handle_cm_list
        }

    async def send_heartbeat(self, interval):
        message = MsgProto(EMsg.ClientHeartBeat)

        while 1:
            await asyncio.sleep(interval)
            await self.send(message)

    def handle_cm_list(self, msg):
        log.debug("Updating CM list")

        new_servers = zip(map(utils.ip_from_int, msg.body.cm_addresses), msg.body.cm_ports)
        self.servers.clear()
        self.servers.merge_list(new_servers)
        self.servers.cell_id = self.cell_id

    @staticmethod
    def can_handle_close(code):
        return code not in (1000, 4004, 4010, 4011)

    async def from_client(self, client, *, fetch=False):
        self.client = client
        self.state = client._connection
        if fetch:
            self.servers = CMServerList(self.state)
            await self.servers.fetch_servers_from_api()
        log.debug("Connect initiated.")

        for server in self.servers:
            if self.servers.dict[server]['quality'] == 1:
                start = time.time()
                log.info(f'Creating a websocket connection to: {server}')
                try:
                    self.ws = await websockets.connect(server)
                except websockets.WebSocketException:
                    diff = time.time() - start
                    log.debug("Failed to connect. Trying another CM")
                    self.servers.mark_bad(server)
                    if diff < 5:
                        await asyncio.sleep(5 - diff)
                else:
                    log.debug(f'Connected to {server}')
                    try:
                        await self.ws.ensure_open()
                    except websockets.ConnectionClosed:
                        log.info(f'Websocket connection to {self.server} failed, retrying.')
                        return await self.from_client(client)
                    else:
                        self._dispatch = client.dispatch
                        self._dispatch('connect')
                        self.server = server
                        self.connected = True
                        return self

    async def receive(self, message):
        self._dispatch('socket_raw_receive', message)

        emsg_id, = struct.unpack_from("<I", message)
        emsg = EMsg(utils.clear_proto_bit(emsg_id))
        if emsg in self.handlers:
            await self.handlers[emsg]()

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

    async def send(self, message):
        self._dispatch('socket_raw_send', message)

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

        await super().send(data)

    async def close(self, code=1000, reason=''):
        if self._heartbeat_loop:
            self._heartbeat_loop.cancel()
            self._recv_loop.cancel()

        for name in [
            'connected', 'channel_secured',
            'channel_key', 'channel_hmac',
            'steam_id', 'session_id',
            '_seen_logon', '_recv_loop',
            '_heartbeat_loop']:
            self.__dict__.pop(name, None)
        await super().close(code, reason)

    async def close_connection(self):
        await self.close()
        await super().close_connection()

    async def handle_logon(self, msg):
        result = msg.body.eresult

        if result in (EResult.TryAnotherCM, EResult.ServiceUnavailable):
            raise ResumeSocket(self.server)
        elif result == EResult.OK:
            self._seen_logon = True

            log.debug("Logon completed")

            self.steam_id = SteamID(msg.header.steamid)
            self.session_id = msg.header.client_sessionid
            self.cell_id = msg.body.cell_id

            if self._heartbeat_loop:
                self._heartbeat_loop.cancel()

            log.debug("Heartbeat started.")

            interval = msg.body.out_of_game_heartbeat_seconds
            self._heartbeat_loop = self.state.loop.create_task(self.send_heartbeat(interval))
            self._dispatch('ready')
        else:
            raise ResumeSocket(self.server)

    async def poll_event(self):
        try:
            await self.ensure_open()
            async for message in self.ws:
                print(message)
                if self.channel_key:
                    if self.channel_hmac:
                        try:
                            message = utils.symmetric_decrypt_HMAC(message, self.channel_key, self.channel_hmac)
                        except RuntimeError as e:
                            log.exception(e)
                            break
                    else:
                        message = utils.symmetric_decrypt(message, self.channel_key)

                await self.receive(message)
        except websockets.exceptions.ConnectionClosed as exc:
            if self.can_handle_close(exc.code):
                log.info(f'Websocket closed with {exc.code} ({exc.reason}), attempting a reconnect.')
                raise ResumeSocket(self.server) from exc
            else:
                log.info(f'Websocket closed with {exc.code} ({exc.reason}), cannot reconnect.')
                raise websockets.ConnectionClosed(exc.code, exc.reason) from exc

    async def handle_encrypt_request(self, req):
        log.debug("Securing channel")

        try:
            if req.body.protocolVersion != 1:
                raise RuntimeError("Unsupported protocol version")
            if req.body.universe != EUniverse.Public:
                raise RuntimeError("Unsupported universe")
        except RuntimeError as e:
            log.exception(e)
            await self.from_client(self.client)
            return

        resp = Msg(EMsg.ChannelEncryptResponse)

        challenge = req.body.challenge
        key, resp.body.key = utils.generate_session_key(challenge)
        resp.body.crc = binascii.crc32(resp.body.key) & 0xffffffff

        await self.send(resp)
        self.channel_key = key
        log.debug("Channel secured")
        self.channel_hmac = key[:16]
        self.channel_secured = True
