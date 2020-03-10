import logging
import time
from collections import defaultdict
from random import shuffle

import websockets

log = logging.getLogger(__name__)


class CMServerList:
    """A class to represent the severs the user can connect to."""
    GOOD = 1
    BAD = 2
    last_updated = 0
    cell_id = 0
    bad_timestamp = 300

    def __init__(self, state):
        self.state = state
        self.list = defaultdict(dict)
        state.loop.create_task(self.bootstrap_from_webapi())

    def __repr__(self):
        return f"<CMServerList {len(self)} servers>"

    def __len__(self):
        return len(self.list)

    def __iter__(self):
        if not self.list:
            return log.error("Server list is empty.")

        good_servers = list(filter(lambda x: x[1]['quality'] == self.GOOD, self.list.items()))

        if len(good_servers) == 0:
            log.debug("No good servers left. Resetting...")
            return self.reset_all()

        shuffle(good_servers)

        for server_address, meta in good_servers:
            yield server_address

    def clear(self):
        """Clears the server list"""
        if len(self.list):
            log.debug("List cleared.")
        self.list.clear()

    async def bootstrap_from_webapi(self, cell_id=0):
        log.debug("Attempting bootstrap via WebAPI")

        try:
            resp = await self.state.http.fetch_cm_list(cell_id)
        except Exception as exp:
            log.error(f'WebAPI bootstrap failed: {repr(exp)}')
            return False

        result = resp['response']['result']

        if result != 1:
            log.error(f'GetCMList failed with {repr(result)}')
            return False

        websocket_list = resp['response']['serverlist_websockets']
        log.debug(f'Received {len(websocket_list)} servers from WebAPI')

        self.clear()
        self.cell_id = cell_id
        self.merge_list(websocket_list)

        return True

    def reset_all(self):
        log.debug('Marking all CM servers as Good.')
        for server in self.list:
            self.mark_good(server)

    def mark_good(self, server):
        log.debug(f'Marking {repr(server)} as good.')
        self.list[server] = {'quality': self.GOOD, 'timestamp': time.time()}

    def mark_bad(self, server):
        log.debug(f'Marking {repr(server)} as bad.')
        self.list[server] = {'quality': self.BAD, 'timestamp': time.time()}

    def merge_list(self, hosts):
        total = len(self.list)

        for host in hosts:
            if host not in self.list:
                self.mark_good(f'wss://{host}/cmsocket')

        if len(self.list) > total:
            log.debug(f'Added {len(self.list) - total} new CM server addresses.')

        self.last_updated = int(time.time())


class State(websockets.client.WebSocketClientProtocol):
    __slots__ = ('loop', 'http', 'client', 'servers')

    def __init__(self, loop, client, http):
        super().__init__()
        self.loop = loop
        self.http = http
        self.client = client
        self.servers = CMServerList(self)

    async def connect(self):
        """ TODO make this work silly
        2. post ping
            .........:.A....
            00000001: 0108 ac80 0438 c4fa ffff 0fa8 0102 8002  .....8..........
            00000002: 0488 0202 9203 0a67 6f62 6f74 3132 3334  .......gobot1234
            00000003: 31a0 0600 ba06 3864 7942 6b58 6e45 6245  1.....8dyBkXnEbE
            00000004: 3159 4141 4141 4141 4141 4141 4141 4141  1YAAAAAAAAAAAAAA
            00000005: 4141 4141 4141 4141 7741 7633 7357 6232  AAAAAAAAwAv3sWb2
            00000006: 7034 4d34 382f 374e 3076 5a76 784a 6e    p4M48/7N0vZvxJn

            First part is wtf
            account name
            token

        3. listen time:
            https://steamcommunity-a.akamaihd.net/public/javascript/webui/steammessages.js
            https://cm2-iad1.cm.steampowered.com:27021/cmping/
        """

        account_name, token = await self.http.fetch_token()
        for server in self.servers:
            if self.servers.list[server]['quality'] == 1:
                log.debug(f'Requesting {server}')
                async with websockets.connect(server) as ws:
                    log.debug(f'Successfully connected to {server}')
                    self.client.dispatch('connect')
                    ping = f".....8.................{account_name}.....{token}"
                    await ws.send(ping)
                    async for msg in ws:
                        print(msg)
