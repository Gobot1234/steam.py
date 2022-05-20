"""Licensed under The MIT License (MIT) - Copyright (c) 2020 James. See LICENSE"""

from typing_extensions import NotRequired, Required, TypedDict


class AssetToDict(TypedDict):
    assetid: str
    amount: int
    appid: str
    contextid: str


class AssetDict(AssetToDict):
    instanceid: str
    classid: str
    missing: bool


class DescriptionDict(TypedDict, total=False):
    instanceid: Required[str]
    classid: Required[str]
    market_name: str
    currency: int
    name: str
    market_hash_name: str
    name_color: str
    background_color: str  # hex code
    type: str
    descriptions: list[dict[str, str]]
    owner_descriptions: list[dict[str, str]]
    market_actions: list[dict[str, str]]
    actions: list[dict[str, str]]
    tags: list[dict[str, str]]
    actions: list[dict[str, str]]
    icon_url: str
    icon_url_large: str
    tradable: bool  # 1 vs 0
    marketable: bool  # same as above
    commodity: int  # might be a bool
    fraudwarnings: list[str]


class ItemDict(AssetDict, DescriptionDict):
    """We combine Assets with their matching Description to form items."""


class InventoryDict(TypedDict):
    assets: list[AssetDict]
    descriptions: list[DescriptionDict]
    total_inventory_count: int
    success: int  # Result
    rwgrsn: int  # p. much always -2


class TradeOfferDict(TypedDict):
    tradeofferid: str
    tradeid: str  # only used for receipts (it's not the useful one)
    accountid_other: int
    message: str
    trade_offer_state: int  # TradeOfferState
    expiration_time: int  # unix timestamps
    time_created: int
    time_updated: int
    escrow_end_date: int
    items_to_give: list[ItemDict]
    items_to_receive: list[ItemDict]
    is_our_offer: bool
    from_real_time_trade: bool
    confirmation_method: int  # https://cs.github.com/SteamDatabase/SteamTracking/blob/e86f560898e9f8fbc93fa4f55d5872b03db5f72b/Structs/enums.steamd#L1607


class TradeOfferReceiptAssetDict(AssetDict):
    new_assetid: str
    new_contextid: str


class TradeOfferReceiptItemDict(TradeOfferReceiptAssetDict, ItemDict):
    ...


class TradeOfferReceiptDict(TypedDict):
    status: int
    tradeid: str
    time_init: int
    assets_received: NotRequired[list[TradeOfferReceiptAssetDict]]
    assets_given: NotRequired[list[TradeOfferReceiptAssetDict]]
    descriptions: list[DescriptionDict]
