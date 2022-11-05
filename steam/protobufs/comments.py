# These were removed for some reason, pulled from:
# https://github.com/SteamDatabase/Protobufs/blob/master/webui/service_community.proto and its history.
# Last updated 9/9/2021

from dataclasses import dataclass

import betterproto

from .base import CMsgIpAddress
from .msg import UnifiedMessage


class GetCommentThreadRequest(UnifiedMessage, um_name="Community.GetCommentThread"):
    id64: int = betterproto.fixed64_field(1)
    type: int = betterproto.uint32_field(2)
    forum_id: int = betterproto.fixed64_field(3)
    topic_id: int = betterproto.fixed64_field(4)
    thread_id: int = betterproto.fixed64_field(5)
    start: int = betterproto.int32_field(6)
    count: int = betterproto.int32_field(7)
    upvotes: int = betterproto.int32_field(8)
    include_deleted: bool = betterproto.bool_field(9)
    id: int = betterproto.fixed64_field(10)
    time_oldest: int = betterproto.uint32_field(11)
    oldest_first: bool = betterproto.bool_field(12)


class GetCommentThreadResponse(UnifiedMessage, um_name="Community.GetCommentThread"):
    @dataclass(eq=False, repr=False)
    class Comment(betterproto.Message):
        id: int = betterproto.fixed64_field(1)
        author_id64: int = betterproto.fixed64_field(2)
        timestamp: int = betterproto.uint32_field(3)
        content: str = betterproto.string_field(4)
        upvotes: int = betterproto.int32_field(5)
        hidden: bool = betterproto.bool_field(6)
        hidden_by_user: bool = betterproto.bool_field(7)
        deleted: bool = betterproto.bool_field(8)
        ipaddress: CMsgIpAddress = betterproto.message_field(9)
        total_hidden: int = betterproto.int32_field(10)
        upvoted_by_user: bool = betterproto.bool_field(11)

        @dataclass(eq=False, repr=False)
        class Reaction(betterproto.Message):
            reactionid: int = betterproto.uint32_field(1)
            count: int = betterproto.uint32_field(1)

        reactions: list[Reaction] = betterproto.message_field(12)
        parent_id: int = betterproto.fixed64_field(13)

    comments: list[Comment] = betterproto.message_field(1)
    deleted_comments: list[Comment] = betterproto.message_field(2)
    id64: int = betterproto.fixed64_field(3)
    thread_id: int = betterproto.fixed64_field(4)
    start: int = betterproto.int32_field(5)
    count: int = betterproto.int32_field(6)
    total_count: int = betterproto.int32_field(7)
    upvotes: int = betterproto.int32_field(8)
    upvoters: list[int] = betterproto.uint32_field(9)
    user_subscribed: bool = betterproto.bool_field(10)
    user_upvoted: bool = betterproto.bool_field(11)
    answer_id: int = betterproto.fixed64_field(12)
    answer_actor: int = betterproto.uint32_field(13)
    answer_actor_rank: int = betterproto.int32_field(14)
    can_post: bool = betterproto.bool_field(15)
    type: int = betterproto.uint32_field(16)
    forum_id: int = betterproto.fixed64_field(17)
    topic_id: int = betterproto.fixed64_field(18)


class PostCommentToThreadRequest(UnifiedMessage, um_name="Community.PostCommentToThread"):
    id64: int = betterproto.fixed64_field(1)
    type: int = betterproto.uint32_field(2)
    forum_id: int = betterproto.fixed64_field(3)
    topic_id: int = betterproto.fixed64_field(4)
    content: str = betterproto.string_field(6)
    parent_id: int = betterproto.fixed64_field(7)
    suppress_notifications: bool = betterproto.bool_field(8)
    is_report: bool = betterproto.bool_field(9)


class PostCommentToThreadResponse(UnifiedMessage, um_name="Community.PostCommentToThread"):
    id: int = betterproto.fixed64_field(1)
    thread_id: int = betterproto.fixed64_field(2)
    count: int = betterproto.int32_field(3)
    upvotes: int = betterproto.int32_field(4)


class DeleteCommentFromThreadRequest(UnifiedMessage, um_name="Community.DeleteCommentFromThread"):
    id64: int = betterproto.fixed64_field(1)
    type: int = betterproto.uint32_field(2)
    forum_id: int = betterproto.fixed64_field(3)
    topic_id: int = betterproto.fixed64_field(4)
    id: int = betterproto.fixed64_field(5)
    undelete: bool = betterproto.bool_field(6)


class DeleteCommentFromThreadResponse(UnifiedMessage, um_name="Community.DeleteCommentFromThread"):
    pass


class RateCommentThreadRequest(UnifiedMessage, um_name="Community.RateCommentThread"):
    type: str = betterproto.string_field(1)
    id64: int = betterproto.fixed64_field(2)
    forum_id: int = betterproto.fixed64_field(3)
    topic_id: int = betterproto.fixed64_field(4)
    id: int = betterproto.fixed64_field(5)
    rate_up: bool = betterproto.bool_field(6)
    suppress_notifications: bool = betterproto.bool_field(7)


class RateCommentThreadResponse(UnifiedMessage, um_name="Community.RateCommentThread"):
    id: int = betterproto.fixed64_field(1)
    thread_id: int = betterproto.uint64_field(2)
    count: int = betterproto.uint32_field(3)
    upvotes: int = betterproto.uint32_field(4)
    has_upvoted: bool = betterproto.bool_field(5)


class GetCommentThreadRatingsRequest(UnifiedMessage, um_name="Community.GetCommentThreadRatings"):
    type: str = betterproto.string_field(1)
    id64: int = betterproto.uint64_field(2)
    forum_id: int = betterproto.uint64_field(3)
    topic_id: int = betterproto.uint64_field(4)
    comment_id: int = betterproto.uint64_field(5)
    max_results: int = betterproto.uint32_field(6)


class GetCommentThreadRatingsResponse(UnifiedMessage, um_name="Community.GetCommentThreadRatings"):
    thread_id: int = betterproto.uint64_field(1)
    comment_id: int = betterproto.uint64_field(2)
    upvotes: int = betterproto.uint32_field(3)
    has_upvoted: bool = betterproto.bool_field(4)
    upvoter_ids: list[int] = betterproto.uint32_field(5)


class RateClanAnnouncementRequest(UnifiedMessage, um_name="Community.RateClanAnnouncement"):
    announcementid: int = betterproto.uint64_field(1)
    vote_up: bool = betterproto.bool_field(2)
    clan_accountid: int = betterproto.uint32_field(3)


class RateClanAnnouncementResponse(UnifiedMessage, um_name="Community.RateClanAnnouncement"):
    pass
