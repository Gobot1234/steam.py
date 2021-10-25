from dataclasses import dataclass
from typing import List

import betterproto


@dataclass(eq=False, repr=False)
class UpdateRequest(betterproto.Message):
    recommendationid: int = betterproto.uint64_field(1)
    review_text: str = betterproto.string_field(2)
    voted_up: bool = betterproto.bool_field(3)
    is_public: bool = betterproto.bool_field(4)
    language: str = betterproto.string_field(5)
    is_in_early_access: bool = betterproto.bool_field(6)
    received_compensation: bool = betterproto.bool_field(7)
    comments_disabled: bool = betterproto.bool_field(8)


@dataclass(eq=False, repr=False)
class UpdateResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class GetIndividualRecommendationsRequest(betterproto.Message):
    requests: List["GetIndividualRecommendationsRequestRecommendationRequest"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class GetIndividualRecommendationsRequestRecommendationRequest(betterproto.Message):
    steamid: int = betterproto.uint64_field(1)
    appid: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class GetIndividualRecommendationsResponse(betterproto.Message):
    recommendations: List["RecommendationDetails"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class RecommendationDetails(betterproto.Message):
    recommendationid: int = betterproto.uint64_field(1)
    steamid: int = betterproto.uint64_field(2)
    appid: int = betterproto.uint32_field(3)
    review: str = betterproto.string_field(4)
    time_created: int = betterproto.uint32_field(5)
    time_updated: int = betterproto.uint32_field(6)
    votes_up: int = betterproto.uint32_field(7)
    votes_down: int = betterproto.uint32_field(8)
    vote_score: float = betterproto.float_field(9)
    language: str = betterproto.string_field(10)
    comment_count: int = betterproto.uint32_field(11)
    voted_up: bool = betterproto.bool_field(12)
    is_public: bool = betterproto.bool_field(13)
    moderator_hidden: bool = betterproto.bool_field(14)
    flagged_by_developer: int = betterproto.int32_field(15)
    report_score: int = betterproto.uint32_field(16)
    steamid_moderator: int = betterproto.uint64_field(17)
    steamid_developer: int = betterproto.uint64_field(18)
    steamid_dev_responder: int = betterproto.uint64_field(19)
    developer_response: str = betterproto.string_field(20)
    time_developer_responded: int = betterproto.uint32_field(21)
    developer_flag_cleared: bool = betterproto.bool_field(22)
    written_during_early_access: bool = betterproto.bool_field(23)
    votes_funny: int = betterproto.uint32_field(24)
    received_compensation: bool = betterproto.bool_field(25)
    unverified_purchase: bool = betterproto.bool_field(26)
    review_quality: int = betterproto.int32_field(27)
    weighted_vote_score: float = betterproto.float_field(28)
    moderation_note: str = betterproto.string_field(29)
    payment_method: int = betterproto.int32_field(30)
    playtime_2weeks: int = betterproto.int32_field(31)
    playtime_forever: int = betterproto.int32_field(32)
    last_playtime: int = betterproto.int32_field(33)
    comments_disabled: bool = betterproto.bool_field(34)
    playtime_at_review: int = betterproto.int32_field(35)
    approved_for_china: bool = betterproto.bool_field(36)
    ban_check_result: int = betterproto.int32_field(37)
    refunded: bool = betterproto.bool_field(38)
    account_score_spend: int = betterproto.int32_field(39)
    reactions: List["RecommendationLoyaltyReaction"] = betterproto.message_field(40)
    ipaddress: str = betterproto.string_field(41)


@dataclass(eq=False, repr=False)
class RecommendationLoyaltyReaction(betterproto.Message):
    reaction_type: int = betterproto.uint32_field(1)
    count: int = betterproto.uint32_field(2)
