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
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, TypeVar

from typing_extensions import Literal, TypeAlias

from .abc import SteamID
from .enums import Enum, GameServerRegion, Type
from .game import Game, StatefulGame
from .utils import StructIO

if TYPE_CHECKING:
    from .protobufs.game_servers import GetServerListResponseServer
    from .state import ConnectionState

T = TypeVar("T")
Q: TypeAlias = "Query[Q]"

__all__ = (
    "Query",
    "GameServer",
    "ServerPlayer",
)


class Operator(Enum):
    # fmt: off
    div  = "\\"
    nor  = "\\nor\\"
    nand = "\\nand\\"
    # fmt: on

    def format(self, query_1: str, query_2: str) -> str:
        return f"{query_1}{query_2}" if self is Operator.div else f"{self.value}[{query_1}{query_2}]"


class QueryAll:
    def __repr__(self) -> str:
        return self.__class__.__name__

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__)

    query = ""


class QueryMeta(type):
    @property
    def not_empty(cls) -> Q:
        """Fetches servers that are not empty."""
        return Query[Q](r"\empty\1")

    @property
    def empty(cls) -> Q:
        """Fetches servers that are empty."""
        return Query[Q](r"\noplayers\1")

    @property
    def proxy(cls) -> Q:
        """Fetches servers that are spectator proxies."""
        return Query[Q](r"\proxy\1")

    @property
    def whitelisted(cls) -> Q:
        """Fetches servers that are whitelisted."""
        return Query[Q](r"\white\1")

    @property
    def dedicated(cls) -> Q:
        """Fetches servers that are running dedicated."""
        return Query[Q](r"\dedicated\1")

    @property
    def secure(cls) -> Q:
        """Fetches servers that are using anti-cheat technology (VAC, but potentially others as well)."""
        return Query[Q](r"\secure\1")

    @property
    def linux(cls) -> Q:
        """Fetches servers running on a Linux platform."""
        return Query[Q](r"\linux\1")

    @property
    def no_password(cls) -> Q:
        """Fetches servers that are not password protected."""
        return Query[Q](r"\password\0")

    @property
    def not_full(cls) -> Q:
        """Fetches servers that are not full."""
        return Query[Q](r"\full\1")

    @property
    def unique_addresses(cls) -> Q:
        """Fetches only one server for each unique IP address matched."""
        return Query[Q](r"\collapse_addr_hash\1")

    @property
    def version_match(cls) -> Query[str]:
        """Fetches servers running version "x" (``"*"`` is wildcard)."""
        return Query[str]("\\version_match\\", type=str)

    @property
    def name_match(cls) -> Query[str]:
        """Fetches servers with their hostname matching "x" (``"*"`` is wildcard)."""
        return Query[str]("\\name_match\\", type=str)

    @property
    def running_mod(cls) -> Query[str]:
        """Fetches servers running the specified modification (e.g. cstrike)."""
        return Query[str]("\\gamedir\\", type=str)

    @property
    def running_map(cls) -> Query[str]:
        """Fetches servers running the specified map (e.g. cs_italy)"""
        return Query[str]("\\map\\", type=str)

    @property
    def ip(cls) -> Query[str]:
        """Fetches servers on the specified IP address, port is optional.

        See Also
        --------
        :meth:`Client.fetch_server` for an query free version of this.
        """
        return Query[str]("\\gameaddr\\", type=str)

    @property
    def running(cls) -> Query[Game | int]:
        """Fetches servers running a :class:`.Game` or an :class:`int` app id."""
        return Query("\\appid\\", type=(Game, int), callback=lambda game: getattr(game, "id", game))

    @property
    def not_running(cls) -> Query[Game | int]:
        """Fetches servers not running a :class:`.Game` or an :class:`int` app id."""
        return Query("\\nappid\\", type=(Game, int), callback=lambda game: getattr(game, "id", game))

    @property
    def match_tags(cls) -> Query[list[str]]:
        """Fetches servers with all of the given tag(s) in :attr:`GameServer.tags`."""
        return Query("\\gametype\\", type=list, callback=lambda items: f"[{','.join(items)}]")

    @property
    def match_hidden_tags(cls) -> Query[list[str]]:
        """Fetches servers with all of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
        return Query("\\gamedata\\", type=list, callback=lambda items: f"[{','.join(items)}]")

    @property
    def match_any_hidden_tags(cls) -> Query[list[str]]:
        """Fetches servers with any of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
        return Query("\\gamedataor\\", type=list, callback=lambda items: f"[{','.join(items)}]")

    @property
    def all(cls) -> QueryAll:
        """Fetches any servers. Any operations on this will fail."""
        return QueryAll()


class Query(Generic[T], metaclass=QueryMeta):
    r"""A :class:`pathlib.Path` like class for constructing Global Master Server queries.

    .. container:: operations

        .. describe:: x == y

            Checks if two queries are equal, order is checked.

        .. describe:: x / y

            Appends y's query to x.

        .. describe:: x | y

            Combines the two queries in ``\nor\[x\y]`` (not or).

        .. describe:: x & y

            Combines the two queries in ``\nand\[x\y]`` (not and).

    Examples
    --------
    .. code-block:: pycon

        >>> Query.running / TF2 / Query.not_empty / Query.secure
        <Query query='\\appid\\440\\empty\\1\\secure\\1'>
        # matches games running TF2, that are not empty and are using VAC
        >>> Query.not_empty / Query.not_full | Query.secure
        <Query query='\\empty\\1\\nor\\[\\full\\1\\secure\\1]'>
        # matches games that are not empty, not full and are using VAC
        >>> Query.name_match / "A not cool server" | Query.match_tags / ["alltalk", "increased_maxplayers"]
        <Query query='\\nor\\[\\name_match\\A not cool server\\gametype\\[alltalk,increased_maxplayers]]'>
        # matches games where the server name is not "A cool Server" or the server doesn't support alltalk or increased
        # max players
        >>> Query.linux & Query.no_password
        # matches games where the server is not on linux and the server doesn't have no password (has a password)
    """

    # simple specification:
    # - immutable
    # - based on https://developer.valvesoftware.com/wiki/Master_Server_Query_Protocol

    __slots__ = ("_raw", "_type", "_callback")

    def __new__(
        cls,
        *raw: Query[Any] | Operator | str,
        type: type[T] | tuple[type[T], ...] | None = None,
        callback: Callable[[T], Any] = lambda x: x,
    ) -> Query[T]:
        self = super().__new__(cls)
        self._raw = raw
        self._type = type
        self._callback = callback
        return self

    def __repr__(self) -> str:
        return f"<Query query={self.query!r}>"

    def _process_op(self, other: T, op: Operator) -> Q:
        cls = self.__class__

        if self._type and isinstance(other, self._type):
            return cls(self, op, other)

        if not isinstance(other, Query):
            return NotImplemented

        return cls(self, op, other, type=other._type, callback=other._callback)

    def __truediv__(self, other: T) -> Q:
        return self._process_op(other, Operator.div)

    def __and__(self, other: T) -> Q:
        return self._process_op(other, Operator.nand)

    def __or__(self, other: T) -> Q:
        return self._process_op(other, Operator.nor)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Query):
            return NotImplemented
        return self._raw == other._raw

    @property
    def query(self) -> str:
        """The actual query used for querying Global Master Servers."""

        if len(self._raw) == 1:  # string query
            return self._raw[0]

        # normal
        query_1, op, query_2 = self._raw

        return op.format(
            query_1.query,
            query_2.query if isinstance(query_2, Query) else query_1._callback(query_2),
        )


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
        if payload_offset not in (10, 12, 18):  # Source
            raise ValueError(f"Unexpected payload_offset - {payload_offset}")
        packet_id, number_of_packets, packet_idx = struct.unpack_from("<LBB", packet, 4)
        compressed = (packet_id & 0x80000000) != 0
        if packet_idx != 0:
            raise ValueError("Unexpected first packet index")

        # receive any remaining packets
        for _ in range(number_of_packets - 1):
            packets.append(await loop.sock_recv(sock, 2048))

        packets = sorted({struct.unpack_from("<B", packet, 9)[0]: packet for packet in packets}.items())
        # reconstruct full response
        data = b"".join(packet[1][payload_offset:] for packet in packets)

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


class GameServer(SteamID):
    """Represents a game server.

    Attributes
    ----------
    name
        The name of the server.
    game
        The game of the server.
    ip
        The ip of the server.
    port
        The port of the server.
    tags
        The tags of the server.
    map
        The map the server is running.
    bot_count
        The number of bots in the server.
    player_count
        The number of players the server.
    max_player_count
        The maximum player count of the server.
    region
        The region the server is in.
    version
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
        "_state",
    )

    def __init__(self, state: ConnectionState, server: GetServerListResponseServer):
        super().__init__(server.steamid, type=Type.GameServer)
        self.name = server.name
        self.game = StatefulGame(state, id=server.appid)
        self.ip = server.addr.split(":")[0]
        self.port = server.gameport
        self.tags = server.gametype.split(",")
        self.map = server.map
        self.bot_count = server.bots
        self.player_count = server.players
        self.max_player_count = server.max_players
        self.region = GameServerRegion.try_value(server.region)
        self.version = server.version

        self._secure = server.secure
        self._dedicated = server.dedicated
        self._loop = state.loop
        self._state = state

    def __repr__(self) -> str:
        attrs = ("name", "game", "ip", "port", "region", "id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    def is_secure(self) -> bool:
        """Whether the sever is secured, likely with VAC."""
        return self._secure

    def is_dedicated(self) -> bool:
        """Whether the sever is dedicated."""
        return self._dedicated

    @asynccontextmanager
    async def connect(self, challenge: int, char: bytes) -> AsyncGenerator[StructIO, None]:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # steam uses TCP over UDP. I would use asyncio streams otherwise
            sock.setblocking(False)
            await self._loop.sock_connect(sock, (self.ip, self.port))

            sock.send(struct.pack("<lci", -1, char, challenge))
            data = await self._loop.sock_recv(sock, 512)
            _, header, challenge = struct.unpack_from("<lcl", data)

            if header != b"A":
                return

            sock.send(struct.pack("<lci", -1, char, challenge))
            try:
                data = await _handle_a2s_response(self._loop, sock)
            except ValueError:
                return

        with StructIO(data) as io:
            yield io

    async def players(self, *, challenge: Literal[-1, 0] = 0) -> list[ServerPlayer] | None:
        """Fetch a server's players  or ``None`` if something went wrong getting the info.

        Parameters
        ----------
        challenge
            The challenge for the request default is 0 can also be -1. You may need to change if the server doesn't seem
            to respond.

        Note
        ----
        It is recommended to use :func:`asyncio.wait_for` to allow this to return if the server doesn't respond.

        Returns
        ServerPlayer is a :class:`typing.NamedTuple` defined as:

            .. code-block:: python3

                class ServerPlayer(NamedTuple):
                    index: int
                    name: str
                    score: int
                    play_time: timedelta
        """
        async with self.connect(challenge, b"U") as buffer:
            header, number_of_players = buffer.read_struct("<4xcB")
            if header != b"D":
                return None

            return [
                ServerPlayer(
                    index=buffer.read_u8(),
                    name=buffer.read_cstring().decode("utf-8", "replace"),
                    score=buffer.read_long(),
                    play_time=timedelta(seconds=buffer.read_f32()),
                )
                for _ in range(number_of_players)
            ]

    async def rules(self, *, challenge: Literal[-1, 0] = 0) -> dict[str, str] | None:
        """Fetch a console variables. e.g. ``sv_gravity`` or ``sv_voiceenable``.

        Parameters
        ----------
        challenge
            The challenge for the request default is 0 can also be -1. You may need to change if the server doesn't seem
            to respond.

        Note
        ----
        It is recommended to use :func:`asyncio.wait_for` to allow this to return if the server doesn't respond.
        """
        async with self.connect(challenge, b"V") as buffer:
            header, number_of_rules = buffer.read_struct("<4xcH")
            if header != b"E":
                return None

            return {
                buffer.read_cstring().decode("utf-8", "replace"): buffer.read_cstring().decode("utf-8", "replace")
                for _ in range(number_of_rules)
            }
