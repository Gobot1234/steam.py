# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: dota_gcmessages_client.proto
# plugin: python-betterproto

from __future__ import annotations

from dataclasses import dataclass

import betterproto

from ....protobufs.msg import GCProtobufMessage
from ..enums import EMsg
from .common import Match  # noqa: TCH001
from .shared_enums import EMatchGroupServerStatus, MatchVote  # noqa: TCH001

# PROFILE CARD


class ClientToGCGetProfileCard(GCProtobufMessage, msg=EMsg.ClientToGCGetProfileCard):
    account_id: int = betterproto.uint32_field(1)


# RANK/BEHAVIOR


class ERankType(betterproto.Enum):
    Invalid = 0
    Casual = 1
    Ranked = 2
    CasualLegacy = 3
    RankedLegacy = 4
    CasualGlicko = 5
    RankedGlicko = 6
    RankMax = 7
    BehaviorPrivate = 100
    BehaviorPublic = 101
    Max = 102


class ClientToGCRankRequest(GCProtobufMessage, msg=EMsg.ClientToGCRankRequest):
    rank_type: ERankType = betterproto.enum_field(1)


class GCToClientRankResponseEResultCode(betterproto.Enum):
    k_Succeeded = 0
    k_Failed = 1
    k_InvalidRankType = 2


class GCToClientRankResponse(GCProtobufMessage, msg=EMsg.GCToClientRankResponse):
    result_enum: GCToClientRankResponseEResultCode = betterproto.enum_field(1)
    rank_value: int = betterproto.uint32_field(2)
    rank_data1: int = betterproto.uint32_field(3)
    rank_data2: int = betterproto.uint32_field(4)
    rank_data3: int = betterproto.uint32_field(5)


# MATCHMAKING STATS


class MatchmakingStatsRequest(GCProtobufMessage, msg=EMsg.MatchmakingStatsRequest):
    pass


class MatchmakingStatsResponse(GCProtobufMessage, msg=EMsg.MatchmakingStatsResponse):
    matchgroups_version: int = betterproto.uint32_field(1)
    legacy_searching_players_by_group_source2: list[int] = betterproto.uint32_field(7)
    match_groups: list[MatchmakingMatchGroupInfo] = betterproto.message_field(8)


@dataclass(eq=False, repr=False)
class MatchmakingMatchGroupInfo(betterproto.Message):
    players_searching: int = betterproto.uint32_field(1)
    auto_region_select_ping_penalty: int = betterproto.sint32_field(2)
    auto_region_select_ping_penalty_custom: int = betterproto.sint32_field(4)
    status: EMatchGroupServerStatus = betterproto.enum_field(3)


# MATCH DETAILS


class MatchDetailsRequest(GCProtobufMessage, msg=EMsg.MatchDetailsRequest):
    match_id: int = betterproto.uint64_field(1)


class MatchDetailsResponse(GCProtobufMessage, msg=EMsg.MatchDetailsResponse):
    eresult: int = betterproto.uint32_field(1)  # originally called result
    match: Match = betterproto.message_field(2)
    vote: MatchVote = betterproto.enum_field(3)
