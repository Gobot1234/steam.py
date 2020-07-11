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

__all__ = (
    "TF2",
    "Game",
    "CSGO",
    "DOTA2",
    "STEAM",
    "CUSTOM_GAME",
)

APP_ID_MAX = 2 ** 32

MAPPING = {
    "Team Fortress 2": [440, 2],
    "DOTA 2": [570, 2],
    "Counter Strike Global-Offensive": [730, 2],
    "Steam": [753, 6],
    440: ["Team Fortress 2", 2],
    570: ["DOTA 2", 2],
    730: ["Counter Strike Global-Offensive", 2],
    753: ["Steam", 6],
}


class Game:
    """Represents a Steam game.

    .. note::

        This class can be defined by users using the above parameters, or
        it can be from an API call this is when :meth:`~steam.User.fetch_games`
        is called.

    Parameters
    ----------
    title: Optional[:class:`str`]
        The game's title.
    app_id: Optional[:class:`int`]
        The game's app_id.
    context_id: Optional[:class:`int`]
        The games's context ID by default 2.

    Attributes
    -----------
    title: Optional[:class:`str`]
        The game's title.
    app_id: :class:`int`
        The game's app_id.
    context_id: :class:`int`
        The context id of the game normally 2.
    total_play_time: Optional[:class:`int`]
        The total time the game has been played for.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    icon_url: Optional[:class:`str`]
        The icon url of the game.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    logo_url: Optional[:class:`str`]
        The logo url of the game.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    stats_visible: Optional[:class:`bool`]
        Whether the game has publicly visible stats.
        Only applies to a :class:`~steam.User`'s games from :meth:`~steam.User.games`.
    """

    __slots__ = (
        "app_id",
        "title",
        "context_id",
        "total_play_time",
        "icon_url",
        "logo_url",
        "stats_visible",
    )

    def __init__(self, app_id: int = None, title: str = None, *, context_id: int = 2):
        if app_id is not None and title is None:
            try:
                self.app_id = int(app_id)
            except ValueError as exc:
                raise ValueError(f"app_id expected to be a digit not {repr(type(app_id).__name__)}") from exc
            if self.app_id < 0:
                raise ValueError("app_id cannot be negative")
            mapping = MAPPING.get(app_id)
            if mapping is not None:
                self.title = mapping[0]
                self.context_id = mapping[1]
            else:
                self.title = title
                self.context_id = context_id

        elif app_id is None and title is not None:
            mapping = MAPPING.get(title)
            if mapping is not None:
                self.app_id = mapping[0]
                self.context_id = mapping[1]
            else:
                self.app_id = app_id
                self.context_id = context_id
            self.title = title

        else:
            app_id = int(app_id)
            mapping = MAPPING.get(app_id)
            if mapping is not None:
                self.title = mapping[0]
                self.app_id = app_id
                self.context_id = mapping[1]
            else:
                self.title = title
                self.app_id = app_id
                self.context_id = context_id

            mapping = MAPPING.get(title)
            if mapping is not None:
                self.title = title
                self.app_id = mapping[0]
                self.context_id = mapping[1]
            else:
                self.title = title
                self.app_id = app_id
                self.context_id = context_id

        self.total_play_time = None
        self.icon_url = None
        self.logo_url = None
        self.stats_visible = None

    @classmethod
    def _from_api(cls, data):
        game = cls(app_id=data.get("appid"), title=data.get("name"))
        game.total_play_time = data.get("playtime_forever", 0)
        game.icon_url = data.get("img_icon_url")
        game.logo_url = data.get("img_logo_url")
        game.stats_visible = data.get("has_community_visible_stats", False)
        return game

    def __repr__(self):
        attrs = ("title", "app_id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Game {' '.join(resolved)}>"

    def __eq__(self, other):
        return isinstance(other, Game) and (self.app_id == other.app_id or self.title == other.title)

    def to_dict(self) -> dict:
        if not self.is_steam_game():
            return {"game_id": str(self.app_id), "game_extra_info": self.title}
        return {"game_id": str(self.app_id)}

    def is_steam_game(self) -> bool:
        return self.app_id <= APP_ID_MAX


TF2 = Game(title="Team Fortress 2", app_id=440)
DOTA2 = Game(title="DOTA 2", app_id=570)
CSGO = Game(title="Counter Strike Global-Offensive", app_id=730)
STEAM = Game(title="Steam", app_id=753, context_id=6)


def CUSTOM_GAME(title: str):
    """Create a custom game instance
    for :meth:`~steam.Client.change_presence`.

    Examples: ::
        await client.change_presence(game=steam.CUSTOM_GAME('my cool game'))

    Parameters
    ----------
    title: :class:`str`
        The name of the game to set your playing status to
    """
    return Game(title=title, app_id=15190414816125648896, context_id=0)
