# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

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

This contains a large amount of
https://github.com/ValvePython/steam/blob/master/steam/game_servers.py
"""

from __future__ import annotations

import asyncio
import socket
import struct
from binascii import crc32
from bz2 import decompress
from contextlib import asynccontextmanager, AbstractAsyncContextManager
from datetime import timedelta
from collections.abc import Callable
from typing import TYPE_CHECKING, NamedTuple, Optional, TypeVar, Union, Any, Generic

from typing_extensions import Literal

from .abc import SteamID
from .enums import Enum, EGameServerRegion
from .game import Game
from .utils import BytesBuffer

if TYPE_CHECKING:
    from .protobufs.steammessages_gameservers import CGameServersGetServerListResponseServer as GameServerProto

T = TypeVar("T")
Q = TypeVar("Q", bound="Query")

__all__ = (
    "Query",
    "GameServer",
    "ServerPlayer",
)


# fmt: off
class Operator(Enum):
    div  = "\\"
    or_  = "nor"
    and_ = "nand"
# fmt: on


class QueryAll:
    def __truediv__(self, other):
        raise NotImplementedError("Query.all does not support operations")

    def __or__(self, other):
        raise NotImplementedError("Query.all does not support operations")

    def __and__(self, other):
        raise NotImplementedError("Query.all does not support operations")

    query = ""


class QueryMeta(type):
    @property
    def not_empty(cls) -> Query[Q]:
        """Fetches servers that are not empty."""
        return Query(r"empty\1")

    @property
    def empty(cls) -> Query[Q]:
        """Fetches servers that are empty."""
        return Query(r"noplayers\1")

    @property
    def proxy(cls) -> Query[Q]:
        """Fetches servers that are spectator proxies."""
        return Query(r"proxy\1")

    @property
    def whitelisted(cls) -> Query[Q]:
        """Fetches servers that are whitelisted."""
        return Query(r"white\1")

    @property
    def dedicated(cls) -> Query[Q]:
        """Fetches servers that are running dedicated."""
        return Query(r"dedicated\1")

    @property
    def secure(cls) -> Query[Q]:
        """Fetches servers that are using anti-cheat technology (VAC, but potentially others as well)."""
        return Query(r"secure\1")

    @property
    def linux(cls) -> Query[Q]:
        """Fetches servers running on a Linux platform."""
        return Query(r"linux\1")

    @property
    def no_password(cls) -> Query[Q]:
        """Fetches servers that are not password protected."""
        return Query(r"password\0")

    @property
    def not_full(cls) -> Query[Q]:
        """Fetches servers that are not full."""
        return Query(r"full\1")

    @property
    def unique_addresses(cls) -> Query[Q]:
        """Fetches only one server for each unique IP address matched."""
        return Query(r"collapse_addr_hash\1")

    @property
    def version_match(cls) -> Query[str]:
        """Fetches servers running version "x" (``"*"`` is wildcard)."""
        return Query("version_match")

    @property
    def name_match(cls) -> Query[str]:
        """Fetches servers with their hostname matching "x" (``"*"`` is wildcard)."""
        return Query("name_match")

    @property
    def running_mod(cls) -> Query[str]:
        """Fetches servers running the specified modification (e.g. cstrike)."""
        return Query("gamedir")

    @property
    def running_map(cls) -> Query[str]:
        """Fetches servers running the specified map (e.g. cs_italy)"""
        return Query("map")

    @property
    def ip(cls) -> Query[str]:
        """Fetches servers on the specified IP address.

        See Also
        --------
        :meth:`Client.fetch_server` for an query free version of this.
        """
        return Query("gameaddr")

    @property
    def running(cls) -> Query[Union[Game, int]]:
        """Fetches servers running a :class:`.Game` or an :class:`int` app id."""
        return Query("appid", type=(Game, int), callback=lambda g: str(getattr(g, "id", g)))

    @property
    def not_running(cls) -> Query[Union[Game, int]]:
        """Fetches servers not running a :class:`.Game` or an :class:`int` app id."""
        return Query("nappid", type=(Game, int), callback=lambda g: str(getattr(g, "id", g)))

    @property
    def match_tags(self) -> Query[list[str]]:
        """Fetches servers with all of the given tag(s) in :attr:`GameServer.tags`."""
        return Query("gametype")

    @property
    def match_hidden_tags(self) -> Query[list[str]]:
        """Fetches servers with all of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
        return Query("gamedata")

    @property
    def match_hidden_tags(self) -> Query[list[str]]:
        """Fetches servers with all of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
        return Query("gamedata")


class Query(Generic[T], metaclass=QueryMeta):
    r"""A :class:`pathlib.Path` like class for constructing Global Master Server queries.

    .. container:: operations

        .. describe:: x == y

            Checks if two queries are equal order is checked.

        .. describe:: x / y

            Appends y's Query to x.

        .. describe:: x | y

            Combines the two queries in ``\nor\[x\y]``.

        .. describe:: x & y

            Combines the two queries in ``\nand\[x\y]``.

    Examples
    --------
    .. code-block::

        >>> (steam.Query.running / steam.TF2 / steam.Query.not_empty / steam.Query.secure).query
        r"\appid\440\empty\1\secure\1"
        >>> (steam.Query.not_empty / steam.Query.not_full | steam.Query.secure).query
        r"\empty\1\nor\[\full\1\secure\1]"
        >>> steam.Query.name_match / "A cool server" | steam.Query.match_tags / ["alltalk", "increased_maxplayers"]
        r"\nor\[\name_match\A cool server\gametype\[alltalk,increased_maxplayers]]"
    """

    all = QueryAll()  #: Fetches any servers. Any operations on this will fail.

    # immutable
    # based on https://developer.valvesoftware.com/wiki/Master_Server_Query_Protocol

    __slots__ = ("_raw", "_op", "_type", "_callback")

    def __new__(
        cls,
        *raw: Union[Query, str],
        op: Optional[Operator] = None,
        type: Union[type[T], tuple[type[T], ...], None] = None,
        callback: Optional[Callable[[T], str]] = None,
    ) -> Query:
        self = super().__new__(cls)
        self._raw = raw
        self._op = op
        self._type = type
        self._callback = callback
        return self

    def __repr__(self) -> str:
        return f"<Query query={self.query!r}>"

    def __truediv__(self, other: T) -> Query:
        cls = self.__class__
        try:
            last = self._raw[-1] if isinstance(self._raw[-1], Query) else None
            types = self._type or last._type
            callback = last._callback
        except (AttributeError, IndexError):
            pass
        else:
            if isinstance(other, types):
                return cls(self, callback(other), op=Operator.div)

        if not isinstance(other, Query):
            raise TypeError

        return self.__class__(self, other, op=Operator.div)

    # I'm not really sure what this does differently to __truediv__ or when to use it.
    def __and__(self, other: T) -> Query:
        cls = self.__class__
        if isinstance(other, self._type):
            return cls(self, other, op=Operator.and_)
        if not isinstance(other, Query):
            raise TypeError
        return cls(self, other, op=Operator.and_)

    def __or__(self, other: T) -> Query:
        cls = self.__class__
        if isinstance(other, self._type):
            return cls(self, other, op=Operator.or_)
        if not isinstance(other, Query):
            raise TypeError
        return cls(self, other, op=Operator.or_)

    def __eq__(self, other: Query) -> bool:
        if not isinstance(other, Query):
            return NotImplemented
        return self._raw == other._raw

    @property
    def query(self) -> str:
        """:class:`str`: The actual query used for querying Global Master Servers."""
        ret = []

        for query in self._raw:
            if isinstance(query, str):
                # a base query
                ret.append(query)
            elif self._type is not None and isinstance(query, self._type):
                ret.append(query._callback(query))
            else:
                ret.append(getattr(query, "query", query))
        return "\\".join(ret)


class BytesBuffer(BytesBuffer):
    def read_cstring(self, *args: Any, **kwargs: Any) -> str:
        return super().read_cstring(*args, **kwargs).decode("utf-8", "replace")


class ServerPlayer(NamedTuple):
    index: int
    name: str
    score: int
    play_time: timedelta


async def _handle_a2s_response(loop: asyncio.AbstractEventLoop, sock: socket.socket) -> bytes:
    packet = await loop.sock_recv(sock, 2048)
    header = struct.unpack_from("<l", packet)[0]

    if header == -1:  # single packet response
        return packet
    elif header == -2:  # multi packet response
        packets = [packet]
        payload_offset = -1

        # locate first packet and handle out of order packets
        while payload_offset == -1:
            # locate payload offset in uncompressed packet
            payload_offset = packet.find(b"\xff\xff\xff\xff", 0, 18)

            # locate payload offset in compressed packet
            if payload_offset == -1:
                payload_offset = packet.find(b"BZh", 0, 21)

            # if we still haven't found the offset receive the next packet
            if payload_offset == -1:
                packet = await loop.sock_recv(sock, 2048)
                packets.append(packet)

        # read header
        packet_idx, number_of_packets, compressed = _unpack_multi_packet_header(payload_offset, packet)
        if packet_idx != 0:
            raise ValueError("Unexpected first packet index")

        # receive any remaining packets
        for _ in range(number_of_packets - 1):
            packets.append(await loop.sock_recv(sock, 2048))

        packets = sorted(
            {_unpack_multi_packet_header(payload_offset, packet)[0]: packet for packet in packets}.items()
        )
        # reconstruct full response
        data = b"".join(x[1][payload_offset:] for x in packets)

        # decompress response if needed
        if compressed:
            size, check_sum = struct.unpack_from("<ll", packet, 10)
            data = decompress(data)

            if len(data) != size:
                raise ValueError(f"Response size mismatch - {len(data)} {size}")
            if check_sum != crc32(data):
                raise ValueError(f"Response check sum mismatch - {check_sum} {crc32(data)}")

        return data

    raise ValueError(f"Invalid response header - {header}")


def _unpack_multi_packet_header(payload_offset: int, packet: bytes):
    if payload_offset in (10, 12, 18):  # Source
        packet_id, number_of_packets, packet_idx = struct.unpack_from("<LBB", packet, 4)
        return packet_idx, number_of_packets, (packet_id & 0x80000000) != 0

    raise ValueError(f"Unexpected payload_offset - {payload_offset}")


class GameServer(SteamID):
    """Represents a game server

    Attributes
    ----------
    name: :class:`str`
        The name of the server.
    game: :class:`.Game`
        The game of the server.
    ip: :class:`str`
        The ip of the server.
    port: :class:`int`
        The port of the server.
    tags: list[:class:`str`]
        The tags of the server.
    map: :class:`str`
        The map the server is running.
    bot_count: :class:`int`
        The number of bots in the server.
    player_count: :class:`int`
        The number of players the server.
    max_player_count: :class:`str`
        The maximum player count of the server.
    region: :class:`str`
        The region the server is in.
    version: :class:`str`
        The version of the server.
    """

    __slots__ = (
        "name",
        "game",
        "ip",
        "port",
        "tags",
        "map",
        "bot_count",
        "player_count",
        "max_player_count",
        "region",
        "version",
        "_secure",
        "_dedicated",
        "_loop",
    )

    def __init__(self, server: GameServerProto):
        super().__init__(server.steamid, type="GameServer")
        self.name = server.name
        self.game = Game(id=server.appid)
        self.ip = server.addr.split(":")[0]
        self.port = server.gameport
        self.tags = server.gametype.split(",")
        self.map = server.map
        self.bot_count = server.bots
        self.player_count = server.players
        self.max_player_count = server.max_players
        self.region = EGameServerRegion.try_value(server.region)
        self.version = server.version

        self._secure = server.secure
        self._dedicated = server.dedicated
        self._loop = asyncio.get_event_loop()

    def __repr__(self) -> str:
        attrs = ("name", "game", "ip", "port", "id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    def is_secure(self) -> bool:
        """:class:`bool`: Whether the sever is secured, likely with VAC."""
        return self._secure

    def is_dedicated(self) -> bool:
        """:class:`bool`: Whether the sever is dedicated."""
        return self._dedicated

    @asynccontextmanager
    async def connect(self) -> AbstractAsyncContextManager[socket.socket]:
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM
        )  # steam uses TCP over UDP. Would use asyncio streams otherwise
        sock.setblocking(False)
        await self._loop.sock_connect(sock, (self.ip, self.port))
        try:
            yield sock
        except ValueError:
            # raised by _handle_a2s_response makes the calling method return None automagically
            return
        finally:
            sock.close()

    async def players(self, *, challenge: Literal[-1, 0] = 0) -> Optional[list[ServerPlayer]]:
        """|coro|
        Fetch a server's players.

        Parameters
        ----------
        challenge: :class:`int`
            The challenge for the request default is 0 can also be -1. You may need to change if the server doesn't seem
            to respond.

        Note
        ----
        It is recommended to use :func:`asyncio.wait_for` to allow this to return if the server doesn't respond.

        Returns
        -------
        Optional[list[:class:`ServerPlayer`]]
            The players, or ``None`` if something went wrong getting the info.

            ServerPlayer is a :class:`typing.NamedTuple` defined as:

                .. code-block:: python3

                    class ServerPlayer(NamedTuple):
                        index: int
                        name: str
                        score: int
                        play_time: timedelta
        """
        async with self.connect() as socket:
            socket.send(struct.pack("<lci", -1, b"U", challenge))
            data = await self._loop.sock_recv(socket, 512)
            _, header, challenge_ = struct.unpack_from("<lcl", data)

            if header == b"D":
                buffer = BytesBuffer(data)
            elif header == b"A":
                socket.send(struct.pack("<lci", -1, b"U", challenge_))

                buffer = BytesBuffer(await _handle_a2s_response(self._loop, socket))
            else:
                return None

            header, number_of_players = buffer.read_struct("<4xcB")
            if header != b"D":
                return None

            return [
                ServerPlayer(
                    index=buffer.read_struct("<B")[0],
                    name=buffer.read_cstring(),
                    score=buffer.read_struct("<f")[0],
                    play_time=timedelta(seconds=buffer.read_float()),
                )
                for _ in range(number_of_players)
            ]

    async def rules(self, *, challenge: Literal[-1, 0] = -1) -> Optional[dict[str, str]]:
        """|coro|
        Fetch a server's rules (console variables). e.g. ``sv_gravity`` or ``sv_voiceenable``.

        Parameters
        ----------
        challenge: :class:`int`
            The challenge for the request default is 0 can also be -1. You may need to change if the server doesn't seem
            to respond.

        Note
        ----
        It is recommended to use :func:`asyncio.wait_for` to allow this to return if the server doesn't respond.

        Returns
        -------
        Optional[dict[:class:`str`, :class:`str]]
            The server's rules.
        """
        async with self.connect() as socket:
            socket.send(struct.pack("<lci", -1, b"V", challenge))
            _, header, challenge = struct.unpack_from("<lcl", await self._loop.sock_recv(socket, 512))

            if header != b"A":
                return None

            socket.send(struct.pack("<lci", -1, b"V", challenge))
            buffer = BytesBuffer(await _handle_a2s_response(self._loop, socket))

            header, number_of_rules = buffer.read_struct("<4xcH")
            if header != b"E":
                return None

            return {buffer.read_cstring(): buffer.read_cstring() for _ in range(number_of_rules)}
