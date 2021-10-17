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

import re
import warnings
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar, overload

from typing_extensions import Literal, TypedDict

from . import utils
from .enums import Enum_, ReviewType
from .models import URL
from .utils import Intable, id64_from_url

if TYPE_CHECKING:
    from .clan import Clan
    from .state import ConnectionState
    from .user import User

__all__ = (
    "TF2",
    "Game",
    "CSGO",
    "DOTA2",
    "LFD2",
    "STEAM",
    "CUSTOM_GAME",
    "UserGame",
    "WishlistGame",
    "FetchedGame",
)

T = TypeVar("T")
APP_ID_MAX = 2 ** 32


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


class WishlistGameDict(TypedDict):
    name: str
    capsule: str
    review_score: int
    review_desc: str
    reviews_total: str
    reviews_percent: int
    release_date: int
    release_string: str
    platform_icons: str
    subs: list[dict[str, Any]]
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


class PackageGroupsDict(TypedDict):
    name: Literal["default", "subscriptions"]
    title: str
    description: str
    selection_text: str
    display_type: Literal[0, 1]
    is_recurring_subscription: bool
    subs: list[dict[str, str]]


class FetchedGameDict(TypedDict):
    # https://wiki.teamfortress.com/wiki/User:RJackson/StorefrontAPI#Result_data_3
    type: Literal["game", "dlc", "demo", "advertising", "mod", "video"]
    name: str
    steam_appid: int
    required_age: int
    is_free: bool
    controller_support: Literal["partial", "full"]
    dlc: list[int]
    detailed_description: str
    short_description: str
    fullgame: dict[str, Any]
    supported_languages: str
    header_image: str
    pc_requirements: list[dict[str, str]]
    mac_requirements: list[dict[str, str]]
    linux_requirements: list[dict[str, str]]
    legal_notice: str
    developers: list[str]
    publishers: list[str]
    demos: list[dict[str, Any]]
    price_overview: list[dict[str, Any]]
    package_groups: list[PackageGroupsDict]
    platforms: dict[str, bool]
    metacritic: list[dict[str, str]]
    categories: list[dict[str, str]]
    release_date: dict[str, str]
    background: str
    website: str
    movies: list[dict[str, Any]]


class Game:
    """Represents a Steam game.

    Attributes
    ----------
    name
        The game's name.
    id
        The game's app ID.
    context_id
        The context id of the game normally ``2``.
    """

    __slots__ = (
        "id",
        "name",
        "context_id",
    )

    @overload
    def __init__(self, *, id: Intable, name: str | None = ..., context_id: int | None = ...):
        ...

    @overload
    def __init__(self, *, name: Literal["Team Fortress 2"], id: Intable = ..., context_id: int | None = ...):
        ...

    @overload
    def __init__(self, *, name: Literal["Left 4 Dead 2"], id: Intable = ..., context_id: int | None = ...):
        ...

    @overload
    def __init__(self, *, name: Literal["DOTA 2"], id: Intable = ..., context_id: int | None = ...):
        ...

    @overload
    def __init__(
        self, *, name: Literal["Counter Strike Global-Offensive"], id: Intable = ..., context_id: int | None = ...
    ):
        ...

    @overload
    def __init__(self, *, name: Literal["Steam"], id: Intable = ..., context_id: int | None = ...):
        ...

    def __init__(
        self,
        *,
        id: Intable | None = None,
        name: str | None = None,
        title: str | None = None,
        context_id: int | None = None,
    ):
        if title is not None:
            warnings.warn("Game.title is depreciated, use Game.name instead", DeprecationWarning)
        name = name or title
        if name is None and id is None:
            raise TypeError("__init__() missing a required keyword argument: 'id' or 'name'")

        if name is None:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError("id expected to support int()")
            try:
                name = Games(id).name
            except ValueError:
                name = None
            else:
                if name == "Steam" and context_id is None:
                    context_id = 6
        elif id is None:
            id = utils.get(Games, name=name)
            if id is None:
                raise ValueError(f"Cannot find a matching game for {name!r}")
        else:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError("id must be an int") from None

        if id < 0:
            raise ValueError("id cannot be negative")

        self.id: int = id
        self.name: str | None = name
        self.context_id: int = 2 if context_id is None else context_id

    def __str__(self) -> str:
        return self.name or ""

    def __repr__(self) -> str:
        attrs = ("name", "id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"{self.__class__.__name__}({', '.join(resolved)})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Game):
            return NotImplemented
        return self.id == other.id

    @property
    def title(self) -> str | None:
        """The game's name.

        .. deprecated:: 0.8.0

            Use :attr:`name` instead.
        """
        warnings.warn("Game.title is depreciated, use Game.name instead", DeprecationWarning, stacklevel=2)
        return self.name

    def to_dict(self) -> GameToDict:
        if self.is_steam_game():
            return {"game_id": str(self.id)}

        if self.name is None or self.id is None:
            raise TypeError("unserializable game with no title and or id")
        return {"game_id": str(self.id), "game_extra_info": self.name}

    def is_steam_game(self) -> bool:
        """Whether the game could be a Steam game."""
        return bool(self.id is not None and self.id <= APP_ID_MAX)

    @property
    def url(self) -> str:
        """What should be the game's url on steamcommunity if applicable."""
        return f"{URL.COMMUNITY}/app/{self.id}"


class Games(Game, Enum_):
    """This is "enum" to trick type checkers into allowing Literal[TF2] to be valid for overloads in extensions."""

    __slots__ = ("_name",)

    def __new__(cls, *, name: str, value: tuple[str, int, int]) -> Games:
        self = object.__new__(cls)
        set_attribute = object.__setattr__
        set_attribute(self, "_name", name)
        set_attribute(self, "name", value[0])
        set_attribute(self, "id", value[1])
        set_attribute(self, "context_id", value[2])
        return self

    def __repr__(self) -> str:
        return self._name

    TF2 = "Team Fortress 2", 440, 2
    LFD2 = "Left 4 Dead 2", 550, 2
    DOTA2 = "DOTA 2", 570, 2
    CSGO = "Counter Strike Global-Offensive", 730, 2
    STEAM = "Steam", 753, 6


TF2 = Games.TF2
DOTA2 = Games.DOTA2
CSGO = Games.CSGO
LFD2 = Games.LFD2
STEAM = Games.STEAM


@overload
def CUSTOM_GAME(name: str) -> Game:  # type: ignore
    ...


def CUSTOM_GAME(name: str = None, title: str = None) -> Game:
    """Create a custom game instance for :meth:`~steam.Client.change_presence`.
    The :attr:`Game.id` will be set to ``15190414816125648896`` and the :attr:`Game.context_id` to ``None``.

    Example:

    .. code-block:: python3

        await client.change_presence(game=steam.CUSTOM_GAME("my cool game"))

    Parameters
    ----------
    name
        The name of the game to set your playing status to.
    """
    if name is None and title is None:
        raise TypeError("CUSTOM_GAME missing argument 'name'")
    return Game(name=name or title, id=15190414816125648896, context_id=None)


class StatefulGame(Game):
    """Games that have state."""

    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, **kwargs: Any):
        super().__init__(**kwargs)
        self._state = state

    async def clan(self) -> Clan:
        """Fetch this game's clan.

        This can be useful to get a Game's updates.

        .. code-block:: python3

            clan = await game.clan()
            async for update in clan.announcements().filter(
                lambda announcement: announcement.type in (steam.ClanEvent.MajorUpdate, steam.ClanEvent.SmallUpdate)
            ):
                ...  # do something with the update

        Raises
        ------
        :exc:`ValueError`
            This game has no associated clan.
        """

        id64 = await id64_from_url(self.url, self._state.http._session)
        if id64 is None:
            raise ValueError("Game has no associated clan")
        clan = await self._state.fetch_clan(id64)
        if clan is None:
            raise ValueError("Game has no associated clan")
        return clan

    async def player_count(self) -> int:
        """The games current player count."""
        return await self._state.fetch_game_player_count(self.id)

    async def friends_who_own(self) -> list[User]:
        """Fetch the users in your friend list who own this game."""
        id64s = await self._state.fetch_friends_who_own(self.id)
        return [self._state.get_user(id64) for id64 in id64s]  # type: ignore  # friends are always cached

    # async def fetch(self) -> Self & FetchedGame:  # TODO update signature to this when types.Intersection is done
    #     fetched = await self._state.client.fetch_game(self)
    #     return utils.update_class(fetched, copy.copy(self))

    async def fetch(self) -> FetchedGame:
        """Short hand for:

        .. code-block:: python3

            game = await client.fetch_game(game)
        """
        game = await self._state.client.fetch_game(self)
        if game is None:
            raise ValueError("Fetched game was not valid.")
        return game


class UserGame(StatefulGame):
    """Represents a Steam game fetched by :meth:`steam.User.games`

    Attributes
    ----------
    total_play_time
        The total time the game has been played for.
    icon_url
        The icon url of the game.
    logo_url
        The logo url of the game.
    """

    __slots__ = (
        "total_play_time",
        "icon_url",
        "logo_url",
        "_stats_visible",
    )

    name: str

    def __init__(self, state: ConnectionState, data: GameDict):
        super().__init__(state=state, id=data["appid"], name=data["name"])
        self.total_play_time: timedelta = timedelta(minutes=data["playtime_forever"])
        self.icon_url = (
            f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{self.id}/"
            f"{data['img_icon_url']}.jpg"
        )
        self.logo_url = (
            f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{self.id}/"
            f"{data['img_logo_url']}.jpg"
        )
        self._stats_visible = data.get("has_community_visible_stats", False)

    def has_visible_stats(self) -> bool:
        """Whether the game has publicly visible stats."""
        return self._stats_visible


class WishlistGame(StatefulGame):
    """Represents a Steam game fetched by :meth:`steam.User.wishlist`\\.

    Attributes
    ----------
    priority
        The priority of the game in the wishlist.
    added_at
        The time the the game was added to their wishlist.
    created_at
        The time the game was uploaded at.
    background_url
        The background URL of the game.
    rank
        The global rank of the game by popularity.
    review_status
        The review status of the game.
    score
        The score of the game out of ten.
    screenshots
        The screenshots of the game.
    tags
        The tags of the game.
    total_reviews
        The total number reviews for the game.
    type
        The type of the app.
    logo_url
        The logo url of the game.
    """

    __slots__ = (
        "priority",
        "added_at",
        "background_url",
        "created_at",
        "logo_url",
        "rank",
        "review_status",
        "score",
        "screenshots",
        "tags",
        "total_reviews",
        "type",
        "_free",
        "_on_linux",
        "_on_mac_os",
        "_on_windows",
    )

    name: str

    def __init__(self, state: ConnectionState, id: int | str, data: WishlistGameDict):
        super().__init__(state, id=id, name=data["name"])
        self.logo_url = data["capsule"]
        self.score = data["review_score"]
        self.total_reviews = int(data["reviews_total"].replace(",", ""))
        self.review_status = ReviewType[data["review_desc"].replace(" ", "")]
        self.created_at = datetime.utcfromtimestamp(int(data["release_date"]))
        self.type: str = data["type"]
        self.screenshots = [
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{self.id}/{screenshot_url}"
            for screenshot_url in data["screenshots"]
        ]
        self.added_at = datetime.utcfromtimestamp(data["added"])
        self.background_url = data["background"]
        self.tags = data["tags"]
        self.rank = data["rank"]
        self.priority = int(data["priority"])

        self._free = data["is_free_game"]
        self._on_windows = bool(data.get("win", False))
        self._on_mac_os = bool(data.get("mac", False))
        self._on_linux = bool(data.get("linux", False))

    def is_free(self) -> bool:
        """Whether or not the game is free to download."""
        return self._free

    def is_on_windows(self) -> bool:
        """Whether or not the game is able to be played on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether or not the game is able to be played on MacOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether or not the game is able to be played on Linux."""
        return self._on_linux


class Movie:
    __slots__ = ("name", "id", "url", "created_at")

    def __init__(self, movie: dict[str, Any]):
        self.name: str = movie["name"]
        self.id: int = movie["id"]
        self.url: str = movie["mp4"]["max"]
        match = re.search(r"t=(\d+)", self.url)
        self.created_at = datetime.utcfromtimestamp(int(match.group(1))) if match else None

    def __repr__(self) -> str:
        attrs = ("name", "id", "url", "created_at")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Movie {' '.join(resolved)}>"


class FetchedGame(StatefulGame):
    """Represents a Steam game fetched by :meth:`steam.Client.fetch_game`\\.

    Attributes
    ----------
    created_at
        The time the game was uploaded at.
    background_url
        The background URL of the game.
    type
        The type of the app.
    logo_url
        The logo URL of the game.
    dlc
        The game's downloadable content.
    website_url
        The website URL of the game.
    developers
        The developers of the game.
    publishers
        The publishers of the game.
    description
        The short description of the game.
    full_description
        The full description of the game.
    movies
        A list of the game's movies, each of which has ``name``\\, ``id``\\, ``url`` and optional
        ``created_at`` attributes.
    """

    __slots__ = (
        "logo_url",
        "background_url",
        "created_at",
        "type",
        "dlc",
        "website_url",
        "developers",
        "publishers",
        "description",
        "full_description",
        "movies",
        "_free",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
    )

    title: str

    def __init__(self, state: ConnectionState, data: FetchedGameDict):
        super().__init__(state, id=data["steam_appid"], name=data["name"])
        self.logo_url = data["header_image"]
        self.background_url = data["background"]
        self.created_at = (
            datetime.strptime(data["release_date"]["date"], "%d %b, %Y") if data["release_date"]["date"] else None
        )
        self.type = data["type"]

        self.dlc = [Game(id=dlc_id) for dlc_id in data["dlc"]] if "dlc" in data else None
        self.website_url = data.get("website")
        self.developers = data["developers"]
        self.publishers = data["publishers"]
        self.description = data["short_description"]
        self.full_description = data["detailed_description"]

        self.movies = [Movie(movie) for movie in data["movies"]] if "movies" in data else None

        self._free = data["is_free"]
        self._on_windows = bool(data["platforms"].get("windows", False))
        self._on_mac_os = bool(data["platforms"].get("mac", False))
        self._on_linux = bool(data["platforms"].get("linux", False))

    def is_free(self) -> bool:
        """Whether or not the game is free to download."""
        return self._free

    def is_on_windows(self) -> bool:
        """Whether or not the game is able to be played on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether or not the game is able to be played on MacOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether or not the game is able to be played on Linux."""
        return self._on_linux
