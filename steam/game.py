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

from typing import Dict, Optional, SupportsInt, overload

from typing_extensions import TypedDict

from .enums import IntEnum

__all__ = (
    "TF2",
    "Game",
    "CSGO",
    "DOTA2",
    "STEAM",
    "CUSTOM_GAME",
)

APP_ID_MAX = 2 ** 32


class Games(IntEnum):
    Team_Fortress_2 = 440
    DOTA_2 = 570
    Counter_Strike_Global__Offensive = 730
    Steam = 753


class GameDict(TypedDict, total=False):
    game_id: str
    game_extra_info: str


class Game:
    """Represents a Steam game.

    .. note::

        This class can be defined by users using the above parameters, or it can be from an API call this is when
        :meth:`~steam.User.fetch_games` is called.

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
    total_play_time: Optional[:class:`int`]
        The total time the game has been played for.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    icon_url: Optional[:class:`str`]
        The icon url of the game.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    logo_url: Optional[:class:`str`]
        The logo url of the game.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    """

    __slots__ = (
        "id",
        "title",
        "context_id",
        "total_play_time",
        "icon_url",
        "logo_url",
        "_stats_visible",
    )

    @overload
    def __init__(self, app_id: SupportsInt, *, context_id: Optional[int] = 2):
        ...

    @overload
    def __init__(self, title: str, *, context_id: Optional[int] = 2):
        ...

    @overload
    def __init__(self, app_id: SupportsInt, title: str, *, context_id: Optional[int] = 2):
        ...

    @overload
    def __init__(self, id: Optional[SupportsInt], title: Optional[str] = None, *, context_id: Optional[int] = 2):
        ...

    def __init__(self, id=None, title=None, *, context_id=2):
        if title is None and id is None:
            raise TypeError("__init__() missing a required positional argument: 'id' or 'title'")
        if id is not None and title is None:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError(f"id expected to support int()")
            if id < 0:
                raise ValueError("id cannot be negative")
            try:
                title = Games(id).name.replace("__", "-").replace("_", " ")
            except ValueError:
                title = None
            else:
                if title == "Steam" and context_id is not None:
                    context_id = 6
        elif id is None and title is not None:
            try:
                id = Games[title.replace(" ", "_").replace("-", "__")].value
            except KeyError:
                id = 0

        else:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError("id must be an int") from None

        self.id: int = id
        self.title: Optional[str] = title
        self.context_id: Optional[int] = context_id

        self.total_play_time: Optional[int] = None
        self.icon_url: Optional[str] = None
        self.logo_url: Optional[str] = None
        self._stats_visible: Optional[bool] = None

    @classmethod
    def _from_api(cls, data: Dict[str, str]) -> "Game":
        game = cls(id=data.get("appid"), title=data.get("name"))
        game.total_play_time = data.get("playtime_forever", 0)
        game.icon_url = data.get("img_icon_url")
        game.logo_url = data.get("img_logo_url")
        game._stats_visible = data.get("has_community_visible_stats", False)
        return game

    def __str__(self) -> str:
        return self.title or ""

    def __repr__(self) -> str:
        attrs = ("title", "id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"Game({', '.join(resolved)})"

    def to_dict(self) -> GameDict:
        """:class:`Dict[:class:`str`, :class:`str`]: The dict representation of the game used to set presences."""
        if not self.is_steam_game():
            return {"game_id": str(self.id), "game_extra_info": self.title}
        return {"game_id": str(self.id)}

    def is_steam_game(self) -> bool:
        """:class:`bool`: Whether the game could be a Steam game."""
        return self.id <= APP_ID_MAX

    def has_visible_stats(self) -> bool:
        """:class:`bool`: Whether the game has publicly visible stats.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
        """
        return self._stats_visible


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
