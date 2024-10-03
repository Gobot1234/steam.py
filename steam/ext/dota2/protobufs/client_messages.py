# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: dota_gcmessages_client.proto
# plugin: python-betterproto

from __future__ import annotations

from dataclasses import dataclass

import betterproto

from ....protobufs.msg import GCProtobufMessage
from ..enums import EMsg
from .base import SOEconItem  # noqa: TCH001
from .common import Match, RecentMatchInfo, StickerbookPage, SuccessfulHero  # noqa: TCH001
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


# MATCH HISTORY


class GetPlayerMatchHistory(GCProtobufMessage, msg=EMsg.GetPlayerMatchHistory):
    account_id: int = betterproto.uint32_field(1)
    start_at_match_id: int = betterproto.uint64_field(2)
    matches_requested: int = betterproto.uint32_field(3)
    hero_id: int = betterproto.uint32_field(4)
    request_id: int = betterproto.uint32_field(5)
    include_practice_matches: bool = betterproto.bool_field(7)
    include_custom_games: bool = betterproto.bool_field(8)
    include_event_games: bool = betterproto.bool_field(9)


class GetPlayerMatchHistoryResponse(GCProtobufMessage, msg=EMsg.GetPlayerMatchHistoryResponse):
    matches: list[GetPlayerMatchHistoryResponseMatch] = betterproto.message_field(1)
    request_id: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class GetPlayerMatchHistoryResponseMatch(betterproto.Message):
    match_id: int = betterproto.uint64_field(1)
    start_time: int = betterproto.uint32_field(2)
    hero_id: int = betterproto.uint32_field(3)
    winner: bool = betterproto.bool_field(4)
    game_mode: int = betterproto.uint32_field(5)
    rank_change: int = betterproto.int32_field(6)
    previous_rank: int = betterproto.uint32_field(7)
    lobby_type: int = betterproto.uint32_field(8)
    solo_rank: bool = betterproto.bool_field(9)
    abandon: bool = betterproto.bool_field(10)
    duration: int = betterproto.uint32_field(11)
    engine: int = betterproto.uint32_field(12)
    active_plus_subscription: bool = betterproto.bool_field(13)
    seasonal_rank: bool = betterproto.bool_field(14)
    tourney_id: int = betterproto.uint32_field(15)
    tourney_round: int = betterproto.uint32_field(16)
    tourney_tier: int = betterproto.uint32_field(17)
    tourney_division: int = betterproto.uint32_field(18)
    team_id: int = betterproto.uint32_field(19)
    team_name: str = betterproto.string_field(20)
    ugc_team_ui_logo: int = betterproto.uint64_field(21)
    selected_facet: int = betterproto.uint32_field(22)


# SOCIAL FEED POST MESSAGE


class ClientToGCSocialFeedPostMessageRequest(GCProtobufMessage, msg=EMsg.ClientToGCSocialFeedPostMessageRequest):
    message: str = betterproto.string_field(1)
    match_id: int = betterproto.uint64_field(2)  # doesn't seem like we can use it
    match_timestamp: int = betterproto.uint32_field(3)  # doesn't seem like we can use it


class GCToClientSocialFeedPostMessageResponse(GCProtobufMessage, msg=EMsg.GCToClientSocialFeedPostMessageResponse):
    success: bool = betterproto.bool_field(1)


# PROFILE REQUEST


class ProfileRequest(GCProtobufMessage, msg=EMsg.ProfileRequest):
    account_id: int = betterproto.uint32_field(1)


class ProfileResponseEResponse(betterproto.Enum):
    InternalError = 0
    Success = 1
    TooBusy = 2
    Disabled = 3


class ProfileResponse(GCProtobufMessage, msg=EMsg.ProfileResponse):
    background_item: SOEconItem = betterproto.message_field(1)
    featured_heroes: list[ProfileResponseFeaturedHero] = betterproto.message_field(2)
    recent_matches: list[ProfileResponseMatchInfo] = betterproto.message_field(3)
    successful_heroes: list[SuccessfulHero] = betterproto.message_field(4)
    recent_match_details: RecentMatchInfo = betterproto.message_field(5)
    eresult: ProfileResponseEResponse = betterproto.enum_field(6)
    stickerbook_page: StickerbookPage = betterproto.message_field(7)


@dataclass
class ProfileResponseFeaturedHero(betterproto.Message):
    hero_id: int = betterproto.uint32_field(1)
    equipped_econ_items: list[SOEconItem] = betterproto.message_field(2)
    manually_set: bool = betterproto.bool_field(3)
    plus_hero_xp: int = betterproto.uint32_field(4)
    plus_hero_relics_item: SOEconItem = betterproto.message_field(5)


@dataclass
class ProfileResponseMatchInfo(betterproto.Message):
    match_id: int = betterproto.uint64_field(1)
    match_timestamp: int = betterproto.uint32_field(2)
    performance_rating: int = betterproto.sint32_field(3)
    hero_id: int = betterproto.uint32_field(4)
    won_match: bool = betterproto.bool_field(5)
