"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .enums import UserBadge
from .game import StatefulGame

if TYPE_CHECKING:
    from .state import ConnectionState


__all__ = (
    "Badge",
    "FavouriteBadge",
    "UserBadges",
)


class BaseBadge:
    """
    Attributes
    ----------
    id
        The badge's ID.
    level
        The badge's level.
    game
        The game associated with the badge.
    """

    __slots__ = ()
    id: int
    level: int
    game: StatefulGame | None

    def __repr__(self) -> str:
        attrs = ("id", "level", "game")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self.id == other.id


@dataclass(repr=False)
class FavouriteBadge(BaseBadge):
    """Represents a User's favourite badge.

    Attributes
    ----------
    id
        The badge's ID.
    level
        The badge's level.
    game
        The game associated with the badge.
    item_id
        The badge's item's ID.
    type
        The badge's type.
    border_colour
        The colour of the boarder of the badge.
    """

    __slots__ = ("id", "level", "game", "item_id", "type", "border_colour")

    id: int
    level: int
    game: StatefulGame | None
    item_id: int
    type: int
    border_colour: int


class Badge(BaseBadge):
    """Represents a Steam badge.

    Attributes
    ----------
    id
        The badge's ID.
    level
        The badge's level.
    game
        The game associated with the badge.
    xp
        The badge's XP.
    completion_time
        The time the badge was completed at.
    scarcity
        The scarcity of the badge.
    """

    __slots__ = ("id", "xp", "game", "level", "scarcity", "completion_time")

    def __init__(self, state: ConnectionState, data: dict[str, Any]):
        self.id = UserBadge.try_value(data["badgeid"])
        self.level: int = data["level"]
        self.xp: int = data["xp"]
        self.completion_time = datetime.utcfromtimestamp(data["completion_time"])
        self.scarcity: int = data["scarcity"]
        self.game = StatefulGame(state, id=data["appid"]) if "appid" in data else None


class UserBadges:
    """Represents a Steam :class:`~steam.User`'s badges/level.

    Attributes
    ----------
    level
        The badge's level.
    xp
        The badge's XP.
    xp_needed_to_level_up
        The amount of XP the user needs to level up.
    xp_needed_for_current_level
        The amount of XP the user's current level requires to achieve.
    badges
        A list of the user's badges.
    """

    __slots__ = (
        "xp",
        "level",
        "badges",
        "xp_needed_to_level_up",
        "xp_needed_for_current_level",
    )

    def __init__(self, state: ConnectionState, data: dict[str, Any]):
        self.level: int = data["player_level"]
        self.xp: int = data["player_xp"]
        self.xp_needed_to_level_up: int = data["player_xp_needed_to_level_up"]
        self.xp_needed_for_current_level: int = data["player_xp_needed_current_level"]
        self.badges: Sequence[Badge] = [Badge(state, data) for data in data["badges"]]

    def __repr__(self) -> str:
        attrs = ("level", "xp")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f'<UserBadges {" ".join(resolved)}>'

    def __len__(self) -> int:
        return len(self.badges)
