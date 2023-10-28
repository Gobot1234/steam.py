"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

from typing_extensions import TypeVar

from .enums import Currency, PurchaseResult, Realm, Result
from .models import DescriptionMixin
from .protobufs import econ
from .trade import Asset, Item
from .types.id import ListingID

if TYPE_CHECKING:
    from datetime import datetime

    from .abc import PartialUser
    from .state import ConnectionState
    from .types import market
    from .user import ClientUser

__all__ = (
    "PriceOverview",
    "Wallet",
)

PRICE_RE = re.compile(r"(^\D*(?P<price>[\d,.]*)\D*$)")


class PriceOverview:
    """Represents the data received from the Steam Community Market."""

    __slots__ = ("currency", "volume", "lowest_price", "median_price")

    lowest_price: float | str
    """The lowest price observed by the market."""
    median_price: float | str
    """The median price observed by the market."""

    def __init__(self, data: market.PriceOverview, currency: Currency) -> None:
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


class PriceHistory(NamedTuple):
    date: datetime
    snapshot_number: int
    average_price: float
    quantity: int


class MarketBuySellInfo(NamedTuple):
    class Entry(NamedTuple):
        price: float
        number: int

    buys: Entry
    sells: Entry


OwnerT = TypeVar("OwnerT", bound="PartialUser | None", default=None, covariant=True)


class MarketItem(Asset[OwnerT], DescriptionMixin):
    __slots__ = (
        *DescriptionMixin.SLOTS,
        "_state",
        "_name_id",
    )

    def __init__(self, state: ConnectionState, data: market.ListingItem, owner: OwnerT = None):
        super().__init__(state, econ.Asset().from_dict(data), owner)
        DescriptionMixin.__init__(self, state, econ.ItemDescription().from_dict(data))

    async def histogram(self, name_id: int | None = None) -> list[MarketBuySellInfo]:
        return await self._state.client.fetch_histogram(
            self.market_hash_name, self.app, name_id or await self.name_id()
        )


class Listing:
    def __init__(self, state: ConnectionState, data: market.Listing):
        self.id = ListingID(data["id"])
        self.item = MarketItem(state, data["item"])

    async def buy(self) -> Item[ClientUser]:
        ...


class MyListing:
    def __init__(self, state: ConnectionState, data: market.Listing):
        self.id = ListingID(data["id"])
        self.item = MarketItem(state, data["item"], state.user)
        self.created_at: datetime


class MarketSearchItem(DescriptionMixin):
    def __init__(self, state: ConnectionState, data: market.SearchResult) -> None:
        self._state = state
        self.sell_listings = data["sell_listings"]
        """The number of sell listings for the item"""
        self.sell_price = data["sell_price"]
        """The lowest sell price for the item."""
        super().__init__(state, econ.ItemDescription().from_dict(data))
