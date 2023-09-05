from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict

if TYPE_CHECKING:
    from typing_extensions import Required

    from ..enums import EventType


class Event(TypedDict, total=False):
    gid: Required[int]
    clan_steamid: Required[int]
    event_name: Required[str]
    event_type: Required[EventType]
    appid: Required[int]
    server_address: str
    server_password: str
    rtime32_start_time: Required[int]
    rtime32_end_time: int
    comment_count: int
    creator_steamid: Required[int]
    last_update_steamid: int
    event_notes: Required[str]
    jsondata: str
    announcement_body: Required[AnnouncementBody]
    published: bool
    hidden: bool
    rtime32_visibility_start: int
    rtime32_visibility_end: int
    broadcaster_accountid: int
    follower_count: int
    ignore_count: int
    forum_topic_id: Required[int]
    gidfeature: Required[int]
    gidfeature2: int
    rtime32_last_modified: int
    news_post_gid: int
    rtime_mod_reviewed: Required[int]
    featured_app_tagid: int
    referenced_appids: list[int]
    build_id: int
    build_branch: str


class AnnouncementBody(TypedDict):
    gid: int
    clanid: int
    posterid: int
    headline: str
    posttime: int
    updatetime: int
    body: str
    commentcount: int
    tags: list[str]
    language: int
    hidden: bool
    forum_topic_id: int
    event_gid: int
    voteupcount: int
    votedowncount: int


GetClanEvents: TypeAlias = dict[Literal["events"], list[Event]]
GetClanAnnouncement: TypeAlias = dict[Literal["event"], Event]
