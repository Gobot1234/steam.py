# These were removed for some reason, pulled from:
# https://github.com/SteamDatabase/Protobufs/blob/master/webui/service_community.proto and its history.
# Last updated 9/9/2021

from dataclasses import dataclass
from typing import List

import betterproto

from .base import CMsgIpAddress


@dataclass(eq=False, repr=False)
class GetCommentThreadRequest(betterproto.Message):
    id64: int = betterproto.fixed64_field(1)
    thread_type: int = betterproto.uint32_field(2)
    gidfeature: int = betterproto.fixed64_field(3)
    gidfeature2: int = betterproto.fixed64_field(4)
    thread_id: int = betterproto.fixed64_field(5)
    start: int = betterproto.int32_field(6)
    count: int = betterproto.int32_field(7)
    upvotes: int = betterproto.int32_field(8)
    include_deleted: bool = betterproto.bool_field(9)
    id: int = betterproto.fixed64_field(10)
    time_oldest: int = betterproto.uint32_field(11)
    oldest_first: bool = betterproto.bool_field(12)


@dataclass(eq=False, repr=False)
class GetCommentThreadResponse(betterproto.Message):
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
            id: int = betterproto.uint32_field(1)
            count: int = betterproto.uint32_field(1)

        reactions: List[Reaction] = betterproto.message_field(12)
        parent_id: int = betterproto.fixed64_field(13)

    comments: List[Comment] = betterproto.message_field(1)
    deleted_comments: List[Comment] = betterproto.message_field(2)
    id64: int = betterproto.fixed64_field(3)
    thread_id: int = betterproto.fixed64_field(4)
    start: int = betterproto.int32_field(5)
    count: int = betterproto.int32_field(6)
    total_count: int = betterproto.int32_field(7)
    upvotes: int = betterproto.int32_field(8)
    upvoters: List[int] = betterproto.uint32_field(9)
    user_subscribed: bool = betterproto.bool_field(10)
    user_upvoted: bool = betterproto.bool_field(11)
    answer_id: int = betterproto.fixed64_field(12)
    answer_actor: int = betterproto.uint32_field(13)
    answer_actor_rank: int = betterproto.int32_field(14)
    can_post: bool = betterproto.bool_field(15)
    thread_type: int = betterproto.uint32_field(16)
    gidfeature: int = betterproto.fixed64_field(17)
    gidfeature2: int = betterproto.fixed64_field(18)


@dataclass(eq=False, repr=False)
class PostCommentToThreadRequest(betterproto.Message):
    id64: int = betterproto.fixed64_field(1)
    thread_type: int = betterproto.uint32_field(2)
    gidfeature: int = betterproto.fixed64_field(3)
    gidfeature2: int = betterproto.fixed64_field(4)
    content: str = betterproto.string_field(6)
    parent_id: int = betterproto.fixed64_field(7)
    suppress_notifications: bool = betterproto.bool_field(8)
    is_report: bool = betterproto.bool_field(9)


@dataclass(eq=False, repr=False)
class PostCommentToThreadResponse(betterproto.Message):
    id: int = betterproto.fixed64_field(1)
    thread_id: int = betterproto.fixed64_field(2)
    count: int = betterproto.int32_field(3)
    upvotes: int = betterproto.int32_field(4)


@dataclass(eq=False, repr=False)
class DeleteCommentFromThreadRequest(betterproto.Message):
    id64: int = betterproto.fixed64_field(1)
    thread_type: int = betterproto.uint32_field(2)
    gidfeature: int = betterproto.fixed64_field(3)
    gidfeature2: int = betterproto.fixed64_field(4)
    id: int = betterproto.fixed64_field(5)
    undelete: bool = betterproto.bool_field(6)


@dataclass(eq=False, repr=False)
class DeleteCommentFromThreadResponse(betterproto.Message):
    pass


@dataclass(eq=False, repr=False)
class RateCommentThreadRequest(betterproto.Message):
    thread_type: str = betterproto.string_field(1)
    id64: int = betterproto.fixed64_field(2)
    gidfeature: int = betterproto.fixed64_field(3)
    gidfeature2: int = betterproto.fixed64_field(4)
    id: int = betterproto.fixed64_field(5)
    rate_up: bool = betterproto.bool_field(6)
    suppress_notifications: bool = betterproto.bool_field(7)


@dataclass(eq=False, repr=False)
class RateCommentThreadResponse(betterproto.Message):
    id: int = betterproto.fixed64_field(1)
    thread_id: int = betterproto.uint64_field(2)
    count: int = betterproto.uint32_field(3)
    upvotes: int = betterproto.uint32_field(4)
    has_upvoted: bool = betterproto.bool_field(5)


@dataclass(eq=False, repr=False)
class GetCommentThreadRatingsRequest(betterproto.Message):
    thread_type: str = betterproto.string_field(1)
    id64: int = betterproto.uint64_field(2)
    gidfeature: int = betterproto.uint64_field(3)
    gidfeature2: int = betterproto.uint64_field(4)
    comment_id: int = betterproto.uint64_field(5)
    max_results: int = betterproto.uint32_field(6)


@dataclass(eq=False, repr=False)
class GetCommentThreadRatingsResponse(betterproto.Message):
    thread_id: int = betterproto.uint64_field(1)
    comment_id: int = betterproto.uint64_field(2)
    upvotes: int = betterproto.uint32_field(3)
    has_upvoted: bool = betterproto.bool_field(4)
    upvoter_ids: List[int] = betterproto.uint32_field(5)


@dataclass(eq=False, repr=False)
class RateClanAnnouncementRequest(betterproto.Message):
    announcementid: int = betterproto.uint64_field(1)
    vote_up: bool = betterproto.bool_field(2)
    clan_accountid: int = betterproto.uint32_field(3)


@dataclass(eq=False, repr=False)
class RateClanAnnouncementResponse(betterproto.Message):
    pass
