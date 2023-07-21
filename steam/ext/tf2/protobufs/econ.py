# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: econ_messages.proto
# plugin: python-betterproto

from dataclasses import dataclass

import betterproto

from ....protobufs.msg import GCProtobufMessage
from ..enums import EMsg


@dataclass(eq=False, repr=False)
class ApplyAutograph(betterproto.Message):
    autograph_item_id: int = betterproto.uint64_field(1)
    item_item_id: int = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class EconPlayerStrangeCountAdjustment(betterproto.Message):
    account_id: int = betterproto.uint32_field(1)
    strange_count_adjustments: """list[EconPlayerStrangeCountAdjustmentCStrangeCountAdjustment]""" = (
        betterproto.message_field(2)
    )


@dataclass(eq=False, repr=False)
class EconPlayerStrangeCountAdjustmentCStrangeCountAdjustment(betterproto.Message):
    event_type: int = betterproto.uint32_field(1)
    item_id: int = betterproto.uint64_field(2)
    adjustment: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class RequestItemPurgatoryFinalizePurchase(betterproto.Message):
    item_ids: list[int] = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class RequestItemPurgatoryFinalizePurchaseResponse(betterproto.Message):
    result: int = betterproto.uint32_field(1)


@dataclass(eq=False, repr=False)
class RequestItemPurgatoryRefundPurchase(betterproto.Message):
    item_id: int = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class RequestItemPurgatoryRefundPurchaseResponse(betterproto.Message):
    result: int = betterproto.uint32_field(1)


@dataclass(eq=False, repr=False)
class CraftingResponse(betterproto.Message):
    item_ids: list[int] = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class RequestStoreSalesData(betterproto.Message):
    version: int = betterproto.uint32_field(1)
    currency: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class RequestStoreSalesDataResponse(betterproto.Message):
    sale_price: "list[RequestStoreSalesDataResponsePrice]" = betterproto.message_field(1)
    version: int = betterproto.uint32_field(2)
    expiration_time: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class RequestStoreSalesDataResponsePrice(betterproto.Message):
    item_def: int = betterproto.uint32_field(1)
    price: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class RequestStoreSalesDataUpToDateResponse(betterproto.Message):
    version: int = betterproto.uint32_field(1)
    expiration_time: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class ToPingRequest(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class ToPingResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class ToGetUserSessionServer(betterproto.Message):
    account_id: int = betterproto.uint32_field(1)


@dataclass(eq=False, repr=False)
class ToGetUserSessionServerResponse(betterproto.Message):
    server_steam_id: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class ToGetUserServerMembers(betterproto.Message):
    account_id: int = betterproto.uint32_field(1)
    max_spectators: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class ToGetUserServerMembersResponse(betterproto.Message):
    member_account_id: list[int] = betterproto.uint32_field(1)


@dataclass(eq=False, repr=False)
class LookupMultipleAccountNames(betterproto.Message):
    accountids: list[int] = betterproto.uint32_field(1)


@dataclass(eq=False, repr=False)
class LookupMultipleAccountNamesResponse(betterproto.Message):
    accounts: "list[LookupMultipleAccountNamesResponseAccount]" = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class LookupMultipleAccountNamesResponseAccount(betterproto.Message):
    accountid: int = betterproto.uint32_field(1)
    persona: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class ToGrantSelfMadeItemToAccount(betterproto.Message):
    item_def_index: int = betterproto.uint32_field(1)
    accountid: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class ToThankedByNewUser(betterproto.Message):
    new_user_accountid: int = betterproto.uint32_field(1)
    thanked_user_accountid: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class ShuffleCrateContents(betterproto.Message):
    crate_item_id: int = betterproto.uint64_field(1)
    user_code_string: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class QuestObjectiveProgress(betterproto.Message):
    quest_id: int = betterproto.uint64_field(1)
    quest_attrib_index: int = betterproto.uint32_field(2)
    delta: int = betterproto.uint32_field(3)
    owner_steamid: int = betterproto.fixed64_field(4)


@dataclass(eq=False, repr=False)
class QuestObjectivePointsChange(betterproto.Message):
    quest_id: int = betterproto.uint64_field(1)
    owner_steamid: int = betterproto.fixed64_field(4)
    update_base_points: bool = betterproto.bool_field(5)
    points_0: int = betterproto.uint32_field(6)
    points_1: int = betterproto.uint32_field(7)
    points_2: int = betterproto.uint32_field(8)


@dataclass(eq=False, repr=False)
class QuestCompleteRequest(betterproto.Message):
    quest_id: int = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class QuestCompleted(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class QuestObjectiveRequestLoanerItems(betterproto.Message):
    quest_id: int = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class QuestObjectiveRequestLoanerResponse(betterproto.Message):
    pass


class CraftCollectionUpgrade(GCProtobufMessage, msg=EMsg.CraftCollectionUpgrade):
    item_id: list[int] = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class CraftHalloweenOffering(betterproto.Message):
    tool_id: int = betterproto.uint64_field(1)
    item_id: list[int] = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class CraftCommonStatClock(betterproto.Message):
    tool_id: int = betterproto.uint64_field(1)
    item_id: list[int] = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class QuestDiscardRequest(betterproto.Message):
    quest_id: int = betterproto.uint64_field(1)
