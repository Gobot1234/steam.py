"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict

from typing_extensions import NotRequired, Required, TypeVar

from .http import ResponseDict
from .id import ID32

if TYPE_CHECKING:
    from ..abc import PartialUser
    from ..enums import Type
    from ..id import ID
    from ..user import ClientUser, User as User_
    from .id import ID64


class User(TypedDict):
    steamid: str
    personaname: str
    primaryclanid: str
    profileurl: str
    realname: str
    # enums
    communityvisibilitystate: int
    profilestate: int
    commentpermission: int
    personastate: int
    personastateflags: int
    # avatar
    avatar: str
    avatarmedium: str
    avatarfull: str
    avatarhash: str
    # country stuff
    loccountrycode: str
    locstatecode: int
    loccityid: int
    # game stuff
    gameid: str  # game app id
    gameextrainfo: str  # game name
    # unix timestamps
    timecreated: int
    lastlogoff: int


class InventoryInfo(TypedDict):
    appid: int
    name: str
    inventory_logo: str
    icon: str
    asset_count: int
    trade_permissions: str
    load_failed: int
    store_vetted: int
    owner_only: bool
    rgContexts: dict[Any, InventoryInfoContexts]


class InventoryInfoContexts(TypedDict):
    id: int
    name: str
    asset_count: int


class RawUserBan(TypedDict):
    SteamId: str
    CommunityBanned: bool
    VACBanned: bool
    NumberOfVACBans: int
    DaysSinceLastBan: int
    NumberOfGameBans: int
    EconomyBan: str


class UserBan(TypedDict):  # steam does such a horrific job exposing this I recreate the dict with lowered keys
    steamid: ID64
    community_banned: bool
    vac_banned: bool
    number_of_vac_bans: int
    days_since_last_ban: int
    number_of_game_bans: int
    economy_ban: str


class UserBadges(TypedDict):
    badges: list[UserBadgeBadge]
    player_xp: int
    player_level: int
    player_xp_needed_to_level_up: int
    player_xp_needed_current_level: int


class UserBadgeBadge(TypedDict):
    badgeid: int
    appid: NotRequired[int]
    level: int
    completion_time: int
    xp: int
    communityitemid: NotRequired[int]
    border_color: NotRequired[int]
    scarcity: int


class CommunityBadgeProgressQuest(TypedDict):
    questid: int
    completed: bool


class TradeHoldDurations(TypedDict):
    my_escrow: NotRequired[Escrow]
    their_escrow: NotRequired[Escrow]
    both_escrow: NotRequired[Escrow]


class Escrow(TypedDict, total=False):
    escrow_end_duration_seconds: Required[int]
    escrow_end_date: int
    escrow_end_date_rfc3339: str


class AuthenticateUserTicketParams(TypedDict):
    result: str
    steamid: str
    ownersteamid: str
    vacbanned: bool
    publisherbanned: bool


GetUserGroupList: TypeAlias = ResponseDict[dict[Literal["groups"], list[dict[Literal["gid"], ID32]]]]
GetPlayerBans: TypeAlias = dict[Literal["players"], list[RawUserBan]]
FriendsList: TypeAlias = dict[Literal["friendslist"], dict[Literal["friends"], list[dict[Literal["steamid"], str]]]]
AuthenticateUserTicket: TypeAlias = dict[Literal["params"], AuthenticateUserTicketParams]
GetSteamLevel: TypeAlias = ResponseDict[dict[Literal["player_level"], int]]

UserT = TypeVar("UserT", bound="PartialUser", default="PartialUser", covariant=True)  # for use when just from cache
Author: TypeAlias = "User_ | ClientUser | PartialUser"
AuthorT = TypeVar(
    "AuthorT", bound="PartialUser", default=Author, covariant=True
)  # for use when something comes from _maybe_user
IndividualID: TypeAlias = "ID[Literal[Type.Individual]]"
