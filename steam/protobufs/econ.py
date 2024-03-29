# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: steammessages_econ.steamclient.proto
# plugin: python-betterproto
# Last updated 09/09/2021

from dataclasses import dataclass

import betterproto

from .msg import UnifiedMessage


@dataclass(eq=False, repr=False)
class GetInventoryItemsWithDescriptionsRequestFilterOptions(betterproto.Message):
    assetids: list[int] = betterproto.uint64_field(1)
    currencyids: list[int] = betterproto.uint32_field(2)
    tradable_only: bool = betterproto.bool_field(3)
    marketable_only: bool = betterproto.bool_field(4)


class GetInventoryItemsWithDescriptionsRequest(UnifiedMessage, um_name="Econ.GetInventoryItemsWithDescriptions"):
    steamid: int = betterproto.fixed64_field(1)
    appid: int = betterproto.uint32_field(2)
    contextid: int = betterproto.uint64_field(3)
    get_descriptions: bool = betterproto.bool_field(4)
    for_trade_offer_verification: bool = betterproto.bool_field(10)
    language: str = betterproto.string_field(5)
    filters: GetInventoryItemsWithDescriptionsRequestFilterOptions = betterproto.message_field(6)
    start_assetid: int = betterproto.uint64_field(8)
    count: int = betterproto.int32_field(9)


@dataclass(eq=False, repr=False)
class Asset(betterproto.Message):
    appid: int = betterproto.uint32_field(1)
    contextid: int = betterproto.uint64_field(2)
    assetid: int = betterproto.uint64_field(3)
    classid: int = betterproto.uint64_field(4)
    instanceid: int = betterproto.uint64_field(5)
    currencyid: int = betterproto.uint32_field(6)
    amount: int = betterproto.int64_field(7)
    missing: int = betterproto.bool_field(8)
    est_usd: int = betterproto.int64_field(9)


@dataclass(eq=False, repr=False)
class ItemDescriptionLine(betterproto.Message):
    type: str = betterproto.string_field(1)
    value: str = betterproto.string_field(2)
    color: str = betterproto.string_field(3)
    label: str = betterproto.string_field(4)


@dataclass(eq=False, repr=False)
class ItemAction(betterproto.Message):
    link: str = betterproto.string_field(1)
    name: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class ItemTag(betterproto.Message):
    appid: int = betterproto.uint32_field(1)
    category: str = betterproto.string_field(2)
    internal_name: str = betterproto.string_field(3)
    localized_category_name: str = betterproto.string_field(4)
    localized_tag_name: str = betterproto.string_field(5)
    color: str = betterproto.string_field(6)


@dataclass(eq=False, repr=False)
class ItemDescription(betterproto.Message):
    appid: int = betterproto.int32_field(1)
    classid: int = betterproto.uint64_field(2)
    instanceid: int = betterproto.uint64_field(3)
    currency: bool = betterproto.bool_field(4)
    background_color: int = betterproto.string_field(5)
    icon_url: str = betterproto.string_field(6)
    icon_url_large: str = betterproto.string_field(7)
    descriptions: list[ItemDescriptionLine] = betterproto.message_field(8)
    tradable: bool = betterproto.bool_field(9)
    actions: list[ItemAction] = betterproto.message_field(10)
    owner_descriptions: list[ItemDescriptionLine] = betterproto.message_field(11)
    owner_actions: list[ItemAction] = betterproto.message_field(12)
    fraudwarnings: list[str] = betterproto.string_field(13)
    name: str = betterproto.string_field(14)
    name_color: str = betterproto.string_field(15)
    type: str = betterproto.string_field(16)
    market_name: str = betterproto.string_field(17)
    market_hash_name: str = betterproto.string_field(18)
    market_fee: str = betterproto.string_field(19)
    market_fee_app: int = betterproto.int32_field(28)
    contained_item: "ItemDescription" = betterproto.message_field(20)
    market_actions: list[ItemAction] = betterproto.message_field(21)
    commodity: bool = betterproto.bool_field(22)
    market_tradable_restriction: int = betterproto.int32_field(23)
    market_marketable_restriction: int = betterproto.int32_field(24)
    marketable: bool = betterproto.bool_field(25)
    tags: list[ItemTag] = betterproto.message_field(26)
    item_expiration: str = betterproto.string_field(27)
    market_buy_country_restriction: str = betterproto.string_field(30)
    market_sell_country_restriction: str = betterproto.string_field(31)


class GetInventoryItemsWithDescriptionsResponse(UnifiedMessage, um_name="Econ.GetInventoryItemsWithDescriptions"):
    assets: list[Asset] = betterproto.message_field(1)
    descriptions: list[ItemDescription] = betterproto.message_field(2)
    missing_assets: list[Asset] = betterproto.message_field(3)
    more_items: bool = betterproto.bool_field(4)
    last_assetid: int = betterproto.uint64_field(5)
    total_inventory_count: int = betterproto.uint32_field(6)


class GetTradeOfferAccessTokenRequest(UnifiedMessage, um_name="Econ.GetTradeOfferAccessToken"):
    generate_new_token: bool = betterproto.bool_field(1)


class GetTradeOfferAccessTokenResponse(UnifiedMessage, um_name="Econ.GetTradeOfferAccessToken"):
    trade_offer_access_token: str = betterproto.string_field(1)


class GetItemShopOverlayAuthUrlRequest(UnifiedMessage, um_name="Econ.ClientGetItemShopOverlayAuthURL"):
    return_url: str = betterproto.string_field(1)


class GetItemShopOverlayAuthUrlResponse(UnifiedMessage, um_name="Econ.ClientGetItemShopOverlayAuthURL"):
    url: str = betterproto.string_field(1)


class GetAssetClassInfoRequest(UnifiedMessage, um_name="Econ.GetAssetClassInfo"):
    language: str = betterproto.string_field(1)
    appid: int = betterproto.uint32_field(2)
    classes: "list[GetAssetClassInfoRequestClass]" = betterproto.message_field(3)


@dataclass(eq=False, repr=False)
class GetAssetClassInfoRequestClass(betterproto.Message):
    classid: int = betterproto.uint64_field(1)
    instanceid: int = betterproto.uint64_field(2)


class GetAssetClassInfoResponse(UnifiedMessage, um_name="Econ.GetAssetClassInfo"):
    descriptions: "list[ItemDescription]" = betterproto.message_field(1)
