"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any, Literal, ParamSpec, TypeVar, cast, runtime_checkable

from typing_extensions import Protocol

from ._const import DEFAULT_AVATAR, URL
from .enums import PurchaseResult, Realm, Result
from .media import Media
from .types.id import AppID, ClassID

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from _typeshed import StrOrBytesPath
    from aiohttp.streams import AsyncStreamIterator, ChunkTupleAsyncStreamIterator
    from yarl import URL as _URL

    from .app import PartialApp
    from .enums import Currency
    from .market import PriceOverview
    from .protobufs import econ
    from .state import ConnectionState
    from .types import user


__all__ = (
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


class _IOMixin:
    __slots__ = ()

    if __debug__:

        def __init_subclass__(cls) -> None:
            if cls.open is _IOMixin.open and not hasattr(cls, "url") and not hasattr(cls, "_state"):
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
            with open(filename, "wb") as actual_fp:  # noqa: PTH123
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
        return isinstance(other, self.__class__) and self.sha == other.sha

    def __hash__(self) -> int:
        return hash(self.sha)


@dataclass(slots=True, unsafe_hash=True)
class CDNAsset(_IOMixin):
    _state: ConnectionState = field(repr=False, hash=False)
    url: str = field()
    """The URL of the asset."""


@runtime_checkable
class DescriptionMixin(Protocol):
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
        "_market_fee_app_id",
        "_is_tradable",
        "_is_marketable",
    )
    if not TYPE_CHECKING:
        __slots__ = ()

    _state: ConnectionState
    _app_id: AppID
    class_id: ClassID
    """The classid of the item."""

    def __init__(self, state: ConnectionState, description: econ.ItemDescription):
        self.name = description.market_name
        """The market_name of the item."""
        self.class_id = ClassID(description.classid)
        self.display_name = description.name or self.name
        """
        The displayed name of the item. This could be different to :attr:`Item.name` if the item is user re-nameable.
        """
        self.market_hash_name = description.market_hash_name
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
        return await self._state.client.fetch_price(self.market_hash_name, self.app, currency)

    async def name_id(self) -> int:
        listing = await self.listing()
        return listing.item._name_id

    async def listings(self):
        return await self._state.client.fetch_listings(self.market_hash_name, self.app)

    async def histogram(self, name_id: int | None = None):
        ...

    @property
    def app(self) -> PartialApp[None]:
        """The app the item is from."""
        from .app import PartialApp

        return PartialApp(self._state, id=self._app_id)

    @property
    def market_fee_app(self) -> PartialApp[None]:
        """The app for which the Steam Community Market fee percentage is applied."""
        from .app import PartialApp

        return PartialApp(self._state, id=self._market_fee_app_id)
