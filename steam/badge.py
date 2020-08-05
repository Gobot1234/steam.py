# -*- coding: utf-8 -*-

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

from datetime import datetime
from typing import List

from .enums import EUserBadge
from .game import Game

__all__ = (
    "Badge",
    "UserBadges",
)


class Badge:
    """Represents a Steam badge.

    Attributes
    ----------
    id: Union[:class:`.EUserBadge`, :class:`int`]
        The badge's ID.
    level: :class:`int`
        The badge's level.
    xp: :class:`int`
        The badge's XP.
    completion_time: :class:`datetime.datetime`
        The time the badge was completed at.
    scarcity: :class:`int`
        The scarcity of the badge.
    game: Optional[:class:`~steam.Game`]
        The game associated with the badge.
    """

    __slots__ = ("id", "xp", "game", "level", "scarcity", "completion_time")

    def __init__(self, data: dict):
        self.id = EUserBadge.try_value(data["badgeid"])
        self.level: int = data["level"]
        self.xp: int = data["xp"]
        self.completion_time = datetime.utcfromtimestamp(data["completion_time"])
        self.scarcity: int = data["scarcity"]
        self.game = Game(data["appid"]) if "appid" in data else None

    def __repr__(self):
        attrs = ("id", "level", "xp", "game")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f'<Badge {" ".join(resolved)}>'


class UserBadges:
    """Represents a Steam :class:`~steam.User`'s badges/level.

    Attributes
    ----------
    level: :class:`int`
        The badge's level.
    xp: :class:`int`
        The badge's XP.
    xp_needed_to_level_up: :class:`int`
        The amount of XP the user needs to level up.
    xp_needed_for_current_level: :class:`int`
        The amount of XP the user's current level requires to achieve.
    badges: List[:class:`Badge`]
        A list of the user's badges.
    """

    __slots__ = (
        "xp",
        "level",
        "badges",
        "xp_needed_to_level_up",
        "xp_needed_for_current_level",
    )

    def __init__(self, data: dict):
        self.level: int = data["player_level"]
        self.xp: int = data["player_xp"]
        self.xp_needed_to_level_up: int = data["player_xp_needed_to_level_up"]
        self.xp_needed_for_current_level: int = data["player_xp_needed_current_level"]
        self.badges: List[Badge] = [Badge(data) for data in data["badges"]]

    def __repr__(self):
        attrs = ("level", "xp")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f'<UserBadges {" ".join(resolved)}>'

    def __len__(self):
        return len(self.badges)
