"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict, final

from .vdf import TypedVDFDict, VDFBool, VDFInt, VDFList

if TYPE_CHECKING:
    from multidict import MultiDict
    from typing_extensions import NotRequired


class UserAppStats(TypedVDFDict):
    gamename: str
    version: VDFInt
    stats: VDFList[AppStat | AchievementStat]


class AppStatDisplay(TypedVDFDict):
    name: str


@final
class AppStat(TypedVDFDict):
    type: Literal["1"]
    name: str
    incrementonly: VDFBool
    display: AppStatDisplay
    id: VDFInt


class AchievementStatBitsDisplay(TypedVDFDict):
    name: MultiDict[str]
    """e.g.
    {
        "token": "TF_PLAY_GAME_FRIENDSONLY_NAME",
        "english": "With Friends Like these...",
        "german": "Kumpels",
    }
    """
    desc: MultiDict[str]  # same as above
    hidden: VDFBool
    icon: str  # https://cdn.akamai.steamstatic.com/steamcommunity/public/images/apps/440/ + this
    icon_gray: str


class AchievementStatBitsProgress(TypedVDFDict):
    min_value: NotRequired[VDFInt]
    max_value: NotRequired[VDFInt]
    value: MultiDict[str]


class AchievementStatBits(TypedVDFDict):
    name: str
    display: AchievementStatBitsDisplay
    progress: NotRequired[AchievementStatBitsProgress]
    bit: int  # actually an int lol


@final
class AchievementStat(TypedVDFDict):
    type: Literal["4"]
    bits: VDFList[AchievementStatBits]
    id: VDFInt


class AppAppStats(TypedDict):
    gameName: str
    gameVersion: int
    availableGameStats: AppAppStatsAvailableGameStats


class AppAppStatsAvailableGameStats(TypedDict):
    stats: NotRequired[list[AppAppStatsAvailableGameStatsStats]]
    achievements: NotRequired[list[AppStatsAvailableGameStatsAchievements]]


class AppAppStatsAvailableGameStatsStats(TypedDict):
    name: str
    defaultvalue: int
    displayName: str


class AppStatsAvailableGameStatsAchievements(TypedDict):
    name: str
    defaultvalue: int
    displayName: str
    hidden: bool  # 0 or 1
    description: str
    icon: str
    icongray: str
