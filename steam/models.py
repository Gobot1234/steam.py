"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, Protocol, TypedDict, TypeVar, cast

from aiohttp.streams import AsyncStreamIterator, ChunkTupleAsyncStreamIterator
from yarl import URL as _URL

from . import utils
from ._const import DEFAULT_AVATAR, URL
from .enums import CurrencyCode, PurchaseResult, Realm, Result
from .media import Media

if TYPE_CHECKING:
    from _typeshed import StrOrBytesPath

    from .state import ConnectionState
    from .types import user


__all__ = (
    "PriceOverview",
    "Ban",
    "Avatar",
    "Wallet",
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

    def __init__(self, data: user.UserBan):
        self._vac_banned = data["vac_banned"]
        self._community_banned = data["community_banned"]
        self._market_banned = data["economy_ban"] != "none"
        self.since_last_ban = timedelta(days=data["days_since_last_ban"])
        """The amount of time that has passed since user was last banned"""
        self.number_of_game_bans: int = data["number_of_game_bans"]
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
        url = cast(str, self.url)  # type: ignore
        state = cast("ConnectionState", self._state)  # type: ignore

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
        self.sha = sha if sha != b"\x00" * 20 else DEFAULT_AVATAR
        self._state = state

    @property
    def url(self) -> str:
        """The URL of the avatar. Uses the large (184x184 px) image URL."""
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


@dataclass(slots=True)
class Wallet:
    _state: ConnectionState
    balance: int
    """The balance of your wallet in its base most currency denomination.

    E.g. $3.45 -> 345
    """
    currency: CurrencyCode
    """The currency the balance is in."""
    balance_delayed: int
    """Your delayed balance if Steam is refunding something?"""
    realm: Realm
    """The realm this wallet is for."""

    async def add(self, code: str) -> int:
        """Add a wallet code to your wallet.

        Parameters
        ----------
        code
            The wallet code to redeem.

        Returns
        -------
        The balance added to your account.
        """
        self._state.handled_wallet.clear()
        resp = await self._state.http.add_wallet_code(code)
        result = Result.try_value(resp["success"])
        if result != Result.OK:
            raise ValueError(
                f"Activation of code failed with result {result} {PurchaseResult.try_value(resp['detail'])!r}"
            )
        await self._state.handled_wallet.wait()
        return resp["amount"]
