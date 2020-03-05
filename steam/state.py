import logging

# import socket
# from collections import defaultdict
# from random import shuffle
# from time import time

# from .enums import EResult

log = logging.getLogger(__name__)

# This is still in the works I pushed it by accident oops
'''
class CMServerList(object):
    """
    Managing object for CM servers
    Comes with built in list of CM server to bootstrap a connection
    To get a server address from the list simply iterate over it
    .. code:: python
        servers = CMServerList()
        for server_addr in servers:
            pass
    The good servers are returned first, then bad ones. After failing to connect
    call :meth:`mark_bad` with the server addr. When connection succeeds break
    out of the loop.
    """

    GOOD = 1
    BAD = 2
    last_updated = 0  #: timestamp of when the list was last updated
    cell_id = 0  #: cell id of the server list
    bad_timestamp = 300  #: how long bad mark lasts in seconds

    def __init__(self, state):
        self._state = state
        self.log = logging.getLogger("CMServerList")
        self.list = defaultdict(dict)

    def __repr__(self):
        return "<CMServerList {} servers>".format(len(self))

    def __len__(self):
        return len(self.list)

    def __iter__(self):
        def cm_server_iter():
            if not self.list:
                self.log.error("Server list is empty.")
                return

            good_servers = list(filter(lambda x: x[1]['quality'] == CMServerList.GOOD,
                                       self.list.items()))

            if len(good_servers) == 0:
                self.log.debug("No good servers left. Reseting...")
                self.reset_all()
                return

            shuffle(good_servers)

            for server_addr, meta in good_servers:
                yield server_addr

        return cm_server_iter()

    def clear(self):
        """Clears the server list"""
        if len(self.list):
            log.debug("List cleared.")
        self.list.clear()

    async def bootstrap_from_webapi(self, cell_id=0):
        """
        Fetches CM server list from WebAPI and replaces the current one
        :param cell_id:
        :param cellid: cell id (0 = global)
        :type cellid: :class:`int`
        :return: booststrap success
        :rtype: :class:`bool`
        """
        self.log.debug("Attempting bootstrap via WebAPI")

        try:
            resp = await self._state.http.get_cm_list(cell_id)
        except Exception as exp:
            self.log.error("WebAPI boostrap failed: %s" % str(exp))
            return False

        result = EResult(resp['response']['result'])

        if result != EResult.OK:
            self.log.error("GetCMList failed with %s" % repr(result))
            return False

        serverlist = resp['response']['serverlist']
        self.log.debug("Recieved %d servers from WebAPI" % len(serverlist))

        def str_to_tuple(serveraddr):
            ip, port = serveraddr.split(':')
            return str(ip), int(port)

        self.clear()
        self.cell_id = cell_id
        self.merge_list(map(str_to_tuple, serverlist))

        return True

    def reset_all(self):
        """Reset status for all servers in the list"""

        self.log.debug("Marking all CMs as Good.")

        for key in self.list:
            self.mark_good(key)

    def mark_good(self, server_addr):
        """Mark server address as good
        :param server_addr: (ip, port) tuple
        :type server_addr: :class:`tuple`
        """
        self.list[server_addr].update({'quality': self.GOOD, 'timestamp': time()})

    def mark_bad(self, server_addr):
        """Mark server address as bad, when unable to connect for example
        :param server_addr: (ip, port) tuple
        :type server_addr: :class:`tuple`
        """
        self.log.debug("Marking %s as Bad." % repr(server_addr))
        self.list[server_addr].update({'quality': self.BAD, 'timestamp': time()})

    def merge_list(self, new_list):
        """Add new CM servers to the list
        :param new_list: a list of ``(ip, port)`` tuples
        :type new_list: :class:`list`
        """
        total = len(self.list)

        for ip, port in new_list:
            if (ip, port) not in self.list:
                self.mark_good((ip, port))

        if len(self.list) > total:
            self.log.debug("Added %d new CM addresses." % (len(self.list) - total))

        self.last_updated = int(time())

'''


class State:

    def __init__(self, loop, client, http):
        self.loop = loop
        self.http = http
        self.client = client
        self.request = http.request
