from typing import List

import betterproto


class UpdateRequest(betterproto.Message):
    recommendationid = betterproto.uint64_field(1)
    review_text = betterproto.string_field(2)
    voted_up = betterproto.bool_field(3)
    is_public = betterproto.bool_field(4)
    language = betterproto.string_field(5)
    is_in_early_access = betterproto.bool_field(6)
    received_compensation = betterproto.bool_field(7)
    comments_disabled = betterproto.bool_field(8)


class UpdateResponse(betterproto.Message):
    pass


class GetIndividualRecommendationsRequest(betterproto.Message):
    requests: "GetIndividualRecommendationsRequestRecommendationRequest" = betterproto.message_field(1)


class GetIndividualRecommendationsRequestRecommendationRequest(betterproto.Message):
    steamid = betterproto.uint64_field(1)
    appid = betterproto.uint32_field(2)


class GetIndividualRecommendationsResponse(betterproto.Message):
    recommendations: List["RecommendationDetails"] = betterproto.message_field(1)


class RecommendationDetails(betterproto.Message):
    recommendationid = betterproto.uint64_field(1)
    steamid = betterproto.uint64_field(2)
    appid = betterproto.uint32_field(3)
    review = betterproto.string_field(4)
    time_created = betterproto.uint32_field(5)
    time_updated = betterproto.uint32_field(6)
    votes_up = betterproto.uint32_field(7)
    votes_down = betterproto.uint32_field(8)
    vote_score = betterproto.float_field(9)
    language = betterproto.string_field(10)
    comment_count = betterproto.uint32_field(11)
    voted_up = betterproto.bool_field(12)
    is_public = betterproto.bool_field(13)
    moderator_hidden = betterproto.bool_field(14)
    flagged_by_developer = betterproto.int32_field(15)
    report_score = betterproto.uint32_field(16)
    steamid_moderator = betterproto.uint64_field(17)
    steamid_developer = betterproto.uint64_field(18)
    steamid_dev_responder = betterproto.uint64_field(19)
    developer_response = betterproto.string_field(20)
    time_developer_responded = betterproto.uint32_field(21)
    developer_flag_cleared = betterproto.bool_field(22)
    written_during_early_access = betterproto.bool_field(23)
    votes_funny = betterproto.uint32_field(24)
    received_compensation = betterproto.bool_field(25)
    unverified_purchase = betterproto.bool_field(26)
    review_quality = betterproto.int32_field(27)
    weighted_vote_score = betterproto.float_field(28)
    moderation_note = betterproto.string_field(29)
    payment_method = betterproto.int32_field(30)
    playtime_2weeks = betterproto.int32_field(31)
    playtime_forever = betterproto.int32_field(32)
    last_playtime = betterproto.int32_field(33)
    comments_disabled = betterproto.bool_field(34)
    playtime_at_review = betterproto.int32_field(35)
    approved_for_china = betterproto.bool_field(36)
    ban_check_result = betterproto.int32_field(37)
    refunded = betterproto.bool_field(38)
    account_score_spend = betterproto.int32_field(39)
    reactions: List["RecommendationLoyaltyReaction"] = betterproto.message_field(40)
    ipaddress = betterproto.string_field(41)


class RecommendationLoyaltyReaction(betterproto.Message):
    reaction_type = betterproto.uint32_field(1)
    count = betterproto.uint32_field(2)
