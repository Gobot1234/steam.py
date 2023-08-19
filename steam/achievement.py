"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from ._const import URL
from .models import CDNAsset
from .utils import DateTime

if TYPE_CHECKING:
    from datetime import datetime

    from .app import App, PartialApp
    from .enums import Language
    from .protobufs import user_stats
    from .state import ConnectionState
    from .types import achievement

__all__ = (
    "AppStat",
    "UserAppStat",
    "AppAchievement",
    "AppStatAchievement",
    "UserAppAchievement",
    "AppStats",
    "UserAppStats",
)


class StatType:  # https://partner.steamgames.com/doc/api/steam_api#ESteamUserStatType
    Int: Final = "1"
    Float: Final = "2"
    AverageRate: Final = "3"
    Achievement: Final = "4"
    GroupAchievement: Final = "5"


@dataclass(slots=True)
class Stat:
    name: str
    """The name of the stat."""
    display_name: str
    """The display name of the stat."""
    app: PartialApp
    """The app this stat is for."""


@dataclass(slots=True)
class AppStat(Stat):
    """Represents a stat for an app."""

    default_value: int
    """The value of the stat."""


@dataclass(slots=True)
class UserAppStat(Stat):
    """Represents a stat for a user in an app."""

    increment_only: bool
    """Whether the stat can only be incremented."""
    value: int = field(init=False)
    """The value of the stat."""


@dataclass(slots=True)
class Achievement:
    name: str
    """The name of the achievement."""
    app: PartialApp
    """The app this achievement is for."""


@dataclass(slots=True)
class AppAchievement(Achievement):
    """Represents an achievement for an app."""

    display_name: str
    """The display name of the achievement."""
    description: str
    """The description of the achievement."""
    icon: CDNAsset
    """The icon of the achievement."""
    icon_gray: CDNAsset
    """The gray icon of the achievement."""
    hidden: bool
    """Whether the achievement is hidden from the app's achievement list."""
    global_percent_unlocked: float
    """The percentage of the players that have this achievement."""


@dataclass(slots=True)
class UserNewsAchievement(Achievement):
    """Represents an achievement for an app."""

    display_name: str
    """The display name of the achievement."""
    description: str
    """The description of the achievement."""
    icon: CDNAsset
    """The icon of the achievement."""
    hidden: bool
    """Whether the achievement is hidden from the app's achievement list."""
    percent_unlocked: float
    """The percentage of the players that have this achievement."""


@dataclass(slots=True)
class AppStatAchievement(Achievement):
    """Represents an achievement for an app."""

    display_name: str
    """The localised name of the achievement."""
    description: str
    """The description of the achievement."""
    default_value: int
    """The default value of the stat."""
    icon: CDNAsset
    """The icon of the achievement."""
    icon_gray: CDNAsset
    """The gray icon of the achievement."""
    hidden: bool
    """Whether the achievement is hidden from the app's achievement list."""


@dataclass(slots=True)
class UserAppAchievement(Achievement):
    """Represents an achievement for a user in an app."""

    display_name: str
    """The localised name of the achievement."""
    min: int | None
    """The minimum value of the stat."""
    max: int | None
    """The maximum value of the achievement."""
    icon: CDNAsset
    """The icon of the achievement."""
    icon_gray: CDNAsset
    """The gray icon of the achievement."""
    hidden: bool
    """Whether the achievement is hidden from the app's achievement list."""
    description: str
    """The description of the achievement."""
    unlocked_at: datetime | None = field(init=False)
    """The time the achievement was unlocked at."""


# This currently isn't useful cause it doesn't include the internal name or the time the player unlocked the
# achievement
# @dataclass(slots=True)
# class UserAchievement(Achievement):
#     description: str
#     """The description of the achievement."""
#     icon: CDNAsset
#     """The icon of the achievement."""
#     icon_gray: CDNAsset
#     """The gray icon of the achievement."""
#     hidden: bool
#     """Whether the achievement is hidden from the app's achievement list."""
#     global_percent_unlocked: float
#     """The percentage of the players that have this achievement."""


class AppStats:
    """Represents a collection of stats and achievements for an app."""

    def __init__(self, state: ConnectionState, app: App, data: achievement.AppAppStats) -> None:
        from .app import PartialApp

        self.app = PartialApp(state, id=app.id, name=data["gameName"])
        """The app these stats and achievement are for."""
        self.version = int(data["gameVersion"])
        """The version of the schema used to generate the stats and achievements."""
        self.achievements = [
            AppStatAchievement(
                achievement["name"],
                self.app,
                achievement["displayName"],
                achievement["description"],
                achievement["defaultvalue"],
                CDNAsset(state, achievement["icon"]),
                CDNAsset(state, achievement["icongray"]),
                bool(achievement["hidden"]),
            )
            for achievement in data["availableGameStats"].get("achievements", [])
        ]
        """The achievements for the app."""
        self.stats = [
            AppStat(
                stat["name"],
                stat["displayName"],
                self.app,
                stat["defaultvalue"],
            )
            for stat in data["availableGameStats"].get("stats", [])
        ]
        """The stats for the app."""

    def __repr__(self) -> str:
        return f"<AppStats app={self.app!r}>"


class UserAppStats:
    """Represents a collection of stats and achievements for a user in an app."""

    def __init__(
        self,
        state: ConnectionState,
        app: App,
        msg: user_stats.CMsgClientGetUserStatsResponse,
        data: achievement.UserAppStats,
        language: Language,
    ) -> None:
        from .app import PartialApp

        self.app = PartialApp(state, id=app.id, name=data["gamename"])
        """The app these stats and achievement are for."""
        self.version = int(data["version"])
        """The version of the schema used to generate the stats and achievements."""
        achievements = {
            int(achievement_["id"]): [
                UserAppAchievement(
                    achievement["name"],
                    self.app,
                    (display := achievement["display"])["name"].get(language.api_name, ""),
                    (
                        int(progress["min_value"])
                        if (progress := achievement.get("progress")) and "min_value" in progress
                        else None
                    ),
                    int(progress["max_value"]) if progress and "max_value" in progress else None,
                    CDNAsset(
                        state,
                        f"{URL.CDN}/steamcommunity/public/images/apps/{app.id}/{display['icon']}",
                    ),
                    CDNAsset(
                        state,
                        f"{URL.CDN}/steamcommunity/public/images/apps/{app.id}/{display['icon_gray']}",
                    ),
                    bool(int(display["hidden"])),
                    display["desc"].get(language.api_name, ""),
                )
                for achievement in achievement_["bits"].values()
            ]
            for achievement_ in data["stats"].values()
            if achievement_["type"] == StatType.Achievement
        }
        stats = {
            int(stat["id"]): UserAppStat(
                stat["name"],
                stat["display"].get("name", ""),
                self.app,
                bool(stat.get("incrementonly", False)),
            )
            for stat in data["stats"].values()
            if stat["type"] == StatType.Int
        }

        self.stats: list[UserAppStat] = []
        """The stats for the app."""
        self.achievements: list[UserAppAchievement] = []
        """The achievements for the app."""

        for stat in msg.stats:
            try:
                app_stat = stats[stat.stat_id]
            except KeyError:
                continue  # not really sure why this happens, they are in achievements for some reason
            app_stat.value = stat.stat_value
            self.stats.append(app_stat)

        # this is a contender for the worse steam API data representation there is
        # achievements are chunked into blocks of 32 and give each block an id, then the unlock_time are a list of the same length
        # and you have to zip them together to get the correct unlock time for each achievement after finding it in
        # doubly nested dict of the schema. Why??????
        for achievement in msg.achievement_blocks:
            for app_achievement, unlock_time in zip(achievements[achievement.achievement_id], achievement.unlock_time):
                app_achievement.unlocked_at = DateTime.from_timestamp(unlock_time) if unlock_time else None
                self.achievements.append(app_achievement)

    def __repr__(self) -> str:
        return f"<UserAppStats app={self.app!r}>"
