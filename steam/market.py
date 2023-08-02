from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .enums import Currency, PurchaseResult, Realm, Result
from .models import DescriptionMixin
from .trade import Asset, OwnerT

if TYPE_CHECKING:
    from datetime import datetime

    from .state import ConnectionState
    from .types import market

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


class MarketItem(Asset[OwnerT], DescriptionMixin):
    __slots__ = (
        *DescriptionMixin.SLOTS,
        "_state",
        "class_id",
        "instance_id",
        "_app_id",
    )

    def cancel_sell_order():
        ...


class Listing:
    def __init__(self, state: ConnectionState, data: market.Listing):
        self.id = data["id"]


class MyListing:
    id: int
    created_at: datetime


# Client.currency
# Client.get_histogram
# Client.search_for_listings  https://steamcommunity.com/market/search/render/?query=&start=0&count=10&search_descriptions=0&sort_column=popular&sort_dir=desc&appid=730&norender=1
# App.search_for_listings
# Listing -> {id: int, item: MarketItem, buy}
