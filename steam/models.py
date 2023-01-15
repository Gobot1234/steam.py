"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import logging
import re
import traceback
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from io import BytesIO
from types import CoroutineType
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, Protocol, TypedDict, TypeVar

from aiohttp.streams import AsyncStreamIterator, ChunkTupleAsyncStreamIterator
from typing_extensions import Self
from yarl import URL as _URL

from . import utils
from ._const import URL
from .enums import CurrencyCode, IntEnum
from .media import Media
from .protobufs import EMsg

if TYPE_CHECKING:
    from _typeshed import StrOrBytesPath

    from .gateway import Msgs
    from .state import ConnectionState


__all__ = (
    "PriceOverview",
    "Ban",
    "Avatar",
)

F = TypeVar("F", bound="Callable[..., Any]")
P = ParamSpec("P")


def api_route(path: str, version: int = 1, *, publisher: bool = False) -> _URL:
    return (URL.PUBLISHER_API if publisher else URL.API) / f"{path}/v{version}"


class _ReturnTrue:
    __slots__ = ()

    def __call__(self, *_: Any, **__: Any) -> Literal[True]:
        return True

    def __repr__(self) -> str:
        return "<return_true>"


return_true = _ReturnTrue()


class Registerable:
    __slots__ = ("parsers_name",)

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        self = super().__new__(cls)
        cls.parsers_name = tuple(cls.__annotations__)[0]
        bases = tuple(reversed(cls.__mro__[:-2]))  # skip Registerable and object
        for idx, base in enumerate(bases):
            parsers_name = tuple(base.__annotations__)[0]
            for name, attr in base.__dict__.items():
                if not hasattr(attr, "msg"):
                    continue
                try:
                    parsers = getattr(self, parsers_name)
                except AttributeError:
                    parsers = {}
                    setattr(self, parsers_name, parsers)
                msg_parser = getattr(self, name)
                if idx != 0 and isinstance(attr.msg, EMsg):
                    parsers = getattr(self, tuple(bases[0].__annotations__)[0])
                parsers[attr.msg] = msg_parser

        return self

    @utils.cached_property
    def _logger(self) -> logging.Logger:
        return logging.getLogger(self.__class__.__module__)

    @staticmethod
    def _run_parser_callback(task: asyncio.Task[object]) -> None:
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception:
            traceback.print_exception(exception)

    def run_parser(self, msg: Msgs) -> None:
        try:
            event_parser: Callable[[Msgs], CoroutineType[Any, Any, object] | object] = getattr(self, self.parsers_name)[
                msg.__class__.MSG
            ]
        except (KeyError, TypeError):
            try:
                self._logger.debug("Ignoring event %r", msg, exc_info=True)
            except Exception:
                self._logger.debug("Ignoring event with %r", msg.__class__)
        else:
            try:
                result = event_parser(msg)
            except Exception:
                return traceback.print_exc()

            if isinstance(result, CoroutineType):
                asyncio.create_task(result, name=f"steam.py: {event_parser.__name__}").add_done_callback(
                    self._run_parser_callback
                )


EventParser = None


def register(msg: IntEnum) -> Callable[[F], F]:  # this afaict is not type able currently without HKT
    def wrapper(callback: F) -> F:
        callback.msg = msg
        return callback

    return wrapper


PRICE_RE = re.compile(r"(^\D*(?P<price>[\d,.]*)\D*$)")


class PriceOverviewDict(TypedDict):
    success: bool
    lowest_price: str
    median_price: str
    volume: str


class PriceOverview:
    """Represents the data received from https://steamcommunity.com/market/priceoverview."""

    __slots__ = ("currency", "volume", "lowest_price", "median_price")

    lowest_price: float | str
    """The lowest price observed by the market."""
    median_price: float | str
    """The median price observed by the market."""

    def __init__(self, data: PriceOverviewDict, currency: CurrencyCode) -> None:
        lowest_price = PRICE_RE.search(data["lowest_price"])["price"]
        median_price = PRICE_RE.search(data["median_price"])["price"]

        try:
            self.lowest_price = float(lowest_price.replace(",", "."))
            self.median_price = float(median_price.replace(",", "."))
        except ValueError:
            self.lowest_price = lowest_price
            self.median_price = median_price

        self.volume: int = int(data["volume"].replace(",", ""))
        """The number of items sold in the last 24 hours."""
        self.currency = currency

    def __repr__(self) -> str:
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in self.__slots__]
        return f"<PriceOverview {' '.join(resolved)}>"


class Ban:
    """Represents a Steam ban."""

    __slots__ = (
        "since_last_ban",
        "number_of_game_bans",
        "_vac_banned",
        "_community_banned",
        "_market_banned",
    )

    def __init__(self, data: dict[str, Any]):
        self._vac_banned: bool = data["VACBanned"]
        self._community_banned: bool = data["CommunityBanned"]
        self._market_banned: bool = data["EconomyBan"]
        self.since_last_ban = timedelta(days=data["DaysSinceLastBan"])
        """The amount of time that has passed since user was last banned"""
        self.number_of_game_bans: int = data["NumberOfGameBans"]
        """The number of game bans the user has."""

    def __repr__(self) -> str:
        attrs = [
            ("number_of_game_bans", self.number_of_game_bans),
            ("is_vac_banned()", self.is_vac_banned()),
            ("is_community_banned()", self.is_community_banned()),
            ("is_market_banned()", self.is_market_banned()),
        ]
        resolved = [f"{method}={value!r}" for method, value in attrs]
        return f"<Ban {' '.join(resolved)}>"

    def is_banned(self) -> bool:
        """Species if the user is banned from any part of Steam."""
        return any((self.is_vac_banned(), self.is_community_banned(), self.is_market_banned()))

    def is_vac_banned(self) -> bool:
        """Whether or not the user is VAC banned."""
        return self._vac_banned

    def is_community_banned(self) -> bool:
        """Whether or not the user is community banned."""
        return self._community_banned

    def is_market_banned(self) -> bool:
        """Whether or not the user is market banned."""
        return self._market_banned


class StreamReaderProto(Protocol):
    def __aiter__(self) -> AsyncStreamIterator[bytes]:
        ...

    def iter_chunked(self, n: int) -> AsyncStreamIterator[bytes]:
        ...

    def iter_any(self) -> AsyncStreamIterator[bytes]:
        ...

    def iter_chunks(self) -> ChunkTupleAsyncStreamIterator:
        ...

    async def readline(self) -> bytes:
        ...

    async def readuntil(self, separator: bytes = b"\n", /) -> bytes:
        ...

    async def read(self, n: int = -1, /) -> bytes:
        ...

    async def readany(self) -> bytes:
        ...

    async def readchunk(self) -> tuple[bytes, bool]:
        ...

    async def readexactly(self, n: int, /) -> bytes:
        ...

    def read_nowait(self, n: int = -1, /) -> bytes:
        ...


class _IOMixin:
    __slots__ = ()

    if __debug__:

        def __init_subclass__(cls) -> None:
            if cls.open is _IOMixin.open and not getattr(cls, "url", None) and not getattr(cls, "_state", None):
                raise NotImplementedError("Missing required attributes for implicit _IOMixin.open()")

    @asynccontextmanager
    async def open(self, **kwargs: Any) -> AsyncGenerator[StreamReaderProto, None]:
        """Open this file as and returns its contents as an :class:`aiohttp.StreamReader`."""
        url: str = self.url  # type: ignore
        state: ConnectionState = self._state  # type: ignore

        async with state.http._session.get(url) as r:
            yield r.content

    async def read(self, **kwargs: Any) -> bytes:
        """Read the whole contents of this file."""
        async with self.open(**kwargs) as io:
            return await io.read()

    async def save(self, filename: StrOrBytesPath, **kwargs: Any) -> int:
        """Save the file to a path.

        Parameters
        ----------
        filename
            The filename of the file to be created and have this saved to.

        Returns
        -------
        The number of bytes written.
        """
        total = 0
        async with self.open(**kwargs) as file:
            with open(filename, "wb") as actual_fp:
                async for chunk in file.iter_chunked(2048):
                    total += actual_fp.write(chunk)
        return total

    async def media(self, *, spoiler: bool = False, **kwargs: Any) -> Media:
        """Return this file as :class:`Media` for uploading."""
        return Media(BytesIO(await self.read()), spoiler=spoiler)


class Avatar(_IOMixin):
    __slots__ = (
        "sha",
        "_state",
    )

    def __init__(self, state: ConnectionState, sha: bytes):
        sha = bytes(sha)
        self.sha = (
            sha
            if sha != b"\x00" * 20
            else b"\xfe\xf4\x9e\x7f\xa7\xe1\x99s\x10\xd7\x05\xb2\xa6\x15\x8f\xf8\xdc\x1c\xdf\xeb"
        )
        self._state = state

    @property
    def url(self) -> str:
        """The URL of the avatar. Uses the large (184x184 px) image url."""
        return f"https://avatars.cloudflare.steamstatic.com/{self.sha.hex()}_full.jpg"

    def __eq__(self, other: object) -> bool:
        return self.sha == other.sha if isinstance(other, self.__class__) else NotImplemented


@dataclass(slots=True)
class CDNAsset(_IOMixin):
    _state: ConnectionState = field(repr=False)
    url: str = field()
    """The URL of the asset."""

    def __eq__(self, other: object) -> bool:
        return self.url == other.url if isinstance(other, self.__class__) else NotImplemented
