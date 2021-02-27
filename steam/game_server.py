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

This contains a copy of
https://github.com/ValvePython/steam/blob/master/steam/game_servers.py
"""

from __future__ import annotations

import asyncio
import socket
import struct
from binascii import crc32
from bz2 import decompress
from datetime import timedelta
from typing import TYPE_CHECKING, Any, NamedTuple, Optional, TypeVar, Union

from typing_extensions import Literal

from . import SteamID
from .game import Game
from .utils import BytesBuffer

if TYPE_CHECKING:
    from .protobufs.steammessages_gameservers import CGameServersGetServerListResponseServer

Q = TypeVar("Q", bound="Query")

__all__ = (
    "Query",
    "GameServer",
    "ServerPlayer",
)


class QueryMeta(type):
    @property
    def not_empty(cls) -> Query:
        """Fetches servers that are not empty."""
        return Query(r"empty\1")

    @property
    def empty(cls) -> Query:
        """Fetches servers that are empty."""
        return Query(r"noplayers\1")

    @property
    def proxy(cls) -> Query:
        """Fetches servers that are spectator proxies."""
        return Query(r"proxy\1")

    @property
    def whitelisted(cls) -> Query:
        """Fetches servers that are whitelisted."""
        return Query(r"white\1")

    @property
    def dedicated(cls) -> Query:
        """Fetches servers that are running dedicated."""
        return Query(r"dedicated\1")

    @property
    def secure(cls) -> Query:
        """Fetches servers that are using anti-cheat technology (VAC, but potentially others as well)."""
        return Query(r"secure\1")

    @property
    def linux(cls) -> Query:
        """Fetches servers running on a Linux platform."""
        return Query(r"linux\1")

    @property
    def no_password(cls) -> Query:
        """Fetches servers that are not password protected."""
        return Query(r"password\0")

    @property
    def not_full(cls) -> Query:
        """Fetches servers that are not full."""
        return Query(r"full\1")

    @property
    def unique_addresses(cls) -> Query:
        """Fetches only one server for each unique IP address matched."""
        return Query(r"collapse_addr_hash\1")

    @property
    def version_match(cls) -> Query:
        """Fetches servers running version "x" (``"*"`` is wildcard)."""
        return StringQuery("version_match")

    @property
    def name_match(cls) -> Query:
        """Fetches servers with their hostname matching "x" (``"*"`` is wildcard)."""
        return StringQuery("name_match")

    @property
    def running_mod(cls) -> Query:
        """Fetches servers running the specified modification (e.g. cstrike)."""
        return StringQuery("gamedir")

    @property
    def running_map(cls) -> Query:
        """Fetches servers running the specified modification (ex. cstrike)."""
        return StringQuery("gamedir")

    @property
    def ip(cls) -> Query:
        """Fetches servers on the specified IP address.

        See Also
        --------
        :meth:`Client.fetch_server` for an query free version of this.
        """
        return StringQuery("gameaddr")

    @property
    def running(cls) -> Query:
        """Fetches servers running a :class:`.Game` or an :class:`int` app id."""
        return GameQuery("appid")

    @property
    def not_running(cls) -> Query:
        """Fetches servers not running a :class:`.Game` or an :class:`int` app id."""
        return GameQuery("nappid")

    @property
    def match_tags(self) -> Query:
        """Fetches servers with all of the given tag(s) in :attr:`GameServer.tags`."""
        return ListQuery("gametype")

    @property
    def match_hidden_tags(self) -> Query:
        """Fetches servers with all of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
        return ListQuery("gamedata")

    @property
    def match_hidden_tags(self) -> Query:
        """Fetches servers with all of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
        return ListQuery("gamedata")

    @property
    def all(cls) -> Query:
        """Fetches any servers."""
        return Query("")


class Query(metaclass=QueryMeta):
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
        >>> steam.Query.name_match / "A cool server" | steam.Query.match_tags / ["all_talk", "sv_cheats"]
        r"\nor\[\name_match\A cool server\gametype\[all_talk,sv_cheats]]"
    """

    __slots__ = ("raw",)

    def __init__(self, *values: str):
        self.raw = values

    def __repr__(self) -> str:
        return f"<Query query={self.query!r}>"

    def __truediv__(self, other: Union[Query, Game, list[str], str]) -> Query:
        if not isinstance(other, Query):  # TODO this needs redoing to be less garbage
            cls = MAPPING[self.raw[-1]]
            self.raw = self.raw[:-1]
            other = cls / other
        return self.__class__(*self.raw, *other.raw)

    def _parse_op(self, op: str, other: Query) -> Query:
        if not isinstance(other, Query):
            return NotImplemented
        return self.__class__(*self.raw[:-1], rf"{op}\[", self.raw[-1], *other.raw[:-1], f"{other.raw[-1]}]")

    # I'm not really sure what this does differently to __truediv__ or when to use it.
    def __and__(self, other: Query) -> Query:
        return self._parse_op("nand", other)

    def __or__(self, other: Query) -> Query:
        return self._parse_op("nor", other)

    def __eq__(self, other: Query) -> bool:
        if not isinstance(other, Query):
            return NotImplemented
        return self.raw == other.raw

    @property
    def query(self) -> str:
        """:class:`str`: The actual query used for querying Global Master Servers."""
        return "\\".join(("", *self.raw))


class StringQuery(Query):
    def __truediv__(self: Q, other: Union[str, Query]) -> Query:
        if other.__class__ is Query:
            return super().__truediv__(other)
        if not isinstance(other, str):
            return NotImplemented
        return self.__class__(*self.raw, other)


class ListQuery(Query):
    def __truediv__(self, other: Union[list[str], Query]) -> Query:
        if other.__class__ is Query:
            return super().__truediv__(other)
        if not isinstance(other, list):
            return NotImplemented
        return self.__class__(*self.raw, f"[{','.join(other)}]")


class GameQuery(Query):
    def __truediv__(self, other: Union[Game, Query]) -> Query:
        if other.__class__ is Query:
            return super().__truediv__(other)
        if isinstance(other, Game):
            return self.__class__(*self.raw, str(other.id))
        if isinstance(other, int):
            return self.__class__(*self.raw, str(other))

        return NotImplemented


MAPPING = {}
for name in dir(QueryMeta):
    attr = getattr(QueryMeta, name, None)
    if attr.__class__ is property:
        query = attr.fget(None)
        MAPPING[query.raw[0]] = query


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
        for _ in range(number_of_packets):
            packets.append(await loop.sock_recv(sock, 2048))

        # ensure packets are in correct order
        packets = sorted({_unpack_multi_packet_header(payload_offset, packet)[0]: packet for packet in packets})

        # reconstruct full response
        data = b"".join(map(lambda x: x[1][payload_offset:], packets))

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


def _unpack_multi_packet_header(payload_offset, packet):
    if payload_offset in (10, 12, 18):  # Source
        (
            packet_id,
            number_packets,
            packet_idx,
        ) = struct.unpack_from("<LBB", packet, 4)
        return packet_id, number_packets, (packet_idx & 0x80000000) != 0  # idx, total, compressed

    raise ValueError(f"Unexpected payload_offset - {payload_offset}")


async def connect_to(ip: str, port: int, loop: asyncio.AbstractEventLoop) -> socket.socket:
    # TCP over UDP :))))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    await loop.sock_connect(sock, (ip, port))
    return sock


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
    )

    def __init__(self, server: CGameServersGetServerListResponseServer):
        super().__init__(server.steamid)
        self.name = server.name
        self.game = Game(id=server.appid)
        self.ip = server.addr.split(":")[0]
        self.port = server.gameport
        self.tags = server.gametype.split(",")
        self.map = server.map
        self.bot_count = server.bots
        self.player_count = server.players
        self.max_player_count = server.max_players
        self.region = server.region
        self.version = server.version

        self._secure = server.secure
        self._dedicated = server.dedicated

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

    async def players(self, *, challenge: Literal[-1, 0] = 0) -> Optional[list[ServerPlayer]]:
        """|coro|
        Fetch a servers players.

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
        loop = asyncio.get_event_loop()
        sock = await connect_to(self.ip, self.port, loop)

        try:
            sock.send(struct.pack("<lci", -1, b"U", challenge))
            data = await loop.sock_recv(sock, 512)
            _, header, challenge_ = struct.unpack_from("<lcl", data)

            if header == b"D":
                buffer = BytesBuffer(data)
            elif header == b"A":
                sock.send(struct.pack("<lci", -1, b"U", challenge_))

                buffer = BytesBuffer(await _handle_a2s_response(loop, sock))
            else:
                return None

            header, num_players = buffer.read_struct("<4xcB")

            if header != b"D":
                return None

            return [
                ServerPlayer(
                    index=buffer.read_struct("<B")[0],
                    name=buffer.read_cstring(),
                    score=buffer.read_struct("<f")[0],
                    play_time=timedelta(seconds=buffer.read_float()),
                )
                for _ in range(num_players)
            ]

        except ValueError:
            return None
        finally:
            sock.close()

    async def rules(self, *, challenge: Literal[-1, 0] = 0) -> Optional[dict[str, str]]:
        """|coro|
        Fetch a server's rules.

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
        loop = asyncio.get_event_loop()
        sock = await connect_to(self.ip, self.port, loop)
        try:
            # request challenge number
            if challenge in (-1, 0):
                sock.send(struct.pack("<lci", -1, b"V", challenge))
                try:
                    _, header, challenge = struct.unpack_from("<lcl", await loop.sock_recv(sock, 512))
                finally:
                    sock.close()

                if header != b"A":
                    return None

            # request player info
            sock.send(struct.pack("<lci", -1, b"V", challenge))
            data = BytesBuffer(await _handle_a2s_response(loop, sock))
        except ValueError:
            return None
        finally:
            sock.close()

        header, num_rules = data.read_struct("<4xcH")

        if header != b"E":
            return None

        return {data.read_cstring(): data.read_cstring() for _ in range(num_rules)}
