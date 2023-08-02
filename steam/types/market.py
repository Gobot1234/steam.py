from datetime import datetime
from typing import TypedDict

from .trade import AssetToDict, ItemAction, ItemDescriptionLine


class PriceOverview(TypedDict):
    success: bool
    lowest_price: str
    median_price: str
    volume: str


class ListingAsset(TypedDict):
    currency: int
    id: str
    amount: str
    appid: str
    contextid: str
    instanceid: str
    classid: str
    status: str
    original_amount: str
    unowned_id: str
    unowned_contextid: str
    background_color: str
    icon_url: str
    icon_url_large: str
    descriptions: list[ItemDescriptionLine]
    tradable: bool  # 1 vs 0
    actions: list[ItemAction]
    name: str
    name_color: str
    type: str
    market_name: str
    market_hash_name: str
    market_tradeable_restriction: int
    market_marketable_restriction: int
    commodity: bool
    marketable: bool
    owner: bool


class _Listing(TypedDict):
    listingid: str
    price: int
    fee: int
    publisher_fee_app: int
    publisher_fee_percent: str
    currencyid: int
    asset: dict[{"currency": int, "appid": int, "contextid": str, "id": str, "amount": str}]  # noqa: F821


_ListingPriceHistory = tuple[str, float, str]  # date (%b %d %Y (snapshot number): %z), avg price, quantity
# e.g. ["Dec 12 2012 01: +0", 1.202, "4719"]
ListingPriceHistory = tuple[datetime, int, float, int]


class ListingItem(ListingAsset):
    name_id: int


class Listing(TypedDict):
    id: int
    price: int
    fee: int  # might be able to stick these on the item
    publisher_fee_app: int
    publisher_fee_percent: float  # make sure to round()
    currency_id: int
    price_history: list[ListingPriceHistory]
    item: ListingItem
