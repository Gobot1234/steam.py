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

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Optional, TypeVar, overload

from typing_extensions import TypedDict

from .enums import EReviewType, IntEnum

if TYPE_CHECKING:
    from .utils import Intable

__all__ = (
    "TF2",
    "Game",
    "CSGO",
    "DOTA2",
    "STEAM",
    "CUSTOM_GAME",
    "UserGame",
    "WishlistGame",
)

T = TypeVar("T")
APP_ID_MAX = 2 ** 32


class Games(IntEnum):
    Team_Fortress_2 = 440
    DOTA_2 = 570
    Counter_Strike_Global__Offensive = 730
    Steam = 753


class GameDict(TypedDict):
    name: str
    appid: str
    playtime_forever: int
    img_icon_url: str
    img_logo_url: str
    has_community_visible_stats: bool


class GameToDict(TypedDict, total=False):
    game_id: str
    game_extra_info: str


class WishlistDict(TypedDict):
    name: str
    capsule: str
    review_score: int
    review_desc: str
    reviews_total: str
    reviews_percent: int
    release_date: int
    release_string: str
    platform_icons: str
    subs: list[dict]
    type: str
    screenshots: list[str]
    review_css: str
    priority: int
    added: int
    background: str
    rank: int
    tags: list[str]
    is_free_game: bool
    win: bool
    mac: bool
    linux: bool


class Game:
    """Represents a Steam game.

    Parameters
    ----------
    title: Optional[:class:`str`]
        The game's title.
    id: Optional[:class:`int`]
        The game's app ID.
    context_id: Optional[:class:`int`]
        The game's context ID by default 2.

    Attributes
    -----------
    title: Optional[:class:`str`]
        The game's title.
    id: :class:`int`
        The game's app ID.
    context_id: :class:`int`
        The context id of the game normally ``2``.
    """

    __slots__ = (
        "id",
        "title",
        "context_id",
    )

    @overload
    def __init__(self, *, id: Intable, context_id: Optional[int] = None):
        ...

    @overload
    def __init__(self, *, title: str, context_id: Optional[int] = None):
        ...

    @overload
    def __init__(self, *, id: Intable, title: str, context_id: Optional[int] = None):
        ...

    @overload
    def __init__(self, *, id: Optional[Intable] = None, title: Optional[str] = None, context_id: Optional[int] = None):
        ...

    def __init__(self, *, id: Optional[Intable] = None, title: Optional[str] = None, context_id: Optional[int] = None):
        if title is None and id is None:
            raise TypeError("__init__() missing a required keyword argument: 'id' or 'title'")

        if title is None:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError(f"id expected to support int()")
            try:
                title = Games(id).name.replace("__", "-").replace("_", " ")
            except ValueError:
                title = None
            else:
                if title == "Steam" and context_id is None:
                    context_id = 6
        elif id is None:
            try:
                id = Games[title.replace(" ", "_").replace("-", "__")].value
            except KeyError:
                id = 0
        else:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError("id must be an int") from None

        if id < 0:
            raise ValueError("id cannot be negative")

        self.id: Optional[int] = id
        self.title: Optional[str] = title
        self.context_id = 2 if context_id is None else context_id

    def __str__(self) -> str:
        return self.title or ""

    def __repr__(self) -> str:
        attrs = ("title", "id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"{self.__class__.__name__}({', '.join(resolved)})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Game):
            return NotImplemented
        return self.id == other.id or self.title == other.title

    def to_dict(self) -> GameToDict:
        """dict[:class:`str`, :class:`str`]: The dict representation of the game used to set presences."""
        return (
            {"game_id": str(self.id)}
            if self.is_steam_game()
            else {"game_id": str(self.id), "game_extra_info": self.title}
        )

    def is_steam_game(self) -> bool:
        """:class:`bool`: Whether the game could be a Steam game."""
        return self.id <= APP_ID_MAX


TF2 = Game(title="Team Fortress 2")
DOTA2 = Game(title="DOTA 2")
CSGO = Game(title="Counter Strike Global-Offensive")
STEAM = Game(title="Steam", context_id=6)


def CUSTOM_GAME(title: str) -> Game:
    """Create a custom game instance for :meth:`~steam.Client.change_presence`.
    The :attr:`Game.id` will be set to ``15190414816125648896`` and the :attr:`Game.context_id` to ``None``.

    Example: ::

        await client.change_presence(game=steam.CUSTOM_GAME('my cool game'))

    Parameters
    ----------
    title: :class:`str`
        The name of the game to set your playing status to.

    Returns
    -------
    class:`Game`
        The created custom game.
    """
    return Game(title=title, id=15190414816125648896, context_id=None)


class UserGame(Game):
    """Represents a Steam game fetched by :meth:`steam.User.games`

    Attributes
    ----------
    total_play_time: :class:`datetime.timedelta`
        The total time the game has been played for.
    icon_url: Optional[:class:`str`]
        The icon url of the game.
    logo_url: Optional[:class:`str`]
        The logo url of the game.
    """

    __slots__ = (
        "total_play_time",
        "icon_url",
        "logo_url",
        "_stats_visible",
    )

    def __init__(self, data: GameDict):
        super().__init__(id=data.get("appid"), title=data.get("name"))
        self.total_play_time: timedelta = timedelta(minutes=data.get("playtime_forever", 0))
        self.icon_url: str = (
            f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{self.id}/"
            f"{data['img_icon_url']}.jpg"
        )
        self.logo_url: str = (
            f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{self.id}/"
            f"{data['img_logo_url']}.jpg"
        )
        self._stats_visible = data.get("has_community_visible_stats", False)

    def has_visible_stats(self) -> bool:
        """:class:`bool`: Whether the game has publicly visible stats.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
        """
        return self._stats_visible


class WishlistGame(Game):
    """Represents a Steam game fetched by :meth:`steam.User.wishlist`

    Attributes
    ----------
    priority: :class:`int`
        The priority of the game.
    added_at: :class:`.datetime`
        The time the the game was added to their wishlist.
    created_at: :class:`.datetime`
        The time the game was uploaded at.
    background: :class:`str`
        The background of the game.
    rank: :class:`int`
        The global rank of the game by popularity.
    review_status: :class:`.EReviewType`
        The review status of the game.
    score: :class:`int`
        The score of the game out of ten.
    screenshots: list[:class:`str`]
        The screenshots of the game.
    tags: list[:class:`str`]
        The tags of the game.
    total_reviews: :class:`int`
        The total number reviews for the game.
    type: :class:`str`
        The type of the app.
    logo_url: :class:`str`
        The logo url of the game.
    """

    __slots__ = (
        "priority",
        "added_at",
        "background",
        "created_at",
        "logo_url",
        "rank",
        "review_status",
        "score",
        "screenshots",
        "tags",
        "total_reviews",
        "type",
        "_is_free_game",
        "_on_linux",
        "_on_mac_os",
        "_on_windows",
    )

    def __init__(self, id: int, data: WishlistDict):
        super().__init__(id=id, title=data["name"])
        self.logo_url = data["capsule"]
        self.score = data["review_score"]
        self.total_reviews = int(data["reviews_total"].replace(",", ""))
        self.review_status = EReviewType(data["review_desc"])
        self.created_at = datetime.utcfromtimestamp(int(data["release_date"]))
        self.type = data["type"]
        self.screenshots: list[str] = [
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{self.id}/{screenshot_url}"
            for screenshot_url in data["screenshots"]
        ]
        self.added_at = datetime.utcfromtimestamp(data["added"])
        self.background = data["background"]
        self.tags = data["tags"]
        self.rank = data["rank"]
        self.priority = int(data["priority"])

        self._is_free_game = data["is_free_game"]
        self._on_windows = bool(data.get("win", False))
        self._on_mac_os = bool(data.get("mac", False))
        self._on_linux = bool(data.get("linux", False))

    def is_free(self) -> bool:
        """:class:`bool`: Whether or not the game is free to download."""
        return self._is_free_game

    def is_on_windows(self) -> bool:
        """:class:`bool`: Whether or not the game is able to be played on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """:class:`bool`: Whether or not the game is able to be played on MacOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """:class:`bool`: Whether or not the game is able to be played on Linux."""
        return self._on_linux
