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

import re
from datetime import timedelta

from typing_extensions import Final
from yarl import URL as _URL

__all__ = (
    "PriceOverview",
    "Ban",
)


def api_route(path: str) -> _URL:
    """Format an API URL for usage with HTTPClient.request"""
    return URL.API / f'{path}{"/v1" if path[-2:] != "v2" else ""}'


def community_route(path: str) -> _URL:
    """Format a Steam Community URL for usage with HTTPClient.request"""
    return URL.COMMUNITY / path


def store_route(path: str) -> _URL:
    """Format a Steam store URL for usage with HTTPClient.request"""
    return URL.STORE / path


class URL:
    API: Final[_URL] = _URL("https://api.steampowered.com")
    COMMUNITY: Final[_URL] = _URL("https://steamcommunity.com")
    STORE: Final[_URL] = _URL("https://store.steampowered.com")


PRICE_REGEX = re.compile(r"(^\D*(?P<price>[\d,.]*)\D*$)")


class PriceOverview:
    """Represents the data received from https://steamcommunity.com/market/priceoverview.

    Attributes
    -------------
    currency: :class:`str`
        The currency identifier for the item eg. "$" or "£".
    volume: :class:`int`
        The amount of items are currently on the market.
    lowest_price: :class:`float`
        The lowest price observed by the market.
    median_price: :class:`float`
        The median price observed by the market.
    """

    __slots__ = ("currency", "volume", "lowest_price", "median_price")

    def __init__(self, data: dict):
        lowest_price = PRICE_REGEX.search(data["lowest_price"]).group("price")
        median_price = PRICE_REGEX.search(data["median_price"]).group("price")

        try:
            self.lowest_price = float(lowest_price.replace(",", "."))
            self.median_price = float(median_price.replace(",", "."))
        except (ValueError, TypeError):
            self.lowest_price = lowest_price
            self.median_price = median_price

        self.volume = int(data["volume"].replace(",", ""))
        self.currency = data["lowest_price"].replace(str(self.lowest_price).replace(",", "."), "")

    def __repr__(self):
        attrs = (
            "volume",
            "currency",
            "lowest_price",
            "median_price",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<PriceOverview {' '.join(resolved)}>"


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
        return f"<Ban {' '.join(resolved)}>"

    def is_banned(self) -> bool:
        """:class:`bool`: Species if the user is banned from any part of Steam."""
        return any((self.is_vac_banned(), self.is_community_banned(), self.is_market_banned()))

    def is_vac_banned(self) -> bool:
        """:class:`bool`: Species if the user is VAC banned."""
        return self._vac_banned

    def is_community_banned(self) -> bool:
        """:class:`bool`: Species if the user is community banned."""
        return self._community_banned

    def is_market_banned(self) -> bool:
        """:class:`bool`: Species if the user is market banned."""
        return self._market_banned


class Permissions:
    def __init__(self, proto):
        self.kick = proto.can_kick
        self.ban_members = proto.can_ban
        self.invite = proto.can_invite
        self.manage_group = proto.can_change_tagline_avatar_name
        self.send_messages = proto.can_chat
        self.read_message_history = proto.can_view_history
        self.change_group_roles = proto.can_change_group_roles
        self.change_user_roles = proto.can_change_user_roles
        self.mention_all = proto.can_mention_all
        self.set_watching_broadcast = proto.can_set_watching_broadcast
