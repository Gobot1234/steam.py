"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Required, TypedDict

from .trade import Item

if TYPE_CHECKING:
    from .trade import ItemAction, ItemDescriptionLine


class PriceOverview(TypedDict):
    success: bool
    lowest_price: str
    median_price: str
    volume: str


class ListingAsset(TypedDict, total=False):
    currency: int
    id: str
    amount: Required[int]
    appid: Required[str]
    contextid: Required[str]
    instanceid: Required[str]
    classid: Required[str]
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
    market_hash_name: Required[str]
    market_tradeable_restriction: int
    market_marketable_restriction: int
    commodity: bool
    marketable: bool
    owner_descriptions: list[ItemDescriptionLine]
    owner_actions: list[ItemAction]
    market_fee: int
    market_fee_app: int
    market_actions: list[ItemAction]
    market_tradable_restriction: int
    # extra fields
    status: Required[str]
    original_amount: str
    unowned_id: str
    unowned_contextid: str
    owner: bool
    rollback_new_id: str
    rollback_new_contextid: str
    new_id: str
    new_contextid: str


class _Listings(TypedDict):
    success: bool
    start: int
    pagesize: int
    total_count: int
    results_html: str
    listinginfo: dict[str, _ListingInfo]
    assets: dict[str, dict[str, dict[str, _SearchAssetDescription]]]
    currency: list[Any]
    hovers: str
    app_data: AppData


class _Listing(TypedDict):
    listingid: str
    price: int
    fee: int
    publisher_fee_app: int
    publisher_fee_percent: str
    currencyid: int
    asset: dict[{"currency": int, "appid": int, "contextid": str, "id": str, "amount": str}]  # noqa: F821, UP037


_ListingPriceHistory = tuple[str, float, str]  # date (%b %d %Y (snapshot number): %z), avg price, quantity
# e.g. ["Dec 12 2012 01: +0", 1.202, "4719"]
ListingPriceHistory = tuple[datetime, int, float, int]


class ListingItem(Item, total=False):
    appid: str
    status: str
    original_amount: str
    unowned_id: str
    unowned_contextid: str
    owner: bool
    rollback_new_id: str
    rollback_new_contextid: str
    new_id: str
    new_contextid: str


class Listing(TypedDict):
    id: int
    price: int
    fee: int  # might be able to stick these on the item
    publisher_fee_app: int
    publisher_fee_percent: float  # make sure to round()
    currency_id: int
    item: ListingItem


class _Filter(TypedDict):
    appid: int
    name: str
    localized_name: str
    tags: dict[str, dict[{"localized_name": str, "matches": str}]]  # noqa: F821, UP037


class Filter(TypedDict):
    name: str
    display_name: str
    tags: list[dict[{"name": str, "display_name": str, "matches": int}]]  # noqa: F821, UP037


class AppFilters(TypedDict):
    success: bool
    facets: dict[str, _Filter]


SortBy = Literal["popular", "name", "quantity", "price"]


class _Search(TypedDict):
    success: bool
    start: int
    pagesize: int
    total_count: int
    searchdata: _SearchData
    results: list[_SearchResult]


class _SearchData(TypedDict):
    query: str
    search_descriptions: bool
    total_count: int
    pagesize: int
    prefix: str
    class_prefix: str


class _SearchResult(TypedDict):
    name: str
    hash_name: str
    sell_listings: int
    sell_price: int
    sell_price_text: str
    app_icon: str
    app_name: str
    asset_description: _SearchAssetDescription
    sale_price_text: str


class _SearchAssetDescription(TypedDict):
    appid: int
    classid: str
    instanceid: str
    background_color: str
    icon_url: str
    name: str
    name_color: str
    type: str
    market_name: str
    market_hash_name: str
    tradable: bool
    commodity: bool


class SearchResult(TypedDict):
    name: str
    sell_listings: int
    sell_price: int
    app_name: str
    sale_price_text: str
    appid: int
    classid: str
    instanceid: str
    background_color: str
    icon_url: str
    name_color: str
    type: str
    market_name: str
    market_hash_name: str
    tradable: bool
    commodity: bool


class _ListingInfo(TypedDict):
    listingid: str
    price: int
    fee: int
    publisher_fee_app: int
    publisher_fee_percent: str
    currencyid: int
    steam_fee: int
    publisher_fee: int
    converted_price: int
    converted_fee: int
    converted_currencyid: int
    converted_steam_fee: int
    converted_publisher_fee: int
    converted_price_per_unit: int
    converted_fee_per_unit: int
    converted_steam_fee_per_unit: int
    converted_publisher_fee_per_unit: int
    asset: Asset


class Asset(TypedDict):
    currency: int
    appid: int
    contextid: str
    id: str
    amount: str
    market_actions: list[dict[{"link": str, "name": str}]]  # noqa: UP037, F821


class AppData(TypedDict):
    appid: int
    name: str
    icon: str
    link: str
