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

from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protobufs.steammessages_chat import CChatRoleActions as RoleProto


__all__ = (
    "Ban",
    "Role",
)


class URL:
    API = "https://api.steampowered.com"
    COMMUNITY = "https://steamcommunity.com"
    STORE = "https://store.steampowered.com"


class Ban:
    """Represents a Steam ban.

    Attributes
    ----------
    since_last_ban: :class:`datetime.timedelta`
        How many days since the user was last banned
    number_of_game_bans: :class:`int`
        The number of game bans the User has.
    """

    __slots__ = (
        "since_last_ban",
        "number_of_game_bans",
        "_vac_banned",
        "_community_banned",
        "_market_banned",
    )

    def __init__(self, data: dict):
        self._vac_banned = data["VACBanned"]
        self._community_banned = data["CommunityBanned"]
        self._market_banned = data["EconomyBan"]
        self.since_last_ban = timedelta(days=data["DaysSinceLastBan"])
        self.number_of_game_bans = data["NumberOfGameBans"]

    def __repr__(self):
        attrs = [
            ("is_banned", self.is_banned()),
            ("is_vac_banned", self.is_vac_banned()),
        ]
        resolved = [f"{method}={value!r}" for method, value in attrs]
        return f'<Ban {" ".join(resolved)}>'

    def is_banned(self) -> bool:
        """:class:`bool`: Species if the user is banned from any part of Steam."""
        return True in (self.is_vac_banned(), self.is_community_banned(), self.is_market_banned(),)

    def is_vac_banned(self) -> bool:
        """:class:`bool`: Species if the user is VAC banned."""
        return self._vac_banned

    def is_community_banned(self) -> bool:
        """:class:`bool`: Species if the user is community banned."""
        return self._community_banned

    def is_market_banned(self) -> bool:
        """:class:`bool`: Species if the user is market banned."""
        return self._market_banned


class Role:
    def __init__(self, proto: "RoleProto"):
        self.id = int(proto.role_id)
        self.can_kick = proto.can_kick
        self.can_ban = proto.can_ban
        self.can_invite = proto.can_invite
        self.can_change_tagline_avatar_name = proto.can_change_tagline_avatar_name
        self.can_chat = proto.can_chat
        self.can_view_history = proto.can_view_history
        self.can_change_group_roles = proto.can_change_group_roles
        self.can_change_user_roles = proto.can_change_user_roles
        self.can_mention_all = proto.can_mention_all
        self.can_set_watching_broadcast = proto.can_set_watching_broadcast
