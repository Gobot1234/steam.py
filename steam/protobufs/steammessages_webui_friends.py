# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: friends.proto/friends_mobile.proto
# plugin: python-betterproto

from dataclasses import dataclass
from typing import List

import betterproto

from .steammessages_base import CcddbAppDetailCommon, CClanMatchEventByRange, CMsgIpAddress
from .steammessages_clientserver_friends import CMsgClientFriendsList


@dataclass(eq=False, repr=False)
class CCommunityGetAppsRequest(betterproto.Message):
    appids: List[int] = betterproto.int32_field(1)
    language: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetAppsResponse(betterproto.Message):
    apps: List["CcddbAppDetailCommon"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityGetAppRichPresenceLocalizationRequest(betterproto.Message):
    appid: int = betterproto.int32_field(1)
    language: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetAppRichPresenceLocalizationResponse(betterproto.Message):
    appid: int = betterproto.int32_field(1)
    token_lists: List["CCommunityGetAppRichPresenceLocalizationResponseTokenList"] = betterproto.message_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetAppRichPresenceLocalizationResponseToken(betterproto.Message):
    name: str = betterproto.string_field(1)
    value: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetAppRichPresenceLocalizationResponseTokenList(betterproto.Message):
    language: str = betterproto.string_field(1)
    tokens: List["CCommunityGetAppRichPresenceLocalizationResponseToken"] = betterproto.message_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetCommentThreadRequest(betterproto.Message):
    steamid: int = betterproto.fixed64_field(1)
    comment_thread_type: int = betterproto.uint32_field(2)
    gidfeature: int = betterproto.fixed64_field(3)
    gidfeature2: int = betterproto.fixed64_field(4)
    commentthreadid: int = betterproto.fixed64_field(5)
    start: int = betterproto.int32_field(6)
    count: int = betterproto.int32_field(7)
    upvoters: int = betterproto.int32_field(8)
    include_deleted: bool = betterproto.bool_field(9)
    gidcomment: int = betterproto.fixed64_field(10)
    time_oldest: int = betterproto.uint32_field(11)
    oldest_first: bool = betterproto.bool_field(12)


@dataclass(eq=False, repr=False)
class CCommunityComment(betterproto.Message):
    gidcomment: int = betterproto.fixed64_field(1)
    steamid: int = betterproto.fixed64_field(2)
    timestamp: int = betterproto.uint32_field(3)
    text: str = betterproto.string_field(4)
    upvotes: int = betterproto.int32_field(5)
    hidden: bool = betterproto.bool_field(6)
    hidden_by_user: bool = betterproto.bool_field(7)
    deleted: bool = betterproto.bool_field(8)
    ipaddress: "CMsgIpAddress" = betterproto.message_field(9)
    total_hidden: int = betterproto.int32_field(10)
    upvoted_by_user: bool = betterproto.bool_field(11)


@dataclass(eq=False, repr=False)
class CCommunityGetCommentThreadResponse(betterproto.Message):
    comments: List["CCommunityComment"] = betterproto.message_field(1)
    deleted_comments: List["CCommunityComment"] = betterproto.message_field(2)
    steamid: int = betterproto.fixed64_field(3)
    commentthreadid: int = betterproto.fixed64_field(4)
    start: int = betterproto.int32_field(5)
    count: int = betterproto.int32_field(6)
    total_count: int = betterproto.int32_field(7)
    upvotes: int = betterproto.int32_field(8)
    upvoters: List[int] = betterproto.uint32_field(9)
    user_subscribed: bool = betterproto.bool_field(10)
    user_upvoted: bool = betterproto.bool_field(11)
    answer_commentid: int = betterproto.fixed64_field(12)
    answer_actor: int = betterproto.uint32_field(13)
    answer_actor_rank: int = betterproto.int32_field(14)
    can_post: bool = betterproto.bool_field(15)


@dataclass(eq=False, repr=False)
class CCommunityPostCommentToThreadResponse(betterproto.Message):
    gidcomment: int = betterproto.fixed64_field(1)
    commentthreadid: int = betterproto.fixed64_field(2)
    count: int = betterproto.int32_field(3)
    upvotes: int = betterproto.int32_field(4)


@dataclass(eq=False, repr=False)
class CCommunityDeleteCommentFromThreadResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityRateCommentThreadResponse(betterproto.Message):
    gidcomment: int = betterproto.uint64_field(1)
    commentthreadid: int = betterproto.uint64_field(2)
    count: int = betterproto.uint32_field(3)
    upvotes: int = betterproto.uint32_field(4)
    has_upvoted: bool = betterproto.bool_field(5)


@dataclass(eq=False, repr=False)
class CCommunityGetCommentThreadRatingsResponse(betterproto.Message):
    commentthreadid: int = betterproto.uint64_field(1)
    gidcomment: int = betterproto.uint64_field(2)
    upvotes: int = betterproto.uint32_field(3)
    has_upvoted: bool = betterproto.bool_field(4)
    upvoter_accountids: List[int] = betterproto.uint32_field(5)


@dataclass(eq=False, repr=False)
class CCommunityRateClanAnnouncementRequest(betterproto.Message):
    announcementid: int = betterproto.uint64_field(1)
    vote_up: bool = betterproto.bool_field(2)
    clan_accountid: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class CCommunityRateClanAnnouncementResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityGetClanAnnouncementVoteForUserRequest(betterproto.Message):
    announcementid: int = betterproto.uint64_field(1)


@dataclass(eq=False, repr=False)
class CCommunityGetClanAnnouncementVoteForUserResponse(betterproto.Message):
    voted_up: bool = betterproto.bool_field(1)
    voted_down: bool = betterproto.bool_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetAvatarHistoryResponse(betterproto.Message):
    avatars: List["CCommunityGetAvatarHistoryResponseAvatarData"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityGetAvatarHistoryResponseAvatarData(betterproto.Message):
    avatar_sha1: str = betterproto.string_field(1)
    user_uploaded: bool = betterproto.bool_field(2)
    timestamp: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class CAppPriority(betterproto.Message):
    priority: int = betterproto.uint32_field(1)
    appid: List[int] = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetUserPartnerEventNewsResponse(betterproto.Message):
    results: List["CClanMatchEventByRange"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityPartnerEventResult(betterproto.Message):
    clanid: int = betterproto.uint32_field(1)
    event_gid: int = betterproto.fixed64_field(2)
    announcement_gid: int = betterproto.fixed64_field(3)
    appid: int = betterproto.uint32_field(4)
    possible_takeover: bool = betterproto.bool_field(5)
    rtime32_last_modified: int = betterproto.uint32_field(6)
    user_app_priority: int = betterproto.int32_field(7)


@dataclass(eq=False, repr=False)
class CCommunityGetBestEventsForUserResponse(betterproto.Message):
    results: List["CCommunityPartnerEventResult"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityClearUserPartnerEventsAppPrioritiesResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityPartnerEventsAppPriority(betterproto.Message):
    appid: int = betterproto.uint32_field(1)
    user_app_priority: int = betterproto.int32_field(2)


@dataclass(eq=False, repr=False)
class CCommunityGetUserPartnerEventsAppPrioritiesResponse(betterproto.Message):
    priorities: List["CCommunityPartnerEventsAppPriority"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityClearSinglePartnerEventsAppPriorityResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityPartnerEventsShowMoreForAppResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityPartnerEventsShowLessForAppResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityMarkPartnerEventsForUserRequest(betterproto.Message):
    markings: List["CCommunityMarkPartnerEventsForUserRequestPartnerEventMarking"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityMarkPartnerEventsForUserRequestPartnerEventMarking(betterproto.Message):
    clanid: int = betterproto.uint32_field(1)
    event_gid: int = betterproto.fixed64_field(2)
    display_location: int = betterproto.int32_field(3)
    mark_shown: bool = betterproto.bool_field(4)
    mark_read: bool = betterproto.bool_field(5)


@dataclass(eq=False, repr=False)
class CCommunityMarkPartnerEventsForUserResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CCommunityGetUserPartnerEventViewStatusResponse(betterproto.Message):
    events: List["CCommunityGetUserPartnerEventViewStatusResponsePartnerEvent"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CCommunityGetUserPartnerEventViewStatusResponsePartnerEvent(betterproto.Message):
    event_gid: int = betterproto.fixed64_field(1)
    last_shown_time: int = betterproto.uint32_field(2)
    last_read_time: int = betterproto.uint32_field(3)
    clan_account_id: int = betterproto.uint32_field(4)


@dataclass(eq=False, repr=False)
class CPlayerGetFavoriteBadgeResponse(betterproto.Message):
    has_favorite_badge: bool = betterproto.bool_field(1)
    badgeid: int = betterproto.uint32_field(2)
    communityitemid: int = betterproto.uint64_field(3)
    item_type: int = betterproto.uint32_field(4)
    border_color: int = betterproto.uint32_field(5)
    appid: int = betterproto.uint32_field(6)
    level: int = betterproto.uint32_field(7)


@dataclass(eq=False, repr=False)
class CPlayerSetFavoriteBadgeResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class ProfileCustomizationSlot(betterproto.Message):
    slot: int = betterproto.uint32_field(1)
    appid: int = betterproto.uint32_field(2)
    publishedfileid: int = betterproto.uint64_field(3)
    item_assetid: int = betterproto.uint64_field(4)
    item_contextid: int = betterproto.uint64_field(5)
    notes: str = betterproto.string_field(6)
    title: str = betterproto.string_field(7)
    accountid: int = betterproto.uint32_field(8)
    badgeid: int = betterproto.uint32_field(9)
    border_color: int = betterproto.uint32_field(10)
    item_classid: int = betterproto.uint64_field(11)
    item_instanceid: int = betterproto.uint64_field(12)


@dataclass(eq=False, repr=False)
class ProfileCustomization(betterproto.Message):
    customization_type: int = betterproto.int32_field(1)
    large: bool = betterproto.bool_field(2)
    slots: List["ProfileCustomizationSlot"] = betterproto.message_field(3)
    active: bool = betterproto.bool_field(4)
    customization_style: int = betterproto.int32_field(5)


@dataclass(eq=False, repr=False)
class ProfileTheme(betterproto.Message):
    theme_id: str = betterproto.string_field(1)
    title: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CPlayerGetProfileCustomizationResponse(betterproto.Message):
    customizations: List["ProfileCustomization"] = betterproto.message_field(1)
    slots_available: int = betterproto.uint32_field(2)
    profile_theme: "ProfileTheme" = betterproto.message_field(3)


@dataclass(eq=False, repr=False)
class CPlayerGetProfileThemesAvailableResponse(betterproto.Message):
    profile_themes: List["ProfileTheme"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CPlayerSetProfileThemeResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CWebRtcClientInitiateWebRtcConnectionRequest(betterproto.Message):
    sdp: str = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class CWebRtcClientInitiateWebRtcConnectionResponse(betterproto.Message):
    remote_description: str = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class CWebRtcWebRtcSessionConnectedNotification(betterproto.Message):
    ssrc: int = betterproto.uint32_field(1)
    client_ip: int = betterproto.uint32_field(2)
    client_port: int = betterproto.uint32_field(3)
    server_ip: int = betterproto.uint32_field(4)
    server_port: int = betterproto.uint32_field(5)


@dataclass(eq=False, repr=False)
class CWebRtcWebRtcUpdateRemoteDescriptionNotification(betterproto.Message):
    remote_description: str = betterproto.string_field(1)
    remote_description_version: int = betterproto.uint64_field(2)
    ssrcs_to_accountids: List[
        "CWebRtcWebRtcUpdateRemoteDescriptionNotificationCssrcToAccountIdMapping"
    ] = betterproto.message_field(3)


@dataclass(eq=False, repr=False)
class CWebRtcWebRtcUpdateRemoteDescriptionNotificationCssrcToAccountIdMapping(betterproto.Message):
    ssrc: int = betterproto.uint32_field(1)
    accountid: int = betterproto.uint32_field(2)


@dataclass(eq=False, repr=False)
class CWebRtcClientAcknowledgeUpdatedRemoteDescriptionRequest(betterproto.Message):
    ip_webrtc_server: int = betterproto.uint32_field(1)
    port_webrtc_server: int = betterproto.uint32_field(2)
    ip_webrtc_session_client: int = betterproto.uint32_field(3)
    port_webrtc_session_client: int = betterproto.uint32_field(4)
    remote_description_version: int = betterproto.uint64_field(5)


@dataclass(eq=False, repr=False)
class CWebRtcClientAcknowledgeUpdatedRemoteDescriptionResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CVoiceChatRequestOneOnOneChatRequest(betterproto.Message):
    steamid_partner: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class CVoiceChatRequestOneOnOneChatResponse(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class CVoiceChatOneOnOneChatRequestedNotification(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    steamid_partner: int = betterproto.fixed64_field(2)


@dataclass(eq=False, repr=False)
class CVoiceChatAnswerOneOnOneChatRequest(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    steamid_partner: int = betterproto.fixed64_field(2)
    accepted_request: bool = betterproto.bool_field(3)


@dataclass(eq=False, repr=False)
class CVoiceChatAnswerOneOnOneChatResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CVoiceChatOneOnOneChatRequestResponseNotification(betterproto.Message):
    voicechat_id: int = betterproto.fixed64_field(1)
    steamid_partner: int = betterproto.fixed64_field(2)
    accepted_request: bool = betterproto.bool_field(3)


@dataclass(eq=False, repr=False)
class CVoiceChatEndOneOnOneChatRequest(betterproto.Message):
    steamid_partner: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class CVoiceChatEndOneOnOneChatResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CVoiceChatLeaveOneOnOneChatRequest(betterproto.Message):
    steamid_partner: int = betterproto.fixed64_field(1)
    voice_chatid: int = betterproto.fixed64_field(2)


@dataclass(eq=False, repr=False)
class CVoiceChatLeaveOneOnOneChatResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CVoiceChatUserJoinedVoiceChatNotification(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    user_steamid: int = betterproto.fixed64_field(2)
    chatid: int = betterproto.uint64_field(3)
    one_on_one_steamid_lower: int = betterproto.fixed64_field(4)
    one_on_one_steamid_higher: int = betterproto.fixed64_field(5)
    chat_group_id: int = betterproto.uint64_field(6)
    user_sessionid: int = betterproto.uint32_field(7)


@dataclass(eq=False, repr=False)
class CVoiceChatUserVoiceStatusNotification(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    user_steamid: int = betterproto.fixed64_field(2)
    user_muted_mic_locally: bool = betterproto.bool_field(3)
    user_muted_output_locally: bool = betterproto.bool_field(4)
    user_has_no_mic_for_session: bool = betterproto.bool_field(5)
    user_webaudio_sample_rate: int = betterproto.int32_field(6)


@dataclass(eq=False, repr=False)
class CVoiceChatAllMembersStatusNotification(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    users: List["CVoiceChatUserVoiceStatusNotification"] = betterproto.message_field(2)


@dataclass(eq=False, repr=False)
class CVoiceChatUpdateVoiceChatWebRtcDataRequest(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    ip_webrtc_server: int = betterproto.uint32_field(2)
    port_webrtc_server: int = betterproto.uint32_field(3)
    ip_webrtc_client: int = betterproto.uint32_field(4)
    port_webrtc_client: int = betterproto.uint32_field(5)
    ssrc_my_sending_stream: int = betterproto.uint32_field(6)
    user_agent: str = betterproto.string_field(7)
    has_audio_worklets_support: bool = betterproto.bool_field(8)


@dataclass(eq=False, repr=False)
class CVoiceChatUpdateVoiceChatWebRtcDataResponse(betterproto.Message):
    send_client_voice_logs: bool = betterproto.bool_field(1)


@dataclass(eq=False, repr=False)
class CVoiceChatUploadClientVoiceChatLogsRequest(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    client_voice_logs_new_lines: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CVoiceChatUploadClientVoiceChatLogsResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CVoiceChatLeaveVoiceChatResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CVoiceChatUserLeftVoiceChatNotification(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    user_steamid: int = betterproto.fixed64_field(2)
    chatid: int = betterproto.uint64_field(3)
    one_on_one_steamid_lower: int = betterproto.fixed64_field(4)
    one_on_one_steamid_higher: int = betterproto.fixed64_field(5)
    chat_group_id: int = betterproto.uint64_field(6)
    user_sessionid: int = betterproto.uint32_field(7)


@dataclass(eq=False, repr=False)
class CVoiceChatVoiceChatEndedNotification(betterproto.Message):
    voice_chatid: int = betterproto.fixed64_field(1)
    one_on_one_steamid_lower: int = betterproto.fixed64_field(2)
    one_on_one_steamid_higher: int = betterproto.fixed64_field(3)
    chatid: int = betterproto.uint64_field(4)
    chat_group_id: int = betterproto.uint64_field(5)


@dataclass(eq=False, repr=False)
class CSteamTvCreateBroadcastChannelResponse(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelIdResponse(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)
    unique_name: str = betterproto.string_field(2)
    steamid: int = betterproto.fixed64_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvSetBroadcastChannelProfileResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelProfileResponse(betterproto.Message):
    unique_name: str = betterproto.string_field(1)
    owner_steamid: int = betterproto.fixed64_field(2)
    name: str = betterproto.string_field(3)
    language: str = betterproto.string_field(4)
    headline: str = betterproto.string_field(5)
    summary: str = betterproto.string_field(6)
    schedule: str = betterproto.string_field(7)
    rules: str = betterproto.string_field(8)
    panels: str = betterproto.string_field(9)
    is_partnered: bool = betterproto.bool_field(10)


@dataclass(eq=False, repr=False)
class CSteamTvSetBroadcastChannelImageResponse(betterproto.Message):
    replace_image_hash: str = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelImagesResponse(betterproto.Message):
    images: List["CSteamTvGetBroadcastChannelImagesResponseImages"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelImagesResponseImages(betterproto.Message):
    image_type: int = betterproto.int32_field(1)
    image_path: str = betterproto.string_field(2)
    image_index: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelLinksResponse(betterproto.Message):
    links: List["CSteamTvGetBroadcastChannelLinksResponseLinks"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelLinksResponseLinks(betterproto.Message):
    link_index: int = betterproto.uint32_field(1)
    url: str = betterproto.string_field(2)
    link_description: str = betterproto.string_field(3)
    left: int = betterproto.uint32_field(4)
    top: int = betterproto.uint32_field(5)
    width: int = betterproto.uint32_field(6)
    height: int = betterproto.uint32_field(7)


@dataclass(eq=False, repr=False)
class CSteamTvSetBroadcastChannelLinkRegionsRequestLinks(betterproto.Message):
    link_index: int = betterproto.uint32_field(1)
    url: str = betterproto.string_field(2)
    link_description: str = betterproto.string_field(3)
    left: int = betterproto.uint32_field(4)
    top: int = betterproto.uint32_field(5)
    width: int = betterproto.uint32_field(6)
    height: int = betterproto.uint32_field(7)


@dataclass(eq=False, repr=False)
class CSteamTvSetBroadcastChannelLinkRegionsResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelStatusResponse(betterproto.Message):
    is_live: bool = betterproto.bool_field(1)
    is_disabled: bool = betterproto.bool_field(2)
    appid: int = betterproto.uint32_field(3)
    viewers: int = betterproto.uint64_field(4)
    views: int = betterproto.uint64_field(5)
    broadcaster_steamid: int = betterproto.fixed64_field(6)
    thumbnail_url: str = betterproto.string_field(7)
    followers: int = betterproto.uint64_field(8)
    subscribers: int = betterproto.uint64_field(9)
    unique_name: str = betterproto.string_field(10)
    broadcast_session_id: int = betterproto.uint64_field(11)


@dataclass(eq=False, repr=False)
class GetBroadcastChannelEntry(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)
    unique_name: str = betterproto.string_field(2)
    name: str = betterproto.string_field(3)
    appid: int = betterproto.uint32_field(4)
    viewers: int = betterproto.uint64_field(5)
    views: int = betterproto.uint64_field(6)
    thumbnail_url: str = betterproto.string_field(7)
    followers: int = betterproto.uint64_field(8)
    headline: str = betterproto.string_field(9)
    avatar_url: str = betterproto.string_field(10)
    broadcaster_steamid: int = betterproto.fixed64_field(11)
    subscribers: int = betterproto.uint64_field(12)
    background_url: str = betterproto.string_field(13)
    is_featured: bool = betterproto.bool_field(14)
    is_disabled: bool = betterproto.bool_field(15)
    is_live: bool = betterproto.bool_field(16)
    language: str = betterproto.string_field(17)
    reports: int = betterproto.uint32_field(18)
    is_partnered: bool = betterproto.bool_field(19)


@dataclass(eq=False, repr=False)
class CSteamTvGetFollowedChannelsResponse(betterproto.Message):
    results: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetSubscribedChannelsResponse(betterproto.Message):
    results: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvFollowBroadcastChannelResponse(betterproto.Message):
    is_followed: bool = betterproto.bool_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvSubscribeBroadcastChannelResponse(betterproto.Message):
    is_subscribed: bool = betterproto.bool_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvReportBroadcastChannelResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelInteractionResponse(betterproto.Message):
    is_followed: bool = betterproto.bool_field(1)
    is_subscribed: bool = betterproto.bool_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvGame(betterproto.Message):
    appid: int = betterproto.uint32_field(1)
    name: str = betterproto.string_field(2)
    image: str = betterproto.string_field(3)
    viewers: int = betterproto.uint64_field(4)
    channels: List["GetBroadcastChannelEntry"] = betterproto.message_field(5)
    release_date: str = betterproto.string_field(6)
    developer: str = betterproto.string_field(7)
    publisher: str = betterproto.string_field(8)


@dataclass(eq=False, repr=False)
class CSteamTvGetGamesResponse(betterproto.Message):
    results: List["CSteamTvGame"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetChannelsResponse(betterproto.Message):
    results: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelBroadcastersResponse(betterproto.Message):
    broadcasters: List["CSteamTvGetBroadcastChannelBroadcastersResponseBroadcaster"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelBroadcastersResponseBroadcaster(betterproto.Message):
    steamid: int = betterproto.fixed64_field(1)
    name: str = betterproto.string_field(2)
    rtmp_token: str = betterproto.string_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvChatBan(betterproto.Message):
    issuer_steamid: int = betterproto.fixed64_field(1)
    chatter_steamid: int = betterproto.fixed64_field(2)
    time_expires: str = betterproto.string_field(3)
    permanent: bool = betterproto.bool_field(4)
    name: str = betterproto.string_field(5)


@dataclass(eq=False, repr=False)
class CSteamTvAddChatBanRequest(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)
    chatter_steamid: int = betterproto.fixed64_field(2)
    duration: int = betterproto.uint32_field(3)
    permanent: bool = betterproto.bool_field(4)
    undo: bool = betterproto.bool_field(5)


@dataclass(eq=False, repr=False)
class CSteamTvAddChatBanResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetChatBansResponse(betterproto.Message):
    results: List["CSteamTvChatBan"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvAddChatModeratorRequest(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)
    moderator_steamid: int = betterproto.fixed64_field(2)
    undo: bool = betterproto.bool_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvAddChatModeratorResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetChatModeratorsRequest(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvChatModerator(betterproto.Message):
    steamid: int = betterproto.fixed64_field(1)
    name: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvGetChatModeratorsResponse(betterproto.Message):
    results: List["CSteamTvChatModerator"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvAddWordBanResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetWordBansResponse(betterproto.Message):
    results: List[str] = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvJoinChatRequest(betterproto.Message):
    broadcast_channel_id: int = betterproto.fixed64_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvJoinChatResponse(betterproto.Message):
    chat_id: int = betterproto.fixed64_field(1)
    view_url_template: str = betterproto.string_field(2)
    flair_group_ids: List[int] = betterproto.uint64_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvSearchResponse(betterproto.Message):
    results: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvGetSteamTvUserSettingsResponse(betterproto.Message):
    stream_live_email: bool = betterproto.bool_field(1)
    stream_live_notification: bool = betterproto.bool_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvSetSteamTvUserSettingsResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CSteamTvGetMyBroadcastChannelsResponse(betterproto.Message):
    results: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateTakeover(betterproto.Message):
    broadcasts: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateSingleGame(betterproto.Message):
    broadcasts: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)
    appid: int = betterproto.uint32_field(2)
    title: str = betterproto.string_field(3)


@dataclass(eq=False, repr=False)
class GameListEntry(betterproto.Message):
    appid: int = betterproto.uint32_field(1)
    game_name: str = betterproto.string_field(2)
    broadcast: "GetBroadcastChannelEntry" = betterproto.message_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateGameList(betterproto.Message):
    entries: List["GameListEntry"] = betterproto.message_field(1)
    title: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateQuickExplore(betterproto.Message):
    broadcasts: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)
    title: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateConveyorBelt(betterproto.Message):
    broadcasts: List["GetBroadcastChannelEntry"] = betterproto.message_field(1)
    title: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateWatchParty(betterproto.Message):
    broadcast: "GetBroadcastChannelEntry" = betterproto.message_field(1)
    title: str = betterproto.string_field(2)
    chat_group_id: int = betterproto.uint64_field(3)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateDeveloper(betterproto.Message):
    broadcast: "GetBroadcastChannelEntry" = betterproto.message_field(1)
    title: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageTemplateEvent(betterproto.Message):
    title: str = betterproto.string_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvHomePageContentRow(betterproto.Message):
    template_type: int = betterproto.int32_field(1)
    takeover: "CSteamTvHomePageTemplateTakeover" = betterproto.message_field(2)
    single_game: "CSteamTvHomePageTemplateSingleGame" = betterproto.message_field(3)
    game_list: "CSteamTvHomePageTemplateGameList" = betterproto.message_field(4)
    quick_explore: "CSteamTvHomePageTemplateQuickExplore" = betterproto.message_field(5)
    conveyor_belt: "CSteamTvHomePageTemplateConveyorBelt" = betterproto.message_field(6)
    watch_party: "CSteamTvHomePageTemplateWatchParty" = betterproto.message_field(7)
    developer: "CSteamTvHomePageTemplateDeveloper" = betterproto.message_field(8)
    event: "CSteamTvHomePageTemplateEvent" = betterproto.message_field(9)


@dataclass(eq=False, repr=False)
class CSteamTvGetHomePageContentsResponse(betterproto.Message):
    rows: List["CSteamTvHomePageContentRow"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CSteamTvBroadcastClipInfo(betterproto.Message):
    broadcast_clip_id: int = betterproto.uint64_field(1)
    channel_id: int = betterproto.uint64_field(2)
    app_id: int = betterproto.uint32_field(3)
    broadcaster_steamid: int = betterproto.fixed64_field(4)
    creator_steamid: int = betterproto.fixed64_field(5)
    video_description: str = betterproto.string_field(6)
    live_time: int = betterproto.uint32_field(7)
    length_ms: int = betterproto.uint32_field(8)
    thumbnail_path: str = betterproto.string_field(9)


@dataclass(eq=False, repr=False)
class CSteamTvGetBroadcastChannelClipsResponse(betterproto.Message):
    clips: List["CSteamTvBroadcastClipInfo"] = betterproto.message_field(1)
    thumbnail_host: str = betterproto.string_field(2)


@dataclass(eq=False, repr=False)
class CFriendsListCategory(betterproto.Message):
    groupid: int = betterproto.uint32_field(1)
    name: str = betterproto.string_field(2)
    accountid_members: List[int] = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class CFriendsListGetCategoriesRequest(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CFriendsListGetCategoriesResponse(betterproto.Message):
    categories: List["CFriendsListCategory"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CFriendsListFavoriteEntry(betterproto.Message):
    accountid: int = betterproto.uint32_field(1)
    clanid: int = betterproto.uint32_field(2)
    chat_group_id: int = betterproto.uint64_field(3)


@dataclass(eq=False, repr=False)
class CFriendsListGetFavoritesRequest(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CFriendsListGetFavoritesResponse(betterproto.Message):
    favorites: List["CFriendsListFavoriteEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CFriendsListSetFavoritesRequest(betterproto.Message):
    favorites: List["CFriendsListFavoriteEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CFriendsListSetFavoritesResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CFriendsListFavoritesChangedNotification(betterproto.Message):
    favorites: List["CFriendsListFavoriteEntry"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CFriendsListGetFriendsListRequest(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CFriendsListGetFriendsListResponse(betterproto.Message):
    friendslist: "CMsgClientFriendsList" = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CClanRespondToClanInviteRequest(betterproto.Message):
    steamid: int = betterproto.fixed64_field(1)
    accept: bool = betterproto.bool_field(2)


@dataclass(eq=False, repr=False)
class CClanRespondToClanInviteResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class CClientMetricsClientBootstrapRequestInfo(betterproto.Message):
    original_hostname: str = betterproto.string_field(1)
    actual_hostname: str = betterproto.string_field(2)
    path: str = betterproto.string_field(3)
    base_name: str = betterproto.string_field(4)
    success: bool = betterproto.bool_field(5)
    status_code: int = betterproto.uint32_field(6)
    address_of_request_url: str = betterproto.string_field(7)
    response_time_ms: int = betterproto.uint32_field(8)
    bytes_received: int = betterproto.uint64_field(9)
    num_retries: int = betterproto.uint32_field(10)


@dataclass(eq=False, repr=False)
class CClientMetricsClientBootstrapSummary(betterproto.Message):
    launcher_type: int = betterproto.uint32_field(1)
    steam_realm: int = betterproto.uint32_field(2)
    beta_name: str = betterproto.string_field(3)
    download_completed: bool = betterproto.bool_field(4)
    total_time_ms: int = betterproto.uint32_field(6)
    manifest_requests: List["CClientMetricsClientBootstrapRequestInfo"] = betterproto.message_field(7)
    package_requests: List["CClientMetricsClientBootstrapRequestInfo"] = betterproto.message_field(8)


@dataclass(eq=False, repr=False)
class CProductImpressionsFromClientNotification(betterproto.Message):
    impressions: List["CProductImpressionsFromClientNotificationImpression"] = betterproto.message_field(1)


@dataclass(eq=False, repr=False)
class CProductImpressionsFromClientNotificationImpression(betterproto.Message):
    type: int = betterproto.int32_field(1)
    appid: int = betterproto.uint32_field(2)
    num_impressions: int = betterproto.uint32_field(3)