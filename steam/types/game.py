"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import Any

from typing_extensions import Literal, TypedDict


class GetOwnedGames(TypedDict):
    games: list[GetOwnedGamesGame]


class GetOwnedGamesGame(TypedDict):
    name: str
    appid: str
    playtime_forever: int
    img_icon_url: str
    has_community_visible_stats: bool


class GameToDict(TypedDict, total=False):
    game_id: str
    game_extra_info: str


class WishlistGame(TypedDict):
    name: str
    capsule: str
    review_score: int
    review_desc: str
    reviews_total: str
    reviews_percent: int
    release_date: int
    release_string: str
    platform_icons: str
    subs: list[dict[str, Any]]
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


class FetchedGamePriceOverview(TypedDict):
    currency: str
    initial: int
    final: int
    discount_percent: int
    initial_formatted: str
    final_formatted: str


class FetchedGame(TypedDict):
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
    fullgame: dict[str, Any]
    supported_languages: str
    header_image: str
    pc_requirements: list[dict[str, str]]
    mac_requirements: list[dict[str, str]]
    linux_requirements: list[dict[str, str]]
    legal_notice: str
    developers: list[str]
    publishers: list[str]
    demos: list[dict[str, Any]]
    price_overview: FetchedGamePriceOverview
    packages: list[int]
    package_groups: list[PackageGroups]
    platforms: dict[str, bool]
    metacritic: list[dict[str, str]]
    categories: list[dict[str, str]]
    release_date: dict[str, str]
    background: str
    website: str
    movies: list[dict[str, Any]]


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
