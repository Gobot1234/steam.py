"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import re
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, NamedTuple, TypeVar, overload

from typing_extensions import Literal

from . import utils
from ._const import DOCS_BUILDING, URL
from .enums import AppFlag, Enum, Language, PublishedFileQueryFileType, PublishedFileRevision, ReviewType
from .iterators import GamePublishedFilesIterator, GameReviewsIterator, ManifestIterator
from .utils import DateTime, Intable, id64_from_url

if TYPE_CHECKING:
    from .clan import Clan
    from .friend import Friend
    from .manifest import Depot, GameInfo, HeadlessDepot, Manifest
    from .package import FetchedGamePackage
    from .protobufs import player
    from .review import Review
    from .state import ConnectionState
    from .types import game
    from .user import User

__all__ = (
    "Game",
    "TF2",
    "LFD2",
    "DOTA2",
    "CSGO",
    "STEAM",
    "CUSTOM_GAME",
    "DLC",
    "UserGame",
    "WishlistGame",
    "FetchedGame",
)

T = TypeVar("T")
APP_ID_MAX = 2**32 - 1


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

        if id is None:
            game = utils.get(Games, name=name)
            if game is None:
                raise ValueError(f"Cannot find a matching game for {name!r}")
            id = game.id
        else:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError("id expected to support int()") from None

            game = utils.get(Games, id=id)
            if game is not None:
                name = game.name

        if id < 0:
            raise ValueError("id cannot be negative")

        if name == "Steam" and context_id is None:
            context_id = 6

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
        return self.id == other.id if isinstance(other, Game) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def title(self) -> str | None:
        """The game's name.

        .. deprecated:: 0.8.0

            Use :attr:`name` instead.
        """
        warnings.warn("Game.title is depreciated, use Game.name instead", DeprecationWarning, stacklevel=2)
        return self.name

    def to_dict(self) -> game.GameToDict:
        if self.is_steam_game():
            return {"game_id": str(self.id)}

        if self.name is None or self.id is None:
            raise TypeError("un-serializable game with no title and or id")
        return {"game_id": str(self.id), "game_extra_info": self.name}

    def is_steam_game(self) -> bool:
        """Whether the game could be a Steam game."""
        return self.id <= APP_ID_MAX

    @property
    def url(self) -> str:
        """What should be the game's url on steamcommunity if applicable."""
        return f"{URL.COMMUNITY}/app/{self.id}"


class Games(Game, Enum):
    """This is "enum" to trick type checkers into allowing Literal[TF2] to be valid for overloads in extensions."""

    __slots__ = ("_name",)

    def __new__(cls, name: str, *args: Any, value: tuple[str, int, int] | tuple[()] = ()) -> Games:
        self = object.__new__(cls)
        set_attribute = object.__setattr__

        if args:  # being called when docs are building
            name = ""
            value = (name, args[0], args[1])

        assert value
        set_attribute(self, "_name", name)
        set_attribute(self, "name", value[0])
        set_attribute(self, "id", value[1])
        set_attribute(self, "context_id", value[2])
        return self

    if DOCS_BUILDING:

        def __init__(self, *args: Any) -> None:
            ...

    def __repr__(self) -> str:
        return self._name

    @property
    def value(self) -> int:
        return self.id

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


def CUSTOM_GAME(name: str | None = None, title: str | None = None) -> Game:
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


class FriendThoughts(NamedTuple):
    recommended: list[Friend]
    not_recommended: list[Friend]


class StatefulGame(Game):
    """Games that have state."""

    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, **kwargs: Any):
        super().__init__(**kwargs)
        self._state = state

    def __repr__(self) -> str:
        attrs = ("name", "id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

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
        ValueError
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

    async def friends_who_own(self) -> list[Friend]:
        """Fetch the users in your friend list who own this game."""
        id64s = await self._state.fetch_friends_who_own(self.id)
        return [self._state.get_friend(id64) for id64 in id64s]

    async def review(
        self,
        content: str,
        *,
        recommend: bool,
        public: bool = True,
        commentable: bool = True,
        received_compensation: bool = False,
        language: Language | None = None,
    ) -> Review:
        """Review a game.

        Parameters
        ----------
        content
            The content of the review.
        recommend
            Whether you recommended the game.
        public
            Whether the review should be public.
        commentable
            Whether the review should allow comments.
        received_compensation
            Whether you received compensation for this review.
        language
            The language the review is in.
        """
        language = language or self._state.http.language
        await self._state.http.post_review(
            self.id, content, recommend, public, commentable, received_compensation, language.api_name
        )
        return await self._state.user.fetch_review(self)  # TODO this sucks can we actually get the id ourselves?

    def reviews(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> GameReviewsIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`steam.Game`'s
        :class:`steam.Review`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for review in game.reviews(limit=10):
                print("Reviewer:", review.author)
                print("Said:", review.content)

        Flattening into a list:

        .. code-block:: python3

            reviews = await game.reviews(limit=50).flatten()
            # reviews is now a list of Review

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of reviews to search through. Default is ``100``. Setting this to ``None`` will fetch all
            the game's reviews, but this will be a very slow operation.
        before
            A time to search for reviews before.
        after
            A time to search for reviews after.

        Yields
        ------
        :class:`~steam.Review`
        """
        return GameReviewsIterator(self._state, self, limit, before, after)

    async def friend_thoughts(self) -> FriendThoughts:
        """Fetch the client user's friends who recommended and didn't recommend this game in a review.

        .. source:: FriendThoughts
        """
        proto = await self._state.fetch_friend_thoughts(self.id)
        return FriendThoughts(
            [self._state.get_friend(utils.make_id64(id)) for id in proto.accountids_recommended],
            [self._state.get_friend(utils.make_id64(id)) for id in proto.accountids_not_recommended],
        )

    # async def fetch(self) -> Self & FetchedGame:  # TODO update signature to this when types.Intersection is done
    #     fetched = await self._state.client.fetch_game(self)
    #     return utils.update_class(fetched, copy.copy(self))

    async def fetch(self, *, language: Language | None = None) -> FetchedGame:
        """Shorthand for:

        .. code-block:: python3

            game = await client.fetch_game(game)
        """
        game = await self._state.client.fetch_game(self, language=language)
        if game is None:
            raise ValueError("Fetched game was not valid.")
        return game

    async def depots(self) -> Sequence[Depot | HeadlessDepot]:
        info = await self.info()
        return await info.depots()

    async def fetch_manifest(
        self, *, id: int, depot_id: int, branch: str = "public", password_hash: str = ""
    ) -> Manifest:
        """Fetch a CDN manifest for a game.

        Parameters
        ----------
        id
            The ID of the manifest to fetch.
        depot_id
            The ID of the manifest's associated depot.
        """
        return await self._state.fetch_manifest(
            self.id, id, depot_id, name=None, branch=branch, password_hash=password_hash
        )

    def manifests(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
        branch: str = "public",
        password: str | None = None,
        password_hash: str = "",
    ) -> ManifestIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`steam.Game`'s
        :class:`steam.Manifest`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for manifest in game.manifests(limit=10):
                print("Manifest:", manifest.name)
                print(f"Contains {len(manifest.paths)} manifests")

        Flattening into a list:

        .. code-block:: python3

            manifests = await game.manifests(limit=50).flatten()
            # manifests is now a list of Manifest

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of :class:`.Manifests` to return.
        before
            The time to get manifests before.
        after
            The time to get manifests after.
        branch
            The name of the branch to fetch manifests from.
        password
            The password for the branch, if any.
        password_hash
            The hashed password for a manifest.

        Yields
        ------
        :class:`Manifest`
        """
        return ManifestIterator(
            state=self._state,
            limit=limit,
            before=before,
            after=after,
            game=self,
            branch=branch,
            password=password,
            password_hash=password_hash,
        )

    def published_files(
        self,
        *,
        type: PublishedFileQueryFileType = PublishedFileQueryFileType.Items,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> GamePublishedFilesIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a game's :class:`steam.PublishedFile`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for published_file in game.published_files(limit=10):
                print("Published file:", published_file.name)
                print("Published at:", published_file.created_at)
                print("Published by:", published_file.author)

        Flattening into a list:

        .. code-block:: python3

            published_files = await game.published_files(limit=50).flatten()
            # published_files is now a list of PublishedFile

        All parameters are optional.

        Parameters
        ----------
        type
            The type of published files to fetch.
        revision
            The desired revision of the published files to fetch.
        language
            The language to fetch the published files in. If ``None`` the current language is used.
        limit
            The maximum number of published files to search through. Default is ``100``. Setting this to ``None`` will
            fetch all the game's published files, but this will be a very slow operation.
        before
            A time to search for published files before.
        after
            A time to search for published files after.

        Yields
        ------
        :class:`~steam.PublishedFile`
        """
        return GamePublishedFilesIterator(self._state, self, type, revision, language, limit, before, after)

    async def info(self) -> GameInfo:
        """Shorthand for:

        .. code-block:: python3

            (info,) = await client.fetch_product_info(games=[game])
        """
        (info,), _ = await self._state.fetch_product_info((self.id,))
        return info

    async def dlc(self, *, language: Language | None = None) -> list[DLC]:
        """Fetch the game's DLC.

        Parameters
        ----------
        language
            The language to fetch the DLC in. If ``None``, the current language will be used.
        """
        data = await self._state.http.get_game_dlc(self.id, language)
        self.name = data["name"]
        return [DLC(self._state, dlc) for dlc in data["dlc"]]

    async def packages(self, *, language: Language | None = None) -> list[FetchedGamePackage]:
        """Fetch the game's packages.

        Parameters
        ----------
        language
            The language to fetch the packages in. If ``None``, the current language will be used.
        """
        fetched = await self.fetch(language=language)
        return fetched._packages

    async def add_free_licenses(self) -> list[License]:
        """Request the free licenses for this game.

        Raises
        ------
        ValueError
            No licenses were granted.
        """
        _, licenses = await self._state.request_free_license(self.id)
        return licenses


@dataclass
class PartialGamePriceOverview:
    currency: str
    initial: int
    final: int
    discount_percent: int


class DLC(StatefulGame):
    """Represents DLC (downloadable content) for a game.

    Attributes
    ----------
    created_at
        The time the DLC was released at.
    logo_url
        The logo url of the DLC.
    price_overview
        A price overview for the DLC.
    """

    name: str

    __slots__ = (
        "created_at",
        "logo_url",
        "price_overview",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
    )

    def __init__(self, state: ConnectionState, data: game.DLC):
        super().__init__(state, id=data["id"], name=data["name"])
        self.created_at = DateTime.from_timestamp(int(data["release_date"]["steam"]))
        self.logo_url: str = data["header_image"]
        self.price_overview = PartialGamePriceOverview(**data["price_overview"])

        platforms = data["platforms"]
        self._on_windows: bool = platforms["windows"]
        self._on_mac_os: bool = platforms["mac"]
        self._on_linux: bool = platforms["linux"]

    def is_free(self) -> bool:
        """Whether the game is free to download."""
        return not self.price_overview.final

    def is_on_windows(self) -> bool:
        """Whether the game is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the game is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the game is playable on Linux."""
        return self._on_linux


class UserGame(StatefulGame):
    """Represents a Steam game fetched by :meth:`steam.User.games`

    Attributes
    ----------
    playtime_forever
        The total time the game has been played for.
    icon_url
        The icon url of the game.
    playtime_two_weeks
        The amount of time the user has played the game in the last two weeks.
    playtime_windows
        The total amount of time the user has played the game on Windows.
    playtime_mac_os
        The total amount of time the user has played the game on macOS.
    playtime_linux
        The total amount of time the user has played the game on Linux.
    last_played_at
        The time the user last played this game at.
    """

    __slots__ = (
        "playtime_forever",
        "playtime_two_weeks",
        "playtime_windows",
        "playtime_mac_os",
        "playtime_linux",
        "icon_url",
        "last_played_at",
        "_stats_visible",
    )

    name: str

    def __init__(self, state: ConnectionState, proto: player.GetOwnedGamesResponseGame):
        super().__init__(state=state, id=proto.appid, name=proto.name)
        self.playtime_forever: timedelta = timedelta(minutes=proto.playtime_forever)
        self.playtime_two_weeks: timedelta = timedelta(minutes=proto.playtime_2_weeks)
        self.playtime_windows: timedelta = timedelta(minutes=proto.playtime_windows_forever)
        self.playtime_mac_os: timedelta = timedelta(minutes=proto.playtime_mac_forever)
        self.playtime_linux: timedelta = timedelta(minutes=proto.playtime_linux_forever)
        self.icon_url = (
            f"https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{self.id}/"
            f"{proto.img_icon_url}.jpg"
        )
        self.last_played_at = DateTime.from_timestamp(proto.rtime_last_played)

        self._stats_visible = proto.has_community_visible_stats

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
        The time that the game was added to their wishlist.
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

    def __init__(self, state: ConnectionState, id: int | str, data: game.WishlistGame):
        super().__init__(state, id=id, name=data["name"])
        self.logo_url = data["capsule"]
        self.score = data["review_score"]
        self.total_reviews = int(data["reviews_total"].replace(",", ""))
        self.review_status = ReviewType[data["review_desc"].replace(" ", "")]
        self.created_at = DateTime.from_timestamp(int(data["release_date"]))
        self.type: str = data["type"]
        self.screenshots = [
            f"https://cdn.cloudflare.steamstatic.com/steam/apps/{self.id}/{screenshot_url}"
            for screenshot_url in data["screenshots"]
        ]
        self.added_at = DateTime.from_timestamp(data["added"])
        self.background_url = data["background"]
        self.tags = data["tags"]
        self.rank = data["rank"]
        self.priority = int(data["priority"])

        self._free = data["is_free_game"]
        self._on_windows = bool(data.get("win", False))
        self._on_mac_os = bool(data.get("mac", False))
        self._on_linux = bool(data.get("linux", False))

    def is_free(self) -> bool:
        """Whether the game is free to download."""
        return self._free

    def is_on_windows(self) -> bool:
        """Whether the game is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the game is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the game is playable on Linux."""
        return self._on_linux


class Movie:
    __slots__ = ("name", "id", "url", "created_at")

    def __init__(self, movie: dict[str, Any]):
        self.name: str = movie["name"]
        self.id: int = movie["id"]
        self.url: str = movie["mp4"]["max"]
        match = re.search(r"t=(\d+)", self.url)
        self.created_at = DateTime.from_timestamp(int(match[1])) if match else None

    def __repr__(self) -> str:
        attrs = ("name", "id", "url", "created_at")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Movie {' '.join(resolved)}>"


@dataclass
class GamePriceOverview(PartialGamePriceOverview):
    initial_formatted: str
    final_formatted: str


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
    partial_dlc
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
    price_overview
        The price overview of the game.
    """

    __slots__ = (
        "logo_url",
        "background_url",
        "created_at",
        "type",
        "partial_dlc",
        "_packages",
        "website_url",
        "developers",
        "publishers",
        "description",
        "full_description",
        "movies",
        "price_overview",
        "_free",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
    )

    name: str

    def __init__(self, state: ConnectionState, data: game.FetchedGame):
        super().__init__(state, id=data["steam_appid"], name=data["name"])
        self.logo_url = data["header_image"]
        self.background_url = data["background"]
        self.created_at = (
            DateTime.parse_steam_date(data["release_date"]["date"], full_month=False)
            if data["release_date"]["date"]
            else None
        )
        self.type = AppFlag.from_str(data["type"])
        self.price_overview = GamePriceOverview(**data["price_overview"])

        self.partial_dlc = [StatefulGame(state, id=dlc_id) for dlc_id in data.get("dlc", [])]

        from .package import FetchedGamePackage

        self._packages = [
            FetchedGamePackage(state, package)
            for package_group in data["package_groups"]
            for package in package_group["subs"]
        ]

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

    async def packages(self, *, languages: Language | None = None) -> list[FetchedGamePackage]:
        return self._packages

    def is_free(self) -> bool:
        """Whether the game is free to download."""
        return self._free

    def is_on_windows(self) -> bool:
        """Whether the game is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the game is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the game is playable on Linux."""
        return self._on_linux
