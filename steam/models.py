"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
import re
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypedDict, TypeVar, runtime_checkable

from typing_extensions import Protocol

from ._const import DEFAULT_AVATAR, URL, ReadOnly
from .enums import Currency, PurchaseResult, Realm, Result
from .media import Media
from .types.id import AppID, ClassID

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from _typeshed import StrOrBytesPath
    from aiohttp.streams import AsyncStreamIterator, ChunkTupleAsyncStreamIterator
    from yarl import URL as _URL

    from .app import PartialApp
    from .protobufs import econ
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
    """Represents the data received from the Steam Community Market."""

    __slots__ = ("currency", "volume", "lowest_price", "median_price")

    lowest_price: float | str
    """The lowest price observed by the market."""
    median_price: float | str
    """The median price observed by the market."""

    def __init__(self, data: PriceOverviewDict, currency: Currency) -> None:
        lowest_price_ = PRICE_RE.search(data["lowest_price"])
        median_price_ = PRICE_RE.search(data["median_price"])
        assert lowest_price_ is not None
        assert median_price_ is not None
        lowest_price = lowest_price_["price"]
        median_price = median_price_["price"]

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
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"


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
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

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


@runtime_checkable
class _IOMixinNoOpen(Protocol):
    __slots__ = ()

    @abc.abstractmethod
    def open(self) -> AbstractAsyncContextManager[StreamReaderProto]:
        raise NotImplementedError

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
            with open(filename, "wb") as actual_fp:  # noqa: PTH123
                async for chunk in file.iter_chunked(2048):
                    total += actual_fp.write(chunk)
        return total

    async def media(self, *, spoiler: bool = False, **kwargs: Any) -> Media:
        """Return this file as :class:`Media` for uploading."""
        return Media(BytesIO(await self.read()), spoiler=spoiler)


@runtime_checkable
class _IOMixin(_IOMixinNoOpen, Protocol):
    __slots__ = ()
    _state: ConnectionState
    url: ReadOnly[str]

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[StreamReaderProto, None]:
        async with self._state.http._session.get(self.url) as r:
            yield r.content


class Avatar(_IOMixin):
    __slots__ = (
        "sha",
        "_suffix",
        "_state",
    )

    def __init__(self, state: ConnectionState, sha: bytes, suffix: str = "full"):
        sha = bytes(sha)
        self.sha = sha if sha != b"\x00" * 20 else DEFAULT_AVATAR
        self._state = state
        self._suffix = suffix

    @property
    def url(self) -> str:
        """The URL of the avatar. Uses the large (184x184 px) image URL."""
        return f"https://avatars.cloudflare.steamstatic.com/{self.sha.hex()}_{self._suffix}.jpg"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self.sha == other.sha

    def __hash__(self) -> int:
        return hash(self.sha)


@dataclass(slots=True, unsafe_hash=True)
class CDNAsset(_IOMixin):
    _state: ConnectionState = field(repr=False, hash=False)
    url: ReadOnly[str] = field()
    """The URL of the asset."""


@dataclass(slots=True)
class Wallet:
    _state: ConnectionState
    balance: int
    """The balance of your wallet in its base most currency denomination.

    E.g. $3.45 -> 345
    """
    currency: Currency
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

        Raises
        ------
        ValueError
            The code was invalid.

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


@runtime_checkable
class AssetMixin(Protocol):
    __slots__ = (
        "_state",
        "_app_id",
        "class_id",
    )

    _state: ConnectionState
    _app_id: AppID
    class_id: ClassID
    """The classid of the item."""

    @property
    def app(self) -> PartialApp[None]:
        """The app the item is from."""
        from .app import PartialApp

        return PartialApp(self._state, id=self._app_id)


@runtime_checkable
class DescriptionMixin(AssetMixin, Protocol):
    __slots__ = SLOTS = (
        "name",
        "type",
        "tags",
        "colour",
        "icon",
        "display_name",
        "market_hash_name",
        "descriptions",
        "owner_descriptions",
        "fraud_warnings",
        "actions",
        "owner_actions",
        "market_actions",
        "market_fee",
        "_market_fee_app_id",
        "_is_tradable",
        "_is_marketable",
    )
    if not TYPE_CHECKING:
        __slots__ = ()

    _app_id: AppID
    class_id: ClassID

    def __init__(self, state: ConnectionState, description: econ.ItemDescription):
        self.name = description.market_name
        """The market_name of the item."""
        self.display_name = description.name or self.name
        """
        The displayed name of the item. This could be different to :attr:`Item.name` if the item is user re-nameable.
        """
        self.market_hash_name = description.market_hash_name or self.name or self.display_name
        """The market_hash_name of the item."""
        self.colour = int(description.name_color, 16) if description.name_color else None
        """The colour of the item."""
        self.descriptions = description.descriptions
        """The descriptions of the item."""
        self.owner_descriptions = description.owner_descriptions
        """The descriptions of the item which are visible only to the owner of the item."""
        self.type = description.type
        """The type of the item."""
        self.tags = description.tags
        """The tags of the item."""
        icon_url = description.icon_url_large or description.icon_url
        self.icon = (
            CDNAsset(state, f"https://community.cloudflare.steamstatic.com/economy/image/{icon_url}")
            if icon_url
            else None
        )
        """The icon url of the item. Uses the large image url where possible."""
        self.fraud_warnings = description.fraudwarnings
        """The fraud warnings for the item."""
        self.actions = description.actions
        """The actions for the item."""
        self.owner_actions = description.owner_actions
        """The owner actions for the item."""
        self.market_actions = description.market_actions
        """The market actions for the item."""
        self.market_fee = (
            int(float(description.market_fee) * 100) if description.market_fee else 10
        )  # if steam ever support currencies that have more than 2 decimals we're screwed
        """The market fee percentage for the item."""
        self._app_id = AppID(description.appid)
        self._market_fee_app_id = AppID(description.market_fee_app)
        self._is_tradable = description.tradable
        self._is_marketable = description.marketable

    def is_tradable(self) -> bool:
        """Whether the item is tradable."""
        return self._is_tradable

    def is_marketable(self) -> bool:
        """Whether the item is marketable."""
        return self._is_marketable

    async def price(self, *, currency: Currency | None = None) -> PriceOverview:
        """Fetch the price of this item on the Steam Community Market place.

        Shorthand for:

        .. code:: python

            await client.fetch_price(item.market_hash_name, item.app, currency)
        """
        price = await self._state.http.get_price(self._app_id, self.market_hash_name, currency)
        return PriceOverview(price, currency or Currency.USD)

    @property
    def market_fee_app(self) -> PartialApp[None]:
        """The app for which the Steam Community Market fee percentage is applied."""
        from .app import PartialApp

        return PartialApp(self._state, id=self._market_fee_app_id)
