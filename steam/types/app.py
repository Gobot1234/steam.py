"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class UserRecentlyPlayedApp(TypedDict):
    name: str
    appid: int
    playtime_2weeks: int
    playtime_forever: int
    img_icon_url: str


class WishlistApp(TypedDict):
    name: str
    capsule: str
    review_score: int
    review_desc: str
    reviews_total: str
    reviews_percent: int
    release_date: str | None  # really an int/float (sometimes)
    release_string: str
    platform_icons: str
    subs: list[WishlistAppSub]
    type: str
    screenshots: list[str]
    review_css: str
    priority: int
    added: int
    background: str
    rank: int
    tags: list[str]
    is_free_game: bool
    win: bool
    mac: bool
    linux: bool


class WishlistAppSub(TypedDict):
    packageid: int
    bundleid: int
    discount_block: str
    discount_pct: int
    price: int


class PackageGroups(TypedDict):
    name: Literal["default", "subscriptions"]
    title: str
    description: str
    selection_text: str
    display_type: Literal[0, 1]
    is_recurring_subscription: bool
    subs: list[PackageGroupSub]


class PackageGroupSub(TypedDict):
    packageid: int
    percent_savings_text: str
    percent_savings: int
    option_text: str
    option_description: str
    can_get_free_license: str
    is_free_license: bool
    price_in_cents_with_discount: int


class FetchedAppPriceOverview(TypedDict):
    currency: str
    initial: int
    final: int
    discount_percent: int
    initial_formatted: str
    final_formatted: str


class FetchedAppCategory(TypedDict):
    id: int
    description: str


class FetchedApp(TypedDict):
    # https://wiki.teamfortress.com/wiki/User:RJackson/StorefrontAPI#Result_data_3
    type: Literal["game", "dlc", "demo", "advertising", "mod", "video"]
    name: str
    steam_appid: int
    required_age: int
    is_free: bool
    controller_support: Literal["partial", "full"]
    dlc: list[int]
    detailed_description: str
    short_description: str
    fullgame: NotRequired[dict[str, Any]]
    supported_languages: str
    header_image: str
    pc_requirements: list[dict[str, str]]
    mac_requirements: list[dict[str, str]]
    linux_requirements: list[dict[str, str]]
    legal_notice: str
    developers: list[str]
    publishers: list[str]
    demos: list[dict[str, Any]]
    price_overview: FetchedAppPriceOverview
    packages: list[int]
    package_groups: list[PackageGroups]
    platforms: dict[str, bool]
    metacritic: list[dict[str, str]]
    categories: list[FetchedAppCategory]
    release_date: dict[str, str]
    background: str
    website: str
    movies: list[dict[str, Any]]
    content_descriptors: dict[str, list[int]]  # a lie but who cares the "notes" key isn't useful


class DLCPriceOverview(TypedDict):
    currency: str
    initial: int
    final: int
    discount_percent: int


class DLCPlatforms(TypedDict):
    windows: bool
    mac: bool
    linux: bool


class DLCReleaseDate(TypedDict):
    steam: str  # unix timestamps
    mac: str
    linux: str


class DLC(TypedDict):
    id: int
    name: str
    header_image: str
    price_overview: DLCPriceOverview
    platforms: DLCPlatforms
    release_date: DLCReleaseDate


class Leaderboard(TypedDict):
    id: int
    name: str
    display_name: str
    entry_count: int
    sort_method: int
    display_type: int


class GetAppList(TypedDict):
    apps: list[AppListApp]
    have_more_results: bool
    last_appid: int


class AppListApp(TypedDict):
    appid: int
    name: str
    last_modified: int
    price_change_number: int


class AssetPricesAsset(TypedDict("", {"class": list[dict[str, Any]]})):
    prices: dict[str, int]  # CurrencyCode.name => price in base denomination (£1.54 == 154)
    original_prices: NotRequired[dict[str, int]]
    name: str  # really the def_index?
    date: str  # the time the item's price was last changed?
    classid: str
    tags: NotRequired[list[str]]
    tag_ids: NotRequired[list[int]]


class AssetPrices(TypedDict):
    success: bool
    assets: list[AssetPricesAsset]
    tags: NotRequired[dict[str, str]]
    tag_ids: NotRequired[dict[int, int]]  # only use .values()
