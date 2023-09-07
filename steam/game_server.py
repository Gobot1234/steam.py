"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from datetime import timedelta
from ipaddress import IPv4Address
from operator import attrgetter  # noqa: TCH003
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, cast, get_type_hints

from typing_extensions import Annotated, TypedDict, Unpack

from .app import App, PartialApp
from .enums import GameServerRegion, Type
from .id import ID
from .protobufs.game_servers import EQueryType, GetServerListResponseServer, QueryResponse

if TYPE_CHECKING:
    from .state import ConnectionState


__all__ = (
    "Query",
    "GameServer",
    "ServerPlayer",
)


class Operator:
    @staticmethod
    def not_(arg: str) -> str:
        return Operator.nor(arg)

    @staticmethod
    def and_(*args: str) -> str:
        """All"""
        return "".join(args)

    # or would be nice if you can figure it out

    @staticmethod
    def nand(*args: str) -> str:
        """Not all"""
        joined = "\\".join(args)
        return f"\\nand\\{len(args)}{joined}"

    @staticmethod
    def nor(*args: str) -> str:
        """Not any"""
        joined = "\\".join(args)
        return f"\\nor\\{len(args)}{joined}"


# class LFD2SpecificQueries:  # TODO need implementing
#     @property
#     def match_hidden_tags(cls) -> Query[list[str]]:
#         """Fetches servers with all the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
#         return Query["list[str]"]("\\gamedata\\", type=list, callback=lambda items: f"[{','.join(items)}]")

#     @property
#     def match_any_hidden_tags(cls) -> Query[list[str]]:
#         """Fetches servers with any of the given tag(s) in their 'hidden' tags only applies for :attr:`steam.LFD2`."""
#         return Query["list[str]"]("\\gamedataor\\", type=list, callback=lambda items: f"[{','.join(items)}]")


class QueryWhereBoolKwargs(TypedDict, total=False):
    # Annotated[bool, TruthyCase | None, FalsyCase?]
    empty: Annotated[bool, r"\noplayers\1", r"\empty\1"]
    is_proxy: Annotated[bool, r"\proxy\1"]
    whitelisted: Annotated[bool, r"\white\1"]
    dedicated: Annotated[bool, r"\dedicated\1"]
    secure: Annotated[bool, r"\secure\1"]
    linux: Annotated[bool, r"\linux\1"]
    has_password: Annotated[bool, None, r"\password\0"]
    full: Annotated[bool, None, r"\full\1"]
    only_one_per_ip: Annotated[Literal[True], r"\collapse_addr_hash\1"]  # only makes sense as Literal[True]


class QueryWhereSimpleKwargs(TypedDict, total=False):
    version_match: Annotated[str, "\\version_match\\"]
    name_match: Annotated[str, "\\name_match\\"]
    game_directory: Annotated[str, "\\gamedir\\"]
    map: Annotated[str, "\\map\\"]
    ip: Annotated[str, "\\gameaddr\\"]
    app: Annotated[App, "\\app\\", attrgetter("id")]  # has inverse?
    not_app: Annotated[App, "\\napp\\", attrgetter("id")]
    tags: Annotated[list[str], "\\gametype\\", ",".join]
    region: Annotated[GameServerRegion, "\\region\\", attrgetter("value")]


class QueryWhereKwargs(QueryWhereBoolKwargs, QueryWhereSimpleKwargs, total=False):
    ...


for cls in (QueryWhereBoolKwargs, QueryWhereSimpleKwargs):
    cls.__annotations__ = get_type_hints(cls, include_extras=True)

QueryWhereKwargs.__annotations__ = QueryWhereBoolKwargs.__annotations__ | QueryWhereSimpleKwargs.__annotations__


class Query:
    """A class to construct Global Master Server queries."""

    @classmethod
    def where(cls, **kwargs: Unpack[QueryWhereKwargs]) -> str:
        """Construct a query meeting all the given criteria.

        Parameters
        ----------
        empty
            Fetches servers that are empty.
        is_proxy
            Fetches servers that are spectator proxies.
        whitelisted
            Fetches servers that are whitelisted.
        dedicated
            Fetches servers that are running dedicated.
        secure
            Fetches servers that are using anti-cheat technology (VAC, but potentially others as well).
        linux
            Fetches servers running on a Linux platform.
        has_password
            Fetches servers that are password protected.
        full
            Fetches servers that are full.
        only_one_per_ip
            Fetches only one server for each unique IP address matched.
        version_match
            Fetches servers running version "x" (``"*"`` is wildcard equivalent to ``.*`` in regex).
        name_match
            Fetches servers with their name matching "x" (``"*"`` is wildcard equivalent to ``.*`` in regex).
        game_directory
            Fetches servers running the specified modification (e.g. cstrike).
        map
            Fetches servers running the specified map (e.g. cs_italy)
        ip
            Fetches servers on the specified IP address, port is optional.
        app
            Fetches servers running a :class:`.App`.
        not_app
            Fetches servers not running a :class:`.App`.
        tags
            Fetches servers with all the given tag(s) in :attr:`GameServer.tags`.
        region
            Fetches servers in a given region.

        Returns
        -------
        The query that should be passed to :meth:`Client.fetch_servers`.

        Examples
        --------

        Match servers running TF2, that are not empty and are using VAC

        .. code-block:: pycon

            >>> Query.where(
            ...     app=TF2,
            ...     empty=False,
            ...     secure=True,
            ... )

        Match servers where the server name is not "A cool Server" and the server supports "alltalk" and increased max
        players

        .. code-block:: pycon

            >>> Query.where(name_match="A not cool server*", match_tags=["alltalk", "increased_maxplayers"])
        """

        filters: list[str] = []

        for name, value in kwargs.items():
            try:
                annotated = QueryWhereKwargs.__annotations__[name]
            except KeyError:
                raise TypeError(f"{name!r} is an invalid keyword argument for where()") from None
            metadata: tuple[Any, ...] = annotated.__metadata__
            if name in QueryWhereBoolKwargs.__annotations__:
                value = cast(bool, value)
                try:
                    filter_code = metadata[not value]
                except IndexError:
                    filter_code = None
                if filter_code is None:
                    inverse_filter_code = metadata[value]
                    filter_code = Operator.not_(inverse_filter_code)
            else:
                filter_code = metadata[0]
                if len(metadata) > 1:
                    value = str(metadata[-1](value))
                filter_code += value
            filters.append(filter_code)
        return Operator.and_(*filters)


class ServerPlayer(NamedTuple):
    name: str
    """The player's name."""
    score: int
    """The player's score."""
    play_time: timedelta
    """The amount of time the player has spent on the server."""


class GameServer(ID[Literal[Type.GameServer]]):
    """Represents a game server."""

    __slots__ = (
        "name",
        "app",
        "ip",
        "port",
        "tags",
        "map",
        "bot_count",
        "player_count",
        "max_player_count",
        "region",
        "version",
        "game_directory",
        "_secure",
        "_dedicated",
        "_state",
    )

    def __init__(self, state: ConnectionState, server: GetServerListResponseServer):
        super().__init__(server.steamid, type=Type.GameServer)
        self.name = server.name
        """The name of the server."""
        self.app = PartialApp(state, id=server.appid)
        """The app of the server."""
        self.ip = IPv4Address(server.addr.rpartition(":")[0])
        """The ip of the server."""
        self.port = server.gameport
        """The port of the server."""
        self.tags = server.gametype.split(",")
        """The tags of the server."""
        self.map = server.map
        """The map the server is running."""
        self.bot_count = server.bots
        """The number of bots in the server."""
        self.player_count = server.players
        """The number of players the server."""
        self.max_player_count = server.max_players
        """The maximum player count of the server."""
        self.region = GameServerRegion.try_value(server.region)
        """The region the server is in."""
        self.version = server.version
        """The version of the server."""
        self.game_directory = server.gamedir
        """The server's game directory e.g. ``"cstrike"``"""

        self._secure = server.secure
        self._dedicated = server.dedicated
        self._state = state

    def __repr__(self) -> str:
        attrs = ("name", "app", "ip", "port", "region", "id", "universe", "instance")
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

    async def _query(self, type: EQueryType) -> QueryResponse:
        return await self._state.query_server(int(self.ip), self.port, self.app.id, type)

    async def update(self) -> None:
        """Update this game server instance in place."""
        proto = await self._query(EQueryType.Ping)
        server = proto.ping_data
        # self.ip = ip_address(betterproto.which_one_of(server, "server_ip")[1])
        # query_port: int = betterproto.uint32_field(2)
        # game_port: int = betterproto.uint32_field(3)
        # spectator_port: int = betterproto.uint32_field(4)
        # spectator_server_name: str = betterproto.string_field(5)
        self.name = server.server_name
        self.game_directory = server.gamedir
        self.map = server.map
        # game_description: str = betterproto.string_field(11)
        self.tags = server.gametype.split(",")
        self.player_count = server.num_players
        self.max_player_count = server.max_players
        self.bot_count = server.num_bots
        # password: bool = betterproto.bool_field(16)
        self._secure = server.secure
        self._dedicated = server.dedicated
        self.version = server.version
        # sdr_popid: int = betterproto.fixed32_field(20)
        # sdr_location_string: str = betterproto.string_field(21)

    async def players(self) -> list[ServerPlayer]:
        """Fetch a server's players.

        Returns
        -------
        .. source:: steam.ServerPlayer
        """
        proto = await self._query(EQueryType.Players)
        return [
            ServerPlayer(
                name=player.name,
                score=player.score,
                play_time=timedelta(seconds=player.time_played),
            )
            for player in proto.players_data.players
        ]

    async def rules(self) -> dict[str, str]:
        """Fetch a console variables. e.g. ``sv_gravity`` or ``sv_voiceenable``."""
        proto = await self._query(EQueryType.Rules)
        return proto.rules_data.rules
