"""Licensed under The MIT License (MIT) - Copyright (c) 2020 James H-B. See LICENSE"""

from typing_extensions import NotRequired, Required, TypedDict


class AssetToDict(TypedDict):
    assetid: str
    amount: int
    appid: str
    contextid: str


class Asset(AssetToDict):
    instanceid: str
    classid: str
    missing: bool
    # rollback_new_assetid: NotRequired[str]


class ItemDescriptionLine(TypedDict):
    type: str
    value: str
    color: str
    label: str


class ItemAction(TypedDict):
    link: str
    name: str


class ItemTag(TypedDict):
    appid: int
    category: str
    internal_name: str
    localized_category_name: str
    localized_tag_name: str
    color: str


class Description(TypedDict, total=False):
    instanceid: Required[str]
    classid: Required[str]
    market_name: str
    currency: int
    name: str
    market_hash_name: str
    name_color: str
    background_color: str  # hex code
    type: str
    descriptions: list[ItemDescriptionLine]
    owner_descriptions: list[ItemDescriptionLine]
    actions: list[ItemAction]
    owner_actions: list[ItemAction]
    market_actions: list[ItemAction]
    tags: list[ItemTag]
    icon_url: str
    icon_url_large: str
    tradable: bool  # 1 vs 0
    marketable: bool  # same as above
    commodity: int  # might be a bool
    fraudwarnings: list[str]


class Item(Asset, Description):
    """We combine Assets with their matching Description to form items."""


class Inventory(TypedDict):
    assets: list[Asset]
    descriptions: list[Description]
    total_inventory_count: int
    last_assetid: str
    more_items: bool
    success: int  # Result
    rwgrsn: int  # p. much always -2


class TradeOffer(TypedDict):
    tradeofferid: str
    tradeid: str  # only used for receipts (it's not the useful one)
    accountid_other: int
    message: str
    trade_offer_state: int  # TradeOfferState
    expiration_time: int  # unix timestamps
    time_created: int
    time_updated: int
    escrow_end_date: int
    items_to_give: list[Item]
    items_to_receive: list[Item]
    is_our_offer: bool
    from_real_time_trade: bool
    confirmation_method: int  # https://cs.github.com/SteamDatabase/SteamTracking/blob/e86f560898e9f8fbc93fa4f55d5872b03db5f72b/Structs/enums.steamd#L1607


class GetTradeOffer(TypedDict):
    offer: TradeOffer
    descriptions: list[Description]


class TradeOfferReceiptAsset(Asset):
    new_assetid: str
    new_contextid: str


class TradeOfferReceiptItem(TradeOfferReceiptAsset, Item):
    pass


class TradeOfferReceipt(TypedDict):
    status: int
    tradeid: str
    time_init: int
    assets_received: NotRequired[list[TradeOfferReceiptAsset]]
    assets_given: NotRequired[list[TradeOfferReceiptAsset]]
    descriptions: list[Description]


class TradeOfferHistoryTrade(TypedDict):
    tradeid: str
    steamid_other: str
    # message: str
    time_init: int
    status: int
    assets_given: list[TradeOfferReceiptAsset]
    assets_received: list[TradeOfferReceiptAsset]


class GetTradeOfferHistory(TypedDict):
    more: bool
    trades: list[TradeOfferHistoryTrade]
    descriptions: list[Description]


class TradeOfferCreateResponse(TypedDict):
    tradeofferid: str
    needs_mobile_confirmation: bool
    needs_email_confirmation: bool
    email_domain: str
