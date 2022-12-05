"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from typing import TYPE_CHECKING, TypeAlias

from typing_extensions import TypedDict, TypeVar


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
    # we pass these ourselves
    last_logon: int
    last_seen_online: int
    rich_presence: dict[str, str]


if TYPE_CHECKING:
    from ..abc import BaseUser, PartialUser
    from ..user import ClientUser, User as User_

UserT = TypeVar("UserT", bound="PartialUser", default="PartialUser", covariant=True)  # for use when just from cache
Author: TypeAlias = "User_ | ClientUser | PartialUser"
AuthorT = TypeVar(
    "AuthorT", bound="PartialUser", default=Author, covariant=True
)  # for use when something comes from _maybe_user
