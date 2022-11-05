"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, TypeVar, overload

from . import utils
from ._const import DOCS_BUILDING, MISSING, STATE, UNIX_EPOCH, URL
from .enums import AppFlag, Enum, Language, PublishedFileQueryFileType, PublishedFileRevision, ReviewType
from .id import ID, id64_from_url
from .protobufs import client_server, player
from .types.id import AppID, ContextID, Intable
from .utils import DateTime

if TYPE_CHECKING:
    from .clan import Clan
    from .friend import Friend
    from .manifest import AppInfo, Depot, HeadlessDepot, Manifest
    from .package import FetchedAppPackage, License
    from .published_file import PublishedFile
    from .review import Review
    from .state import ConnectionState
    from .types import app

__all__ = (
    "App",
    "TF2",
    "LFD2",
    "DOTA2",
    "CSGO",
    "STEAM",
    "CUSTOM_APP",
    "DLC",
    "UserApp",
    "WishlistApp",
    "FetchedApp",
)

T = TypeVar("T")
APP_ID_MAX: Final = AppID(1 << 32 - 1)


class App:
    """Represents a Steam app.

    Attributes
    ----------
    name
        The app's name.
    id
        The app's app ID.
    context_id
        The context id of the app normally ``2``.
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
        context_id: int | None = None,
    ):
        if name is None and id is None:
            raise TypeError("__init__() missing a required keyword argument: 'id' or 'name'")

        if id is None:
            app = utils.get(Apps, name=name)
            if app is None:
                raise ValueError(f"Cannot find a matching app for {name!r}")
            id = app.id
        else:
            try:
                id = int(id)
            except (ValueError, TypeError):
                raise ValueError("id expected to support int()") from None

            app = utils.get(Apps, id=id)
            if app is not None:
                name = app.name

        if id < 0:
            raise ValueError("id cannot be negative")

        if name == "Steam" and context_id is None:
            context_id = 6

        self.id: AppID = AppID(id)
        self.name: str | None = name
        self.context_id: ContextID = ContextID(2 if context_id is None else context_id)

    def __str__(self) -> str:
        return self.name or ""

    def __repr__(self) -> str:
        attrs = ("name", "id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"{self.__class__.__name__}({', '.join(resolved)})"

    def __eq__(self, other: Any) -> bool:
        return self.id == other.id if isinstance(other, App) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

    def to_proto(self) -> client_server.CMsgClientGamesPlayedGamePlayed:
        if self.is_valid():
            return client_server.CMsgClientGamesPlayedGamePlayed(game_id=self.id)

        if self.name is None or self.id is None:
            raise TypeError("un-serializable app with no title and or id")
        return client_server.CMsgClientGamesPlayedGamePlayed(game_id=self.id, game_extra_info=self.name)

    def is_valid(self) -> bool:
        """Whether the app could be a Steam app."""
        return self.id <= APP_ID_MAX

    @property
    def url(self) -> str:
        """What should be the app's url on steamcommunity if applicable."""
        return f"{URL.COMMUNITY}/app/{self.id}"


def CUSTOM_APP(
    name: str,
) -> App:  # TODO if actually optimising make this return a different class cause it's a u64 cause haha steam
    """Create a custom app instance for :meth:`~steam.Client.change_presence`.
    The :attr:`App.id` will be set to ``15190414816125648896`` and the :attr:`App.context_id` to ``None``.

    Example:

    .. code-block:: python3

        await client.change_presence(app=steam.CUSTOM_APP("my cool game"))

    Parameters
    ----------
    name
        The name of the app to set your playing status to.
    """
    return App(name=name, id=15190414816125648896, context_id=None)


import hashlib
from contextlib import asynccontextmanager
from datetime import timezone
from ipaddress import IPv4Address
from zlib import crc32


class Ignore:
    async def changes_since(self, change_number: int) -> tuple[list[AppInfo], list[PackageInfo]]:
        ...

    async def fetch_encrypted_ticket(self, key: bytes, *, user_data: bytes = b"") -> GameTicket:
        encrypted_ticket = await self._state.fetch_encrypted_app_ticket(self.id, user_data)
        decrypted = utils.StructIO(utils.symmetric_decrypt(encrypted_ticket.encrypted_ticket, key))
        if crc32(decrypted.buffer, encrypted_ticket.crc_encryptedticket):
            raise ValueError

        user_data = decrypted.buffer[: encrypted_ticket.cb_encrypteduserdata]
        decrypted.seek(encrypted_ticket.cb_encrypteduserdata)
        ticket_length = decrypted.read_u32()
        ticket = GameTicket(
            decrypted.buffer[
                encrypted_ticket.encrypted_app_ticket.cb_encrypteduserdata
                + ticket_length : encrypted_ticket.encrypted_app_ticket.cb_encrypteduserdata
            ],
            encrypted=True,
        )
        remainder = decrypted.buffer[encrypted_ticket.cb_encrypteduserdata + ticket_length :]
        if len(remainder) >= 8 + 20:
            to_hash = decrypted.buffer[: encrypted_ticket.cb_encrypteduserdata + ticket_length]
            salt = remainder[:8]
            hash = remainder[8:28]
            remainder = remainder[28:]

            hasher = hashlib.sha1(to_hash + salt)
            digested = hasher.digest()
            assert digested == hash, f"Oh no {digested} {hash}"

        return ticket

    @asynccontextmanager
    async def create_auth_ticket(self) -> AsyncGenerator[GameTicket, None]:
        """Create an authentication ticket for this game.

        Examples
        --------

        .. code-block:: python3

            async with game.create_auth_ticket() as ticket:
                ...  # send the ticket to a user or server
        """
        # for the ticket to be valid we have to be playing the game
        to_dict = self.to_dict()
        state = self._state
        games = state._games.copy()  # keep a copy of the old list
        if to_dict not in games:
            await state.ws.change_presence(games=[*games, to_dict])

        ticket = await state.create_ticket(self.id)
        try:
            yield GameTicket(ticket, encrypted=False)
        finally:
            await state.cancel_ticket(self.id)
            if to_dict not in games:
                await state.ws.change_presence(games=games)

    async def fetch_ownership_ticket(self) -> Ticket:
        await self._state.fetch_ownership_ticket(self.id)


class FriendThoughts(NamedTuple):
    recommended: list[Friend]
    not_recommended: list[Friend]


class PartialApp(App):
    """Apps that have state."""

    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, **kwargs: Any):
        super().__init__(**kwargs)
        self._state = state

    def __repr__(self) -> str:
        attrs = ("name", "id", "context_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    async def clan(self) -> Clan:
        """Fetch this app's clan.

        This can be useful to get an App's updates.

        .. code-block:: python3

            clan = await app.clan()
            async for update in clan.announcements():
                if update.type in (steam.EventType.MajorUpdate, steam.EventType.SmallUpdate):
                    ...  # do something with the update

        Raises
        ------
        ValueError
            This app has no associated clan.
        """

        id64 = await id64_from_url(self.url, self._state.http._session)
        if id64 is None:
            raise ValueError("App has no associated clan")
        clan = await self._state.fetch_clan(id64)
        if clan is None:
            raise ValueError("App has no associated clan")
        return clan

    async def player_count(self) -> int:
        """The apps current player count."""
        return await self._state.fetch_app_player_count(self.id)

    async def friends_who_own(self) -> list[Friend]:
        """Fetch the users in your friend list who own this app."""
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
        """Review an app.

        Parameters
        ----------
        content
            The content of the review.
        recommend
            Whether you recommended the app.
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

    async def reviews(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[Review, None]:
        """An :term:`async iterator` for accessing a :class:`steam.App`'s
        :class:`steam.Review`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for review in app.reviews(limit=10):
                print("Reviewer:", review.author)
                print("Said:", review.content)

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of reviews to search through. Default is ``100``. Setting this to ``None`` will fetch all
            the app's reviews, but this will be a very slow operation.
        before
            A time to search for reviews before.
        after
            A time to search for reviews after.

        Yields
        ------
        :class:`~steam.Review`
        """
        from .review import Review, ReviewApp

        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        cursor = "*"
        app = self

        yielded = 0

        while True:
            data = await self._state.http.get_reviews(self.id, "all", "all", "all", cursor)
            if cursor == "*":
                app = ReviewApp(self._state, self.id, data["query_summary"]["review_score"])
            assert isinstance(app, ReviewApp)
            cursor = data["cursor"]
            reviews = data["reviews"]

            for review, user in zip(
                reviews,
                await self._state.fetch_users(int(review["author"]["steamid"]) for review in reviews),
            ):
                if user is None:
                    continue
                review = Review._from_data(self._state, review, app, user)
                if not after < review.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return

                yield review
                yielded += 1

    async def friend_thoughts(self) -> FriendThoughts:
        """Fetch the client user's friends who recommended and didn't recommend this app in a review.

        .. source:: FriendThoughts
        """
        proto = await self._state.fetch_friend_thoughts(self.id)
        return FriendThoughts(
            [self._state.get_friend(utils.parse_id64(id)) for id in proto.accountids_recommended],
            [self._state.get_friend(utils.parse_id64(id)) for id in proto.accountids_not_recommended],
        )

    # async def fetch(self) -> Self & FetchedApp:  # TODO update signature to this when types.Intersection is done
    #     fetched = await self._state.client.fetch_app(self)
    #     return utils.update_class(fetched, copy.copy(self))

    async def fetch(self, *, language: Language | None = None) -> FetchedApp:
        """Shorthand for:

        .. code-block:: python3

            app = await client.fetch_app(app)
        """
        app = await self._state.client.fetch_app(self, language=language)
        if app is None:
            raise ValueError("Fetched app was not valid.")
        return app

    async def depots(self) -> Sequence[Depot | HeadlessDepot]:
        info = await self.info()
        return await info.depots()

    async def fetch_manifest(
        self, *, id: int, depot_id: int, branch: str = "public", password_hash: str = ""
    ) -> Manifest:
        """Fetch a CDN manifest for an app.

        Parameters
        ----------
        id
            The ID of the manifest to fetch.
        depot_id
            The ID of the manifest's associated depot.
        branch
            The name of the branch the manifest is from.
        password_hash
            The hashed password for the manifest.
        """
        return await self._state.fetch_manifest(
            self.id, id, depot_id, name=None, branch=branch, password_hash=password_hash
        )

    async def manifests(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
        branch: str = "public",
        password: str | None = None,
        password_hash: str = "",
    ) -> AsyncGenerator[Manifest, None]:
        """An :term:`async iterator` for accessing a :class:`steam.App`'s
        :class:`steam.Manifest`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for manifest in app.manifests(limit=10):
                print("Manifest:", manifest.name)
                print(f"Contains {len(manifest.paths)} manifests")

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
        manifest_coros = await self._state.fetch_manifests(self.id, branch, password, limit, password_hash)
        for chunk in utils.as_chunks(manifest_coros, 100):
            for manifest in await asyncio.gather(*chunk):
                if after < manifest.created_at < before:
                    yield manifest

    async def published_files(
        self,
        *,
        type: PublishedFileQueryFileType = PublishedFileQueryFileType.Items,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[PublishedFile, None]:
        """An :term:`async iterator` for accessing an app's :class:`steam.PublishedFile`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for published_file in app.published_files(limit=10):
                print("Published file:", published_file.name)
                print("Published at:", published_file.created_at)
                print("Published by:", published_file.author)

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
            fetch all the app's published files, but this will be a very slow operation.
        before
            A time to search for published files before.
        after
            A time to search for published files after.

        Yields
        ------
        :class:`~steam.PublishedFile`
        """
        from .published_file import PublishedFile

        before = before or DateTime.now()
        after = after or UNIX_EPOCH
        remaining = None
        cursor = "*"
        yielded = 0

        while remaining is None or remaining > 0:
            protos = await self._state.fetch_app_published_files(self.id, type, revision, language, limit, cursor)
            if remaining is None:
                remaining = protos.total
            remaining -= len(protos.publishedfiledetails)
            cursor = protos.next_cursor

            files: list[PublishedFile] = []
            for file in protos.publishedfiledetails:
                file = PublishedFile(self._state, file, ID(file.creator))
                if not after < file.created_at < before:
                    remaining = 0
                    break
                files.append(file)

            for file, author in zip(files, await self._state._maybe_users(file.author.id64 for file in files)):
                if limit is not None and yielded >= limit:
                    return
                file.author = author
                yield file
                yielded += 1

    async def info(self) -> AppInfo:
        """Shorthand for:

        .. code-block:: python3

            (info,) = await client.fetch_product_info(apps=[app])
        """
        (info,), _ = await self._state.fetch_product_info((self.id,))
        return info

    async def dlc(self, *, language: Language | None = None) -> list[DLC]:
        """Fetch the app's DLC.

        Parameters
        ----------
        language
            The language to fetch the DLC in. If ``None``, the current language will be used.
        """
        data = await self._state.http.get_app_dlc(self.id, language)
        self.name = data["name"]
        return [DLC(self._state, dlc) for dlc in data["dlc"]]

    async def packages(self, *, language: Language | None = None) -> list[FetchedAppPackage]:
        """Fetch the app's packages.

        Parameters
        ----------
        language
            The language to fetch the packages in. If ``None``, the current language will be used.
        """
        fetched = await self.fetch(language=language)
        return fetched._packages

    async def add_free_licenses(self) -> list[License]:
        """Request the free licenses for this app.

        Raises
        ------
        ValueError
            No licenses were granted.
        """
        _, licenses = await self._state.request_free_license(self.id)
        return licenses


class Apps(PartialApp, Enum):
    """This is "enum" to trick type checkers into allowing Literal[TF2] to be valid for overloads in extensions."""

    __slots__ = ("_name",)

    def __new__(cls, name: str, *args: Any, value: tuple[str, int, int] | tuple[()] = ()) -> Apps:
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

    @property
    def _state(self) -> ConnectionState:
        state = STATE.get(MISSING)
        if state is MISSING:
            raise ValueError("Cannot access the state of constant apps outside of a client.")
        return state


TF2 = Apps.TF2  #: The Team Fortress 2 app.
DOTA2 = Apps.DOTA2  #: The DOTA 2 app.
CSGO = Apps.CSGO  #: The Counter Strike Global-Offensive app.
LFD2 = Apps.LFD2  #: The Left 4 Dead 2 app.
STEAM = Apps.STEAM  #: The Steam app with context ID 6 (gifts).


@dataclass(slots=True)
class PartialAppPriceOverview:
    currency: str
    initial: int
    final: int
    discount_percent: int


class DLC(PartialApp):
    """Represents DLC (downloadable content) for an app.

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

    def __init__(self, state: ConnectionState, data: app.DLC):
        super().__init__(state, id=data["id"], name=data["name"])
        self.created_at = DateTime.from_timestamp(int(data["release_date"]["steam"]))
        self.logo_url: str = data["header_image"]
        self.price_overview = PartialAppPriceOverview(**data["price_overview"])

        platforms = data["platforms"]
        self._on_windows: bool = platforms["windows"]
        self._on_mac_os: bool = platforms["mac"]
        self._on_linux: bool = platforms["linux"]

    def is_free(self) -> bool:
        """Whether the app is free to download."""
        return not self.price_overview.final

    def is_on_windows(self) -> bool:
        """Whether the app is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the app is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the app is playable on Linux."""
        return self._on_linux


class UserApp(PartialApp):
    """Represents a Steam app fetched by :meth:`steam.User.apps`

    Attributes
    ----------
    playtime_forever
        The total time the app has been played for.
    icon_url
        The icon url of the app.
    playtime_two_weeks
        The amount of time the user has played the app in the last two weeks.
    playtime_windows
        The total amount of time the user has played the app on Windows.
    playtime_mac_os
        The total amount of time the user has played the app on macOS.
    playtime_linux
        The total amount of time the user has played the app on Linux.
    last_played_at
        The time the user last played this app at.
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
        """Whether the app has publicly visible stats."""
        return self._stats_visible


class WishlistApp(PartialApp):
    """Represents a Steam app fetched by :meth:`steam.User.wishlist`\\.

    Attributes
    ----------
    priority
        The priority of the app in the wishlist.
    added_at
        The time that the app was added to their wishlist.
    created_at
        The time the app was uploaded at.
    background_url
        The background URL of the app.
    rank
        The global rank of the app by popularity.
    review_status
        The review status of the app.
    score
        The score of the app out of ten.
    screenshots
        The screenshots of the app.
    tags
        The tags of the app.
    total_reviews
        The total number reviews for the app.
    type
        The type of the app.
    logo_url
        The logo url of the app.
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

    def __init__(self, state: ConnectionState, id: int | str, data: app.WishlistApp):
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
        """Whether the app is free to download."""
        return self._free

    def is_on_windows(self) -> bool:
        """Whether the app is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the app is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the app is playable on Linux."""
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


@dataclass(slots=True)
class AppPriceOverview(PartialAppPriceOverview):
    initial_formatted: str
    final_formatted: str


class FetchedApp(PartialApp):
    """Represents a Steam app fetched by :meth:`steam.Client.fetch_app`\\.

    Attributes
    ----------
    created_at
        The time the app was uploaded at.
    background_url
        The background URL of the app.
    type
        The type of the app.
    logo_url
        The logo URL of the app.
    partial_dlc
        The app's downloadable content.
    website_url
        The website URL of the app.
    developers
        The developers of the app.
    publishers
        The publishers of the app.
    description
        The short description of the app.
    full_description
        The full description of the app.
    movies
        A list of the app's movies, each of which has ``name``\\, ``id``\\, ``url`` and optional
        ``created_at`` attributes.
    price_overview
        The price overview of the app.
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
        "_language",
    )

    name: str

    def __init__(self, state: ConnectionState, data: app.FetchedApp, language: Language):
        super().__init__(state, id=data["steam_appid"], name=data["name"])
        self.logo_url = data["header_image"]
        self.background_url = data["background"]
        self.created_at = (
            DateTime.parse_steam_date(data["release_date"]["date"], full_month=False)
            if data["release_date"]["date"]
            else None
        )
        self.type = AppFlag.from_str(data["type"])
        self.price_overview = AppPriceOverview(**data["price_overview"])

        self.partial_dlc = [PartialApp(state, id=dlc_id) for dlc_id in data.get("dlc", [])]

        from .package import FetchedAppPackage

        self._packages = [
            FetchedAppPackage(state, package)
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

        self._language = language

    async def packages(self, *, language: Language | None = None) -> list[FetchedAppPackage]:
        if language is not self._language:
            return await super().packages(language=language)
        return self._packages

    def is_free(self) -> bool:
        """Whether the app is free to download."""
        return self._free

    def is_on_windows(self) -> bool:
        """Whether the app is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the app is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the app is playable on Linux."""
        return self._on_linux


@dataclass(slots=True)
class UserInventoryInfoContext:
    """Represents a context ID type."""

    id: ContextID
    """The ID of the context ID type."""
    name: str
    """The name of the context ID type."""
    count: int
    """The number of items in the context ID type."""


class UserInventoryInfoApp(PartialApp):
    name: str
    __slots__ = ("icon_url", "inventory_logo_url")

    def __init__(self, state: ConnectionState, id: int, name: str, icon_url: str, inventory_logo_url: str):
        super().__init__(state, id=id, name=name)
        self.icon_url = icon_url
        self.inventory_logo_url = inventory_logo_url
