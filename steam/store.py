"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import TYPE_CHECKING

from yarl import URL as URL_

from ._const import URL
from .app import PartialApp
from .bundle import PartialBundle
from .clan import PartialClan
from .enums import AppType, ContentDescriptor, Currency, Language, PaymentMethod, ReviewType
from .models import CDNAsset
from .package import PartialPackage
from .protobufs import store
from .tag import Category, Tag
from .utils import DateTime

if TYPE_CHECKING:
    from datetime import datetime

    from .state import ConnectionState

__all__ = (
    "StoreItem",
    "AppStoreItem",
    "PackageStoreItem",
    "BundleStoreItem",
    "TransactionReceipt",
)


class StoreItemTag(Tag[None]):
    __slots__ = ("weight",)

    def __init__(self, state: ConnectionState, id: int, weight: int):
        super().__init__(state, id)
        self.weight = weight


@dataclass(slots=True)
class StoreItemCreatorHomeLink:
    name: str
    clan: PartialClan


@dataclass(slots=True)
class StoreItemPurchaseOptionDiscount:
    amount: int
    description: str
    ends_at: datetime


class StoreItemPurchaseOption:
    __slots__ = (
        "package",
        "bundle",
        "final_price_in_cents",
        "original_price_in_cents",
        "user_final_price_in_cents",
        "formatted_final_price",
        "formatted_original_price",
        "discount_percentage",
        "user_discount_percentage",
        "bundle_discount_percentage",
        "active_discounts",
        "user_active_discounts",
        "inactive_discounts",
        "user_can_purchase",
        "user_can_purchase_as_gift",
        "is_commercial_license",
        "should_suppress_discount_percentage",
    )

    def __init__(self, state: ConnectionState, proto: store.StoreItemPurchaseOption) -> None:
        self.package = PartialPackage(state, id=proto.packageid) if proto.packageid else None
        self.bundle = PartialBundle(state, id=proto.bundleid) if proto.bundleid else None
        self.final_price_in_cents: int = proto.final_price_in_cents
        self.original_price_in_cents: int = proto.original_price_in_cents
        self.user_final_price_in_cents: int = proto.user_final_price_in_cents
        self.formatted_final_price: str = proto.formatted_final_price
        self.formatted_original_price: str = proto.formatted_original_price
        self.discount_percentage: int = proto.discount_pct
        self.user_discount_percentage: int = proto.user_discount_pct
        self.bundle_discount_percentage: int = proto.bundle_discount_pct
        self.active_discounts: list[StoreItemPurchaseOptionDiscount] = [
            StoreItemPurchaseOptionDiscount(
                discount.discount_amount,
                discount.discount_description,
                DateTime.from_timestamp(discount.discount_end_date),
            )
            for discount in proto.active_discounts
        ]
        self.user_active_discounts: list[StoreItemPurchaseOptionDiscount] = [
            StoreItemPurchaseOptionDiscount(
                discount.discount_amount,
                discount.discount_description,
                DateTime.from_timestamp(discount.discount_end_date),
            )
            for discount in proto.user_active_discounts
        ]
        self.inactive_discounts: list[StoreItemPurchaseOptionDiscount] = [
            StoreItemPurchaseOptionDiscount(
                discount.discount_amount,
                discount.discount_description,
                DateTime.from_timestamp(discount.discount_end_date),
            )
            for discount in proto.inactive_discounts
        ]
        self.user_can_purchase: bool = proto.user_can_purchase
        self.user_can_purchase_as_gift: bool = proto.user_can_purchase_as_gift
        self.is_commercial_license: bool = proto.is_commercial_license
        self.should_suppress_discount_percentage: bool = proto.should_suppress_discount_pct


@dataclass(slots=True)
class LanguageSupport:
    language: Language
    supported: bool
    audio: bool
    subtitles: bool


class StoreItem:
    __slots__ = SLOTS = (  # done to avoid "multiple bases have instance lay-out conflict"
        "_language",
        "hidden",
        "unavailable_for_country_restriction",
        "_apps",
        "created_at",
        "type",
        "included_types",
        "related_parent_app",
        "tags",
        "categories",
        "review_score",
        "review_count",
        "review_percent_positive",
        "filtered_review_score",
        "filtered_review_count",
        "filtered_review_percent_positive",
        "summary",
        "capsule_headline",
        "publishers",
        "developers",
        "franchises",
        "small_capsule",
        "header",
        "package_header",
        "page_background",
        "hero_capsule",
        "library_capsule",
        "library_hero",
        "community_icon",
        "vr_support",
        "game_rating",
        "best_purchase_option",
        "purchase_options",
        "accessories",
        "all_ages_screenshots",
        "mature_screenshots",
        "trailers",
        "supported_languages",
        "free_weekend",
        "content_descriptors",
        "_free",
        "_early_access",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
    )
    if not TYPE_CHECKING:
        __slots__ = ()

    def __init__(self, state: ConnectionState, proto: store.StoreItem, language: Language) -> None:
        super().__init__(state, id=proto.id, name=proto.name)  # type: ignore  # this is a mixin
        self._language = language
        self.hidden = not proto.visible
        self.unavailable_for_country_restriction = proto.unvailable_for_country_restriction
        self._apps = [PartialApp(state, id=id) for id in proto.included_appids]
        self.created_at = DateTime.from_timestamp(proto.release.steam_release_date)
        proto.type = store.EStoreAppType(proto.type)  # TODO remove when enum redux pr is merged
        try:
            self.type = AppType[proto.type.name]
        except KeyError:
            self.type = AppType.try_value(proto.type)  # should be good enough
        self.included_types: list[AppType] = []
        for included_type in proto.included_types:
            included_type = store.EStoreAppType(included_type)  # TODO remove when enum redux pr is merged
            try:
                self.included_types.append(AppType[included_type.name])
            except KeyError:
                self.included_types.append(AppType.try_value(included_type))

        self.related_parent_app = PartialApp(state, id=proto.related_items.parent_appid)
        self.tags = [StoreItemTag(state, tag.tagid, tag.weight) for tag in proto.tags]
        self.categories = [Category(state, id) for id in proto.categories.feature_categoryids]
        self.review_score = ReviewType.try_value(proto.reviews.summary_unfiltered.review_score)
        self.review_count = proto.reviews.summary_unfiltered.review_count
        self.review_percent_positive = proto.reviews.summary_unfiltered.percent_positive
        self.filtered_review_score = ReviewType.try_value(proto.reviews.summary_filtered.review_score)
        self.filtered_review_count = proto.reviews.summary_filtered.review_count
        self.filtered_review_percent_positive = proto.reviews.summary_filtered.percent_positive

        self.summary = proto.basic_info.short_description
        self.capsule_headline = proto.basic_info.capsule_headline
        self.publishers = [
            StoreItemCreatorHomeLink(name=link.name, clan=PartialClan(state, id=link.creator_clan_account_id))
            for link in proto.basic_info.publishers
        ]
        self.developers = [
            StoreItemCreatorHomeLink(name=link.name, clan=PartialClan(state, id=link.creator_clan_account_id))
            for link in proto.basic_info.developers
        ]
        self.franchises = [
            StoreItemCreatorHomeLink(name=link.name, clan=PartialClan(state, id=link.creator_clan_account_id))
            for link in proto.basic_info.franchises
        ]

        base_url = string.Template(f"{URL.CDN}/{proto.assets.asset_url_format}")
        capsule = proto.assets.main_capsule or proto.assets.small_capsule or None
        self.small_capsule = CDNAsset(state, base_url.substitute(FILENAME=capsule)) if capsule else None
        self.header = (
            CDNAsset(state, base_url.substitute(FILENAME=proto.assets.header)) if proto.assets.header else None
        )
        self.package_header = (
            CDNAsset(state, base_url.substitute(FILENAME=proto.assets.package_header))
            if proto.assets.package_header
            else None
        )
        self.page_background = (
            CDNAsset(state, base_url.substitute(FILENAME=proto.assets.page_background))
            if proto.assets.page_background
            else None
        )
        hero_capsule = proto.assets.hero_capsule_2_x or proto.assets.hero_capsule or None
        self.hero_capsule = CDNAsset(state, base_url.substitute(FILENAME=hero_capsule)) if hero_capsule else None
        library_capsule = proto.assets.library_capsule_2_x or proto.assets.library_capsule or None
        self.library_capsule = (
            CDNAsset(state, base_url.substitute(FILENAME=library_capsule)) if library_capsule else None
        )
        library_hero = proto.assets.library_hero_2_x or proto.assets.library_hero or None
        self.library_hero = CDNAsset(state, base_url.substitute(FILENAME=library_hero)) if library_hero else None
        community_icon = URL_(base_url.substitute(FILENAME=proto.assets.community_icon))
        self.community_icon = (
            CDNAsset(state, str(community_icon) if community_icon.suffix else f"{community_icon}.jpg")
            if proto.assets.community_icon
            else None
        )  # this doesn't seem to have an extension in the normal case

        self.vr_support = proto.platforms.vr_support
        self.game_rating = proto.game_rating

        self.best_purchase_option = StoreItemPurchaseOption(state, proto.best_purchase_option)
        self.purchase_options = [
            StoreItemPurchaseOption(state, purchase_option) for purchase_option in proto.purchase_options
        ]
        self.accessories = [StoreItemPurchaseOption(state, purchase_option) for purchase_option in proto.accessories]
        self.all_ages_screenshots = [
            CDNAsset(state, str(URL.CDN / proto.filename)) for proto in proto.screenshots.all_ages_screenshots
        ]
        self.mature_screenshots = [
            CDNAsset(state, str(URL.CDN / proto.filename)) for proto in proto.screenshots.mature_content_screenshots
        ]
        self.trailers = proto.trailers
        self.supported_languages = [
            LanguageSupport(Language.try_value(proto.elanguage), proto.supported, proto.full_audio, proto.subtitles)
            for proto in proto.supported_languages
        ]
        self.free_weekend = proto.free_weekend or None

        self.content_descriptors = [ContentDescriptor.try_value(d) for d in proto.content_descriptorids]

        self._free = proto.is_free
        self._early_access = proto.is_early_access
        self._on_windows = proto.platforms.windows
        self._on_mac_os = proto.platforms.mac
        self._on_linux = proto.platforms.steamos_linux

    def is_free(self) -> bool:
        """Whether the store item is free to play."""
        return self._free

    def is_early_access(self) -> bool:
        """Whether the store item is in early access."""
        return self._early_access

    def is_on_windows(self) -> bool:
        """Whether the store item is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the store item is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the store item is playable on Linux."""
        return self._on_linux


class AppStoreItem(StoreItem, PartialApp[str]):
    """Represents an app fetched from the store."""

    __slots__ = StoreItem.SLOTS


class PackageStoreItem(StoreItem, PartialPackage[str]):
    """Represents a package fetched from the store."""

    __slots__ = StoreItem.SLOTS


class BundleStoreItem(StoreItem, PartialBundle[str]):
    """Represents a bundle fetched from the store."""

    __slots__ = StoreItem.SLOTS


@dataclass(slots=True)
class TransactionReceiptItem:
    package: PartialPackage[str] | None
    """The package that was purchased."""
    app: PartialApp[str] | None
    """The app that was purchased."""


class TransactionReceipt:
    """Represents a transaction receipt."""

    def __init__(self, state: ConnectionState, proto: store.PurchaseReceiptInfo):
        self.id = proto.transactionid
        """The ID of the transaction."""
        self.items = [
            TransactionReceiptItem(
                PartialPackage(state, id=item.packageid, name=item.line_item_description) if item.packageid else None,
                PartialApp(state, id=item.appid, name=item.line_item_description) if item.appid else None,
            )
            for item in proto.line_items
        ]  # TODO research if this is a union?
        """The items in the transaction."""

        self.package = PartialPackage(state, id=proto.packageid)  # TODO can this be upgraded to a License?
        """The package in the transaction."""
        self.purchase_status = proto.purchase_status
        """The status of the transaction."""
        self.created_at = DateTime.from_timestamp(proto.transaction_time)
        """The time the transaction was created."""
        self.payment_method = PaymentMethod.try_value(proto.payment_method)
        """The payment method used for the transaction."""
        self.base_price = proto.base_price
        """The base price of the transaction."""
        self.total_discount = proto.total_discount
        """The total discount of the transaction."""
        self.tax = proto.tax
        """The tax of the transaction."""
        self.shipping = proto.shipping
        """The shipping cost of the transaction."""
        self.currency = Currency.try_value(proto.currency_code)
        """The currency code of the transaction."""
        self.language = Language.from_web_api_str(proto.country_code)
        """The country code of the transaction."""
