"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any, Final, Generic, NamedTuple, cast
from zlib import crc32

from typing_extensions import Self, TypeVar

from . import utils
from ._const import (
    JSON_LOADS,
    STATE,
    STEAM_BADGES,
    UNIX_EPOCH,
    URL,
    WRITE_U32,
    ReadOnly,
    impl_eq_via_id,
)
from .achievement import AppAchievement, AppStats
from .badge import AppBadge
from .enums import *
from .id import _ID64_TO_ID32, id64_from_url
from .models import CDNAsset, DescriptionMixin, _IOMixin
from .protobufs import client_server, player
from .tag import Category, Tag
from .types.id import *
from .utils import DateTime

if TYPE_CHECKING:
    from .abc import PartialUser
    from .clan import Clan
    from .friend import Friend
    from .leaderboard import Leaderboard
    from .manifest import AppInfo, Depot, HeadlessDepot, Manifest
    from .package import FetchedAppPackage, License, PartialPackage
    from .protobufs import econ
    from .protobufs.encrypted_app_ticket import EncryptedAppTicket as EncryptedAppTicketProto
    from .published_file import PublishedFile
    from .review import Review
    from .state import ConnectionState
    from .store import AppStoreItem
    from .types import app
    from .types.user import Author

__all__ = (
    "App",
    "PartialApp",
    "TF2",
    "LFD2",
    "DOTA2",
    "CSGO",
    "STEAM",
    "CUSTOM_APP",
    "OwnershipTicket",
    "AuthenticationTicketVerificationResult",
    "AuthenticationTicket",
    "EncryptedTicket",
    "FriendThoughts",
    "AppShopItem",
    "AppShopItemTag",
    "AppShopItems",
    "CommunityItem",
    "RewardItem",
    "DLC",
    "UserApp",
    "UserRecentlyPlayedApp",
    "WishlistApp",
    "FetchedApp",
    "UserInventoryInfoApp",
    "UserInventoryInfoContext",
)

T = TypeVar("T")
APP_ID_MAX: Final = AppID((1 << 32) - 1)
NameT = TypeVar("NameT", bound=str | None, default=str | None, covariant=True)


@impl_eq_via_id
class App(Generic[NameT]):
    """Represents a Steam app."""

    __slots__ = (
        "id",
        "name",
    )

    def __init__(
        self,
        *,
        id: Intable,
        name: NameT = None,
    ):
        try:
            id = int(id)
        except (ValueError, TypeError):
            raise ValueError("id expected to support int()") from None

        if id < 0:
            raise ValueError("id cannot be negative")

        self.id: AppID = AppID(id)
        """The app's app ID."""
        self.name = name
        """The app's name."""

    def __str__(self) -> str:
        return self.name or f"App: {self.id}"

    def __repr__(self) -> str:
        attrs = ("name", "id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"{self.__class__.__name__}({', '.join(resolved)})"

    def to_proto(self) -> client_server.CMsgClientGamesPlayedGamePlayed:
        if self.is_valid():
            return client_server.CMsgClientGamesPlayedGamePlayed(game_id=self.id)

        if self.name is None:
            raise TypeError("un-serializable app with no name")
        return client_server.CMsgClientGamesPlayedGamePlayed(game_id=self.id, game_extra_info=self.name)

    def is_valid(self) -> bool:
        """Whether the app could be a Steam app."""
        return self.id <= APP_ID_MAX

    @property
    def url(self) -> str:
        """The app's URL on https://steamcommunity.com."""
        return f"{URL.COMMUNITY}/app/{self.id}"


def CUSTOM_APP(
    name: str,
) -> App[str]:
    """Create a custom app instance for :meth:`~steam.Client.change_presence`.
    The :attr:`App.id` will be set to ``15190414816125648896``.

    Example:

    .. code:: python

        await client.change_presence(app=steam.CUSTOM_APP("my cool game"))

    Parameters
    ----------
    name
        The name of the app to set your playing status to.
    """
    # if actually optimising make this return a different class cause it's a u64 cause haha steam
    return App(name=name, id=15190414816125648896)


class BaseOwnershipTicket:
    __slots__ = (
        "_state",
        "_ticket",
        "_start",
        "_end",
        "version",
        "user",
        "app",
        "external_ip",
        "internal_ip",
        "flags",
        "created_at",
        "_expires",
        "licenses",
        "dlc",
        "signature",
    )

    def __init__(self, state: ConnectionState, ticket: utils.StructIO) -> None:
        from .package import PartialPackage

        self._state = state
        self._ticket = ticket
        self._start = ticket.position
        self._end = ticket.read_u32()  # including itself, for some reason
        if self._start + self._end != len(ticket) and self._start + self._end + 128 != len(ticket):
            return None

        self.version = ticket.read_u32()
        """The version of the ticket."""
        self.user = state.get_partial_user(ticket.read_u64())
        """The user who owns the ticket."""
        self.app = PartialApp(state, id=ticket.read_u32())
        """The app the ticket is for."""
        self.external_ip = IPv4Address(ticket.read_u32())
        """The external IP address of the user."""
        self.internal_ip = IPv4Address(ticket.read_u32())
        """The internal IP address of the user."""
        self.flags = ticket.read_u32()
        """The flags of the ticket."""
        self.created_at = DateTime.from_timestamp(ticket.read_u32())
        """The time the ticket was created."""
        self._expires = DateTime.from_timestamp(ticket.read_u32())
        """The time the ticket expires."""
        self.licenses = [PartialPackage(state, id=ticket.read_u32()) for _ in range(ticket.read_u16())]
        """The licenses the user owns."""
        self.dlc = [
            OwnershipDLC(
                state,
                id=ticket.read_u32(),
                owned_packages=[PartialPackage(state, id=ticket.read_u32()) for _ in range(ticket.read_u16())],
            )
            for _ in range(ticket.read_u16())
        ]
        """The DLC the user owns."""

        ticket.read_u16()  # reserved
        signature = ticket.read(128)
        self.signature = signature if len(signature) == 128 else None
        """The signature of the ticket."""

    def __repr__(self) -> str:
        attrs = (
            "user",
            "app",
            "version",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"


class OwnershipTicket(BaseOwnershipTicket):
    """Represents an ownership ticket. This is used to verify ownership of an app."""

    __slots__ = ()

    def __bytes__(self) -> bytes:
        return self._ticket.buffer

    def is_signature_valid(self) -> bool:
        if self.signature is not None:
            return utils.verify_signature(
                self._ticket.getbuffer()[self._start : self._start + self._end],
                self.signature,
            )
        return False

    @property
    def expires(self) -> datetime:
        """The time at which the ticket expires."""
        return self._expires

    def is_expired(self) -> bool:
        """Whether the ticket has expired."""
        return self._expires < DateTime.now()

    def is_valid(self) -> bool:
        return not self.is_expired() and (not self.signature or self.is_signature_valid())


@dataclass(slots=True)
class AuthenticationTicketVerificationResult:
    """Represents the result of an authentication ticket verification.

    .. container:: operations

        .. describe:: bool(x)

            Checks if the result is :attr:`Result.OK`.
    """

    result: Result
    """The result of the verification."""
    user: PartialUser
    """The user who sent the ticket."""
    owner: PartialUser
    """The user who owns the ticket."""
    vac_banned: bool
    """Whether the user is VAC banned."""
    publisher_banned: bool
    """Whether the user is publisher banned."""

    def __bool__(self) -> bool:
        return self.result is Result.OK


class AuthenticationTicket(OwnershipTicket):
    """Represents an authentication ticket. This is used to verify ownership of an app and to connect to the game server."""

    __slots__ = (
        "auth_ticket",
        "gc_token",
        "gc_token_created_at",
        "client_ip",
        "client_connected_at",
        "client_connection_count",
    )

    def __init__(self, state: ConnectionState, ticket: utils.StructIO) -> None:
        self.auth_ticket = bytes(ticket.getbuffer()[ticket.position - 4 : ticket.position - 4 + 52])
        """The authentication ticket for the app. The first 52 bytes of the ticket."""
        # this is the part that's passed back to Steam for validation

        self.gc_token = ticket.read_u64()
        """The Game Connect token for the app."""
        ticket.position += 8
        self.gc_token_created_at = DateTime.from_timestamp(ticket.read_u32())
        """When the Game Connect token was created."""

        if ticket.read_u32() != 24:
            raise ValueError("Invalid session header")

        ticket.position += 8  # unknown 1 and unknown 2
        self.client_ip = IPv4Address(ticket.read_u32())
        """The IP address of the client."""
        ticket.position += 4  # filler
        self.client_connected_at = timedelta(milliseconds=ticket.read_u32())
        """The time the client has been connected to Steam"""
        self.client_connection_count = ticket.read_u32()
        """How many servers the client has connected to"""

        if ticket.read_u32() + ticket.position != len(ticket):
            raise ValueError("Invalid ownership section")
        super().__init__(state, ticket)

    def __bytes__(self, _header: bytearray = bytearray(WRITE_U32(20))) -> bytes:
        return bytes(_header + self._ticket.getbuffer())

    async def verify(self, *, publisher_api_key: str | None = None) -> AuthenticationTicketVerificationResult:
        """Verify the ticket with the web API.

        Parameters
        ----------
        publisher_api_key
            The publisher API key to use for verification. If not provided, will use the standard (rate limited) API.
        """
        data = await self._state.http.verify_app_ticket(self.app.id, self._ticket.buffer.hex(), publisher_api_key)
        return AuthenticationTicketVerificationResult(
            Result[data["result"]],
            *await self._state._maybe_users((ID64(int(data["steamid"])), ID64(int(data["ownersteamid"])))),
            vac_banned=data["vacbanned"],
            publisher_banned=data["publisherbanned"],
        )

    async def activate(self) -> None:
        """Activate the ticket."""
        await self._state.activate_auth_session_tickets(self)

    async def deactivate(self) -> None:
        """Deactivate the ticket. Ends our sessions with other users meaning we can't get events from them anymore."""
        await self._state.deactivate_auth_session_tickets(self)

    # def is_valid(self) -> bool:  # TODO is it worth having an opinion on this?
    #     return


class EncryptedTicket(BaseOwnershipTicket):
    """Represents an encrypted ticket."""

    def __init__(self, state: ConnectionState, ticket: EncryptedAppTicketProto, key: bytes) -> None:
        decrypted = utils.StructIO(utils.symmetric_decrypt(ticket.encrypted_ticket, key))
        if crc32(decrypted.getbuffer()) != ticket.crc_encryptedticket:
            raise ValueError("Invalid CRC")
        self.user_data = decrypted.read(ticket.cb_encrypteduserdata)
        """The user's given data for the ticket."""

        (length,) = decrypted.read_struct(">I")

        super().__init__(state, utils.StructIO(decrypted.read(length)))
        remaining = decrypted.read()
        if len(remaining) >= 8 + 20:
            to_hash = decrypted.buffer[: ticket.cb_encrypteduserdata + length]
            salt = remaining[:8]
            hash = remaining[8:28]

            if hashlib.sha1(to_hash + salt).digest() != hash:
                raise ValueError("Invalid hash")


async def parse_app_ticket(state: ConnectionState, ticket: utils.StructIO) -> OwnershipTicket | AuthenticationTicket:
    if ticket.read_u32() == 20:
        app_ticket = AuthenticationTicket(state, ticket)
    else:
        ticket.position -= 4
        app_ticket = OwnershipTicket(state, ticket)

    if not app_ticket.is_valid():
        raise ValueError("Invalid ticket")
    app_ticket.user = await state._maybe_user(app_ticket.user.id64)
    return app_ticket


class FriendThoughts(NamedTuple):
    recommended: list[Friend]
    not_recommended: list[Friend]


@dataclass(slots=True)
class AppShopItemTag:
    name: str
    display_name: str
    id: int


class AppShopItem(DescriptionMixin):
    """Represents an item that can be purchased from the shop."""

    __slots__ = (
        *DescriptionMixin.SLOTS,
        "_state",
        "class_id",
        "def_index",
        "class_",
        "prices",
        "original_prices",
        "updated_at",
        "store_tags",
        "_app_id",
    )

    def __init__(
        self,
        state: ConnectionState,
        data: app.AssetPricesAsset,
        description: econ.ItemDescription,
        tags: Sequence[AppShopItemTag],
    ):
        self._state = state
        self.class_id = ClassID(description.classid)
        self.def_index = int(data["name"])
        """The def index of the item in the app's schema"""
        self.class_ = data["class"]
        """Extra info about the item."""
        self.prices = cast(
            Mapping[Currency, int],
            {Currency.try_name(name): price for name, price in data["prices"].items()},
        )
        """The prices of the asset in the store."""
        self.original_prices = cast(
            Mapping[Currency, int] | None,
            {
                Currency.try_name(name): price
                for name, price in data["original_prices"].items()
                if data["prices"][name] < price
            }
            if "original_prices" in data
            else None,
        )
        """The original prices of any items if the price in ``prices`` is reduced."""
        try:
            self.updated_at = DateTime.strptime(
                data["date"], "%Y/%m/%d"
            )  # yes this could be just a date but maybe volvo will be nice one day
            """The time the price was last updated"""
        except ValueError:
            self.updated_at = None  # they like to sprinkle in a bit of 1960/00/00 for the funsies
        self.store_tags = [tag for tag in tags for tag_id in data.get("tag_ids", ()) if tag.id == tag_id]
        """The tags associated with the item."""

        super().__init__(state, description)

    def __repr__(self) -> str:
        attrs = ("name", "class_id", "def_index", "store_tags", "app")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"


@dataclass(slots=True)
class AppShopItems(Sequence[AppShopItem]):
    """Represents the items that can be purchased from the shop.

    .. container:: operations

        .. describe:: x == y

            Checks if two app shop items are equal.

        .. describe:: len(x)

            Returns the number of items in the shop.

        .. describe:: x[i]

            Returns the item at index ``i``.
    """

    items: Sequence[AppShopItem]
    """The items that can be purchased from the shop"""
    tags: Sequence[AppShopItemTag]
    """All the possible tags for ``items`` to have."""

    if not TYPE_CHECKING:

        def __len__(self):
            return len(self.items)

        def __getitem__(self, idx):
            return self.items[idx]


AppT = TypeVar("AppT", bound="PartialApp", covariant=True)


@dataclass(slots=True)
class CommunityItem(Generic[AppT]):
    """Represents a community item.

    .. container:: operations

        .. describe:: x == y

            Checks if two community items are equal.

        .. describe:: hash(x)

            Returns the community item's hash.
    """

    _state: ConnectionState = field(repr=False, compare=False)
    type: int
    """The type of the community item."""
    app: AppT
    """The app the community item is from."""
    name: str
    """The name of the community item."""
    title: str
    """The title of the community item."""
    description: str
    """The description of the community item."""
    image: CDNAsset | None
    """The image of the community item. Attempts to use the larger image if possible."""
    movie: CDNAsset | None
    """The movie of the community item. Uses the ``.mp4`` version."""
    data: Mapping[str, Any] | None
    """Data associated with the community item."""
    series: int
    """The series of the community item."""
    class_: CommunityItemClass
    """The class of the community item."""
    editor: Author | None
    """The last editor of the community item."""
    active: bool
    """Whether the community item is active."""
    image_composed: CDNAsset | None
    """The composed image of the community item."""
    image_composed_foil: CDNAsset | None
    """The composed foil image of the community item."""
    deleted: bool
    """Whether the community item is deleted."""
    edited_at: datetime | None
    """When the community item was last edited."""
    # broadcast_channel_id: int = betterproto.uint64_field(17)

    def __hash__(self) -> int:
        hashable_slots = set(self.__slots__) - {"data"}
        return hash(
            (*tuple(getattr(self, attr) for attr in hashable_slots), tuple(self.data.items()) if self.data else None)
        )

    @property
    def badges(self) -> Sequence[AppBadge[AppT]]:
        """The badges for the item."""
        if self.class_ is not CommunityItemClass.Badge:
            return []
        if not self.data:
            return []

        badges: list[AppBadge[AppT]] = []
        previous_name = ""
        for name, image in zip(self.data["level_names"].values(), self.data["level_images"].values()):
            if not name:
                name = previous_name
            badge = AppBadge(
                self._state,
                1,
                name,
                self.app,
                CDNAsset(self._state, f"{URL.CDN}/steamcommunity/public/images/items/{self.app.id}/{image}"),
            )
            previous_name = name
            badges.append(badge)
        return badges


@dataclass(slots=True, unsafe_hash=True)
class RewardItem(Generic[AppT]):
    """Represents a reward item in the Steam Points Shop."""

    type: int
    """The type of the reward item."""
    app: AppT
    """The app the reward item is from."""
    name: str
    """The name of the reward item."""
    title: str
    """The title of the reward item."""
    description: str
    """The description of the reward item."""
    display_description: str
    """The displayed description of the reward item."""
    image: CDNAsset | None
    """The image of the reward item. Attempts to use the larger image if possible."""
    movie: CDNAsset | None
    """The movie of the reward item. Uses the ``.mp4`` version."""
    animated: bool
    """Whether the reward item is animated."""
    badges: Sequence[AppBadge[AppT]]
    """The badges for the item."""
    def_index: int
    """The def index of the reward item."""
    quantity: int
    """The quantity of the reward item."""
    class_: CommunityItemClass
    """The class of the reward item."""
    item_type: int  # 6 is bundle, 1 is normal?
    """The type of the reward item."""
    point_cost: int
    """The cost of the reward item in Steam Points."""
    created_at: datetime
    """When the reward item was created."""
    updated_at: datetime
    """When the reward item was last updated."""
    available_at: datetime
    """When the reward item was made available."""
    availability_ends: datetime
    """When the reward item is no longer available."""
    active: bool
    """Whether the reward item is active."""
    profile_theme_id: str
    """The profile theme ID of the reward item."""
    usable_duration: timedelta
    """How long the reward item is usable for."""
    bundle_discount: int
    """The discount of the reward item if it is a bundle."""
    bundles: Sequence[Self] = field(init=False)
    """The bundles the reward contains."""


class PartialApp(App[NameT]):
    """Apps that have state."""

    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, *, id: Intable, name: NameT = None):
        super().__init__(id=id, name=name)
        self._state = state

    def __repr__(self) -> str:
        attrs = ("name", "id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    async def clan(self) -> Clan:
        """Fetch this app's clan.

        This can be useful to get an App's updates.

        .. code:: python

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
        return await self._state.fetch_clan(id64)

    async def player_count(self) -> int:
        """The apps current player count."""
        return await self._state.fetch_app_player_count(self.id)

    async def stats(self, *, language: Language | None = None) -> AppStats:
        """The stats for this app.

        Parameters
        ----------
        language
            The language to fetch the stats in. If ``None``, the current language will be used.

        See Also
        --------
        :meth:`achievements` if you want a faster way to fetch just achievements.
        """
        data = await self._state.http.get_app_stats(self.id, language)
        return AppStats(self._state, self, data)

    async def achievements(self, *, language: Language | None = None) -> list[AppAchievement]:
        """The achievements for this app.

        Parameters
        ----------
        language
            The language to fetch the achievements in. If ``None``, the current language will be used.
        """
        achievements = await self._state.fetch_app_achievements(self.id, language)
        return [
            AppAchievement(
                achievement.internal_name,
                self,
                achievement.localized_name,
                achievement.localized_desc,
                CDNAsset(
                    self._state,
                    f"{URL.CDN}/steamcommunity/public/images/apps/{self.id}/{achievement.icon}",
                ),
                CDNAsset(self._state, f"{URL.CDN}/steamcommunity/public/images/apps/{self.id}/{achievement.icon_gray}"),
                achievement.hidden,
                float(achievement.player_percent_unlocked),
            )
            for achievement in achievements
        ]

    async def leaderboards(self, *, language: Language | None = None) -> list[Leaderboard[Self, str]]:
        """The leaderboards for this app.

        Parameters
        ----------
        language
            The language to fetch the leaderboards in. If ``None``, the current language will be used.
        """
        from .leaderboard import Leaderboard

        leaderboards = await self._state.http.get_app_leaderboards(self.id, language)
        return [
            Leaderboard(
                self._state,
                id=LeaderboardID(leaderboard["id"]),
                app=self,
                name=leaderboard["name"],
                display_name=leaderboard["display_name"],
                entry_count=leaderboard["entry_count"],
                sort_method=LeaderboardSortMethod.try_value(leaderboard["sort_method"]),
                display_type=LeaderboardDisplayType.try_value(leaderboard["display_type"]),
            )
            for leaderboard in leaderboards
        ]

    async def fetch_leaderboard(self, name: str) -> Leaderboard[Self, None]:
        """Fetch a leaderboard by name.

        Parameters
        ----------
        name
            The name of the leaderboard to fetch.

            Note
            ----
            This is not the name of the leaderboard shown in the app's stat page, you can find the name of the leaderboard
            from :meth:`leaderboards`.
        """
        from .leaderboard import Leaderboard

        leaderboard = await self._state.fetch_or_create_app_leaderboard(self.id, name)
        return Leaderboard(
            self._state,
            id=LeaderboardID(int(leaderboard.leaderboard_id)),
            app=self,
            name=leaderboard.leaderboard_name,
            entry_count=leaderboard.leaderboard_entry_count,
            sort_method=LeaderboardSortMethod.try_value(leaderboard.leaderboard_sort_method),
            display_type=LeaderboardDisplayType.try_value(leaderboard.leaderboard_display_type),
        )

    async def create_leaderboard(self, name: str) -> Leaderboard[Self, None]:
        """Create a leaderboard with a given name.

        Parameters
        ----------
        name
            The name of the leaderboard to create.
        """
        from .leaderboard import Leaderboard

        leaderboard = await self._state.fetch_or_create_app_leaderboard(self.id, name, create=True)
        return Leaderboard(
            self._state,
            id=LeaderboardID(int(leaderboard.leaderboard_id)),
            app=self,
            name=leaderboard.leaderboard_name,
            entry_count=leaderboard.leaderboard_entry_count,
            sort_method=LeaderboardSortMethod.try_value(leaderboard.leaderboard_sort_method),
            display_type=LeaderboardDisplayType.try_value(leaderboard.leaderboard_display_type),
        )

    async def friends_who_own(self) -> list[Friend]:
        """Fetch the users in your friend list who own this app."""
        id64s = await self._state.fetch_friends_who_own(self.id)
        return [self._state.get_friend(_ID64_TO_ID32(id64)) for id64 in id64s]

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
        """An :term:`asynchronous iterator` for accessing a :class:`steam.App`'s
        :class:`steam.Review`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
        app = None

        yielded = 0

        while True:
            data = await self._state.http.get_reviews(self.id, "all", "all", "all", cursor)
            if cursor == "*":
                app = ReviewApp(self._state, self.id, data["query_summary"]["review_score"])
            assert app
            cursor = data["cursor"]
            reviews = data["reviews"]

            for review, user in zip(
                reviews,
                await self._state.fetch_users(ID64(int(review["author"]["steamid"])) for review in reviews),
            ):
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
            [self._state.get_friend(id) for id in cast("list[ID32]", proto.accountids_recommended)],
            [self._state.get_friend(id) for id in cast("list[ID32]", proto.accountids_not_recommended)],
        )

    async def fetch(self, *, language: Language | None = None) -> FetchedApp:
        """Fetch this app.

        Shorthand for:

        .. code:: python

            app = await client.fetch_app(app_id, language=language)
        """
        return await self._state.fetch_app(self.id, language=language)

    async def store_item(self, *, language: Language | None = None) -> AppStoreItem:
        """Fetch the store item for this app.

        Shorthand for:

        .. code:: python

            (item,) = await client.fetch_store_item(apps=[app], language=language)
        """
        from .store import AppStoreItem

        language = language or self._state.http.language
        (item,) = await self._state.fetch_store_info(app_ids=(self.id,), language=language)
        return AppStoreItem(self._state, item, language)

    async def info(self) -> AppInfo:
        """Fetches this app's product info.

        Shorthand for:

        .. code:: python

            (info,) = await client.fetch_product_info(apps=[app])
        """
        (info,), _ = await self._state.fetch_product_info((self.id,))
        return info

    async def depots(self) -> Sequence[Depot | HeadlessDepot]:
        """Fetch the depots for this app."""
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
            self.id, ManifestID(id), DepotID(depot_id), name=None, branch=branch, password_hash=password_hash
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
        """An :term:`asynchronous iterator` for accessing a this app's :class:`steam.Manifest`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
        after = after or UNIX_EPOCH
        before = before or DateTime.now()

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
        """An :term:`asynchronous iterator` for accessing an app's :class:`steam.PublishedFile`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
                file = PublishedFile(self._state, file, self._state.get_partial_user(file.creator))
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

    async def dlc(self, *, language: Language | None = None) -> list[DLC]:
        """Fetch the app's DLC.

        Parameters
        ----------
        language
            The language to fetch the DLC in. If ``None``, the current language will be used.
        """
        data = await self._state.http.get_app_dlc(self.id, language)
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
        info = await self._state.request_free_licenses(self.id)
        return info[self.id]

    async def shop_items(self, *, currency: Currency | None = None, language: Language | None = None) -> AppShopItems:
        """Fetch the items that are purchasable inside of the app's shop.

        Parameters
        ----------
        currency
            If passed only return the prices in this currency otherwise return the prices in all supported currencies.
        language
            The language to resolve the descriptions of the items to. If ``None`` uses the current language.
        """
        data = await self._state.http.get_app_asset_prices(self.id, currency)
        tags = (
            [
                AppShopItemTag(name, display_name, id)
                for (display_name, name), id in zip(data["tags"].items(), data["tag_ids"].values())
            ]
            if "tags" in data and "tag_ids" in data
            else []
        )

        INSTANCE_ID_0 = InstanceID(0)
        assets = {(ClassID(int(asset["classid"])), INSTANCE_ID_0): asset for asset in data["assets"]}
        return AppShopItems(
            [
                AppShopItem(self._state, assets[class_id, INSTANCE_ID_0], description, tags)
                for (class_id, _), description in (await self._state.fetch_item_info(self.id, assets, language)).items()
            ],
            tags,
        )

    async def community_items(
        self, *, type: CommunityDefinitionItemType = CommunityDefinitionItemType.NONE, language: Language | None = None
    ) -> list[CommunityItem[Self]]:
        """Fetch the app's community item definitions.

        Parameters
        ----------
        type
            The type of community item definitions to fetch.
        language
            The language to fetch the community item definitions in. If ``None``, the current language will be used.
        """
        defs = await self._state.fetch_community_item_definitions(self.id, type, language)
        return [
            CommunityItem(
                self._state,
                def_.item_type,
                self,
                def_.item_name,
                def_.item_title,
                def_.item_description,
                (
                    CDNAsset(
                        self._state,
                        f"{URL.CDN}/steamcommunity/public/images/items/{def_.item_image_large or def_.item_image_small}",
                    )
                    if def_.item_image_large or def_.item_image_small
                    else None
                ),
                (
                    CDNAsset(
                        self._state,
                        f"{URL.CDN}/steamcommunity/public/images/items/{def_.item_movie_mp4 or def_.item_movie_mp4_small}",
                    )
                    if def_.item_movie_mp4 or def_.item_movie_mp4_small
                    else None
                ),
                JSON_LOADS(def_.item_key_values) if def_.item_key_values else None,
                def_.item_series,
                CommunityItemClass.try_value(def_.item_class),
                await self._state._maybe_user(def_.editor_accountid) if def_.editor_accountid else None,
                def_.active,
                (
                    CDNAsset(
                        self._state,
                        f"https://community.cloudflare.steamstatic.com/economy/image/{def_.item_image_composed}",
                    )
                    if def_.item_image_composed
                    else None
                ),
                (
                    CDNAsset(
                        self._state, f"{URL.CDN}/steamcommunity/public/images/items/{def_.item_image_composed_foil}"
                    )
                    if def_.item_image_composed_foil
                    else None
                ),
                def_.deleted,
                DateTime.from_timestamp(def_.item_last_changed) if def_.item_last_changed else None,
            )
            for def_ in defs
        ]

    async def reward_items(self, *, language: Language | None = None) -> list[RewardItem[Self]]:
        """Fetch the app's reward item definitions.

        Parameters
        ----------
        language
            The language to fetch the reward item definitions in. If ``None``, the current language will be used.
        """
        defs = await self._state.fetch_reward_items(self.id, language)
        items = [
            RewardItem(
                def_.type,
                self,
                def_.community_item_data.item_name,
                def_.community_item_data.item_title,
                def_.community_item_data.item_description,
                def_.internal_description,  # really seems to be the name?
                (
                    CDNAsset(
                        self._state,
                        (
                            f"{URL.CDN}/steamcommunity/public/images/items/"
                            f"{def_.community_item_data.item_image_large or def_.community_item_data.item_image_small}"
                        ),
                    )
                    if def_.community_item_data.item_image_large or def_.community_item_data.item_image_small
                    else None
                ),
                (
                    CDNAsset(
                        self._state,
                        (
                            f"{URL.CDN}/steamcommunity/public/images/items/"
                            f"{def_.community_item_data.item_movie_mp4 or def_.community_item_data.item_movie_mp4_small}"
                        ),
                    )
                    if def_.community_item_data.item_movie_mp4 or def_.community_item_data.item_movie_mp4_small
                    else None
                ),
                def_.community_item_data.animated,
                tuple(
                    AppBadge(
                        self._state,
                        1,
                        f"{def_.community_item_data.item_name.removesuffix(' Point Shop Badge')} - Level {badge.level}",
                        self,
                        CDNAsset(self._state, f"{URL.CDN}/steamcommunity/public/images/items/{self.id}/{badge.image}"),
                        badge.level,
                    )
                    for badge in def_.community_item_data.badge_data
                ),
                def_.defid,
                def_.quantity,
                CommunityItemClass.try_value(def_.community_item_class),
                def_.community_item_type,
                def_.point_cost,
                DateTime.from_timestamp(def_.timestamp_created),
                DateTime.from_timestamp(def_.timestamp_updated),
                DateTime.from_timestamp(def_.timestamp_available),
                DateTime.from_timestamp(def_.timestamp_available_end),
                def_.active,
                def_.community_item_data.profile_theme_id,
                timedelta(seconds=def_.usable_duration),
                def_.bundle_discount,
            )
            for def_ in defs
        ]
        for item, def_ in zip(items, defs):
            if def_.bundle_defids:
                item.bundles = cast(
                    "tuple[RewardItem[Self], ...]", tuple(utils.get(items, def_index=id) for id in def_.bundle_defids)
                )

        return items

    async def badges(self, *, language: Language | None = None) -> Sequence[AppBadge[Self]]:
        """Fetch this app's badges.

        Parameters
        ----------
        language
            The language to fetch the badges in. If ``None``, the current language will be used.
        """
        if self.id == STEAM.id:
            # 753 doesn't have a community item definition, so we just have the badges hardcoded
            return [
                AppBadge(self._state, badge.id, badge.name, self, CDNAsset(self._state, badge.url), level=badge.level)
                for badge in STEAM_BADGES
            ]

        community_items, rewards = await asyncio.gather(
            self.community_items(language=language), self.reward_items(language=language)
        )

        badge_def = utils.get(community_items, class_=CommunityItemClass.Badge)
        badge_rewards = utils.get(rewards, class_=CommunityItemClass.Badge)

        if badge_def is None and badge_rewards is None:
            return []
        if badge_def is not None and badge_rewards is None:
            return badge_def.badges
        if badge_def is None and badge_rewards is not None:
            return badge_rewards.badges

        assert badge_def
        assert badge_rewards
        return [*badge_def.badges, *badge_rewards.badges]

    async def legacy_cd_key(self) -> str:
        """Fetch the legacy CD key for this app."""
        return await self._state.fetch_legacy_cd_key(self.id)

    async def encrypted_ticket(self, key: bytes, *, user_data: bytes = b"") -> EncryptedTicket:
        """Fetch an encrypted ticket for this app.

        Parameters
        ----------
        key
            The key to encrypt the ticket with.
        user_data
            The user data to include in the ticket.
        """
        encrypted_ticket = await self._state.fetch_encrypted_app_ticket(self.id, user_data)
        return EncryptedTicket(self._state, encrypted_ticket, key)

    async def ownership_ticket(self) -> OwnershipTicket:
        """Fetch an ownership ticket for this app."""
        ticket = await self._state.fetch_app_ownership_ticket(self.id)
        return await parse_app_ticket(self._state, utils.StructIO(ticket))

    @asynccontextmanager
    async def create_authentication_ticket(self) -> AsyncGenerator[AuthenticationTicket, None]:
        """Create an authentication ticket for this app.

        Examples
        --------

        .. code:: python

            async with app.create_authentication_ticket() as ticket:
                ...  # send the ticket to a user or server
                # ticket will only be valid inside this block
        """
        # for the ticket to be valid we have to be playing the game
        async with self._state.temporarily_play(self):
            ownership_ticket = await self._state.fetch_app_ownership_ticket(self.id)
            with utils.StructIO() as io:
                bytes = self._state._game_connect_bytes.pop(0)
                io.write_u32(len(bytes))
                io.write(bytes)
                io.write_u32(24)
                io.write_u32(1)
                io.write_u32(2)
                io.write_u32(int(self._state.ws.public_ip))
                io.write_u32(0)
                io.write_u32(int((self._state.steam_time.timestamp() - self._state.ws.connect_time.timestamp()) * 1000))
                self._state.connection_count += 1
                io.write_u32(self._state.connection_count)
                io.write_u32(len(ownership_ticket))
                io.write(ownership_ticket)
                io.seek(0)
                ticket = await parse_app_ticket(self._state, io)
                assert isinstance(ticket, AuthenticationTicket)
                try:
                    await ticket.activate()
                    yield ticket
                finally:
                    await ticket.deactivate()


class Apps(PartialApp[str], Enum):
    """This is "enum" to trick type checkers into allowing Literal[TF2] to be valid for overloads in extensions."""

    __slots__ = ("_name",)

    @classmethod
    def _new_member(cls, *, name: str, value: tuple[str, int]) -> Self:
        self = object.__new__(cls)
        set_attribute = object.__setattr__
        set_attribute(self, "_name", name)
        set_attribute(self, "name", value[0])
        set_attribute(self, "id", value[1])
        return self

    def __repr__(self) -> str:
        return self._name

    @property
    def value(self) -> int:
        return self.id

    TF2 = "Team Fortress 2", 440
    LFD2 = "Left 4 Dead 2", 550
    DOTA2 = "DOTA 2", 570
    CSGO = "Counter Strike Global-Offensive", 730
    STEAM = "Steam", 753

    @property
    def _state(self) -> ConnectionState:
        try:
            return STATE.get()
        except LookupError:
            raise ValueError("Cannot access the state of constant apps outside of a client.") from None


TF2 = Apps.TF2
"""The Team Fortress 2 app."""
DOTA2 = Apps.DOTA2
"""The DOTA 2 app."""
CSGO = Apps.CSGO
"""The Counter Strike Global-Offensive app."""
LFD2 = Apps.LFD2
"""The Left 4 Dead 2 app."""
STEAM = Apps.STEAM
"""The Steam app with context ID 6 (gifts)."""


class OwnershipDLC(PartialApp):
    def __init__(self, state: ConnectionState, *, id: int, owned_packages: list[PartialPackage]):
        super().__init__(state, id=id)
        self.owned_packages = owned_packages
        """The packages that the ticket owner owns which grant them this DLC."""


@dataclass(slots=True)
class PartialAppPriceOverview:
    currency: Currency
    initial: int
    final: int
    discount_percent: int


class DLC(PartialApp[str]):
    """Represents DLC (downloadable content) for an app."""

    __slots__ = (
        "created_at",
        "logo",
        "price_overview",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
    )

    def __init__(self, state: ConnectionState, data: app.DLC):
        super().__init__(state, id=data["id"], name=data["name"])
        self.created_at = (
            DateTime.from_timestamp(int(data["release_date"]["steam"])) if data["release_date"]["steam"] else None
        )
        """The time the DLC was released at."""
        self.logo = CDNAsset(state, data["header_image"])
        """The logo url of the DLC."""
        currency_code = Currency[data["price_overview"].pop("currency")]  # type: ignore  # TypedDict is immutable
        self.price_overview = PartialAppPriceOverview(currency=currency_code, **data["price_overview"])  # type: ignore
        """A price overview for the DLC."""

        platforms = data["platforms"]
        self._on_windows = platforms["windows"]
        self._on_mac_os = platforms["mac"]
        self._on_linux = platforms["linux"]

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


class UserApp(PartialApp[str]):
    """Represents a Steam app fetched by :meth:`steam.User.apps`."""

    __slots__ = (
        "playtime_forever",
        "playtime_two_weeks",
        "playtime_windows",
        "playtime_mac_os",
        "playtime_linux",
        "icon",
        "last_played_at",
        "content_descriptors",
        "_stats_visible",
        "_workshop",
        "_market",
        "_dlc",
        "_leaderboards",
    )

    def __init__(self, state: ConnectionState, proto: player.GetOwnedGamesResponseGame):
        super().__init__(state=state, id=proto.appid, name=proto.name)
        self.playtime_forever: timedelta = timedelta(minutes=proto.playtime_forever)
        """The total time the app has been played for."""
        self.playtime_two_weeks: timedelta = timedelta(minutes=proto.playtime_2_weeks)
        """The amount of time the user has played the app in the last two weeks."""
        self.playtime_windows: timedelta = timedelta(minutes=proto.playtime_windows_forever)
        """The total amount of time the user has played the app on Windows."""
        self.playtime_mac_os: timedelta = timedelta(minutes=proto.playtime_mac_forever)
        """The total amount of time the user has played the app on macOS."""
        self.playtime_linux: timedelta = timedelta(minutes=proto.playtime_linux_forever)
        """The total amount of time the user has played the app on Linux."""
        self.icon = CDNAsset(
            state, str(URL.CDN / f"steamcommunity/public/images/apps/{self.id}/{proto.img_icon_url}.jpg")
        )
        """The icon of the app."""
        self.last_played_at = DateTime.from_timestamp(proto.rtime_last_played)
        """The time the user last played this app at."""

        self.content_descriptors = [
            ContentDescriptor.try_value(descriptor) for descriptor in proto.content_descriptorids
        ]
        """The content descriptors of the app."""

        self._stats_visible = proto.has_community_visible_stats
        self._workshop = proto.has_workshop
        self._market = proto.has_market
        self._dlc = proto.has_dlc
        self._leaderboards = proto.has_leaderboards

    def has_visible_stats(self) -> bool:
        """Whether the app has publicly visible stats."""
        return self._stats_visible

    def has_workshop(self) -> bool:
        """Whether the app has a workshop."""
        return self._workshop

    def has_market(self) -> bool:
        """Whether the app has a market."""
        return self._market

    def has_dlc(self) -> bool:
        """Whether the app has DLC."""
        return self._dlc

    def has_leaderboards(self) -> bool:
        """Whether the app has leaderboards."""
        return self._leaderboards


class UserRecentlyPlayedApp(PartialApp[str]):
    def __init__(self, state: ConnectionState, data: app.UserRecentlyPlayedApp):
        super().__init__(state, id=data["appid"], name=data["name"])
        self.playtime_forever: timedelta = timedelta(minutes=data["playtime_forever"])
        """The total time the app has been played for."""
        self.playtime_two_weeks: timedelta = timedelta(minutes=data["playtime_2weeks"])
        """The amount of time the user has played the app in the last two weeks."""
        self.icon = CDNAsset(
            state, str(URL.CDN / f"steamcommunity/public/images/apps/{self.id}/{data['img_icon_url']}.jpg")
        )
        """The icon of the app."""


class WishlistApp(PartialApp[str]):
    """Represents a Steam app fetched by :meth:`steam.User.wishlist`\\."""

    __slots__ = (
        "priority",
        "added_at",
        "background",
        "created_at",
        "logo",
        "rank",
        "review_status",
        "score",
        "screenshots",
        # "tags",
        "total_reviews",
        "type",
        "partial_packages",
        "partial_bundles",
        "_free",
        "_on_linux",
        "_on_mac_os",
        "_on_windows",
    )

    def __init__(self, state: ConnectionState, id: int, data: app.WishlistApp):
        from .bundle import PartialBundle
        from .package import PartialPackage

        super().__init__(state, id=id, name=data["name"])
        self.priority = int(data["priority"])
        """The priority of the app in the wishlist."""
        self.type = AppType.from_str(data["type"])
        """The type of the app."""
        self.logo = CDNAsset(state, data["capsule"])
        """The logo of the app."""
        self.score = data["review_score"]
        """The score of the app out of ten."""
        self.total_reviews = int(data["reviews_total"].replace(",", ""))
        """The total number reviews for the app."""
        self.review_status = ReviewType.try_value(data["review_score"])
        """The review status of the app."""
        self.created_at = DateTime.from_timestamp(float(data["release_date"])) if data["release_date"] else None
        """The time the app was uploaded at."""
        self.screenshots = [
            CDNAsset(state, f"{URL.CDN}/steam/apps/{self.id}/{screenshot_url}")
            for screenshot_url in data["screenshots"]
        ]
        """The screenshots of the app."""
        self.added_at = DateTime.from_timestamp(data["added"])
        """The time that the app was added to their wishlist."""
        self.background = CDNAsset(state, data["background"])
        """The background of the app."""
        # self.tags = [Tag(state, int(tag)) for tag in data["tags"]]
        # """The tags of the app."""
        self.rank = data["rank"]
        """The global rank of the app by popularity."""
        self.partial_packages: list[PartialPackage] = []
        """The packages this app is included in."""
        self.partial_bundles: list[PartialBundle] = []
        """The bundles this app is included in."""
        for sub in data["subs"]:
            if package_id := sub["packageid"]:
                self.partial_packages.append(PartialPackage(state, id=package_id))
            elif bundle_id := sub["bundleid"]:
                self.partial_bundles.append(PartialBundle(state, id=bundle_id))

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


class FetchedAppMovie(_IOMixin):
    __slots__ = ("name", "id", "url", "created_at", "_state")

    def __init__(self, state: ConnectionState, movie: dict[str, Any]):
        self._state = state
        self.name: str = movie["name"]
        self.id: int = movie["id"]
        self.url: ReadOnly[str] = movie["mp4"]["max"]
        match = re.search(r"t=(\d+)", self.url)  # type: ignore  # should become unnecessary at some point
        self.created_at = DateTime.from_timestamp(int(match[1])) if match else None

    def __repr__(self) -> str:
        attrs = ("name", "id", "url", "created_at")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"


@dataclass(slots=True)
class AppPriceOverview(PartialAppPriceOverview):
    initial_formatted: str
    final_formatted: str


class FetchedApp(PartialApp[str]):
    """Represents a Steam app fetched by :meth:`steam.Client.fetch_app`\\."""

    __slots__ = (
        "logo",
        "background",
        "created_at",
        "type",
        "categories",
        "partial_dlc",
        "_packages",
        "website_url",
        "developers",
        "publishers",
        "description",
        "full_description",
        "movies",
        "price_overview",
        "content_descriptors",
        "_free",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
        "_language",
    )

    def __init__(self, state: ConnectionState, data: app.FetchedApp, language: Language):
        from .package import PartialPackage

        super().__init__(state, id=data["steam_appid"], name=data["name"])
        self.logo = CDNAsset(state, data["header_image"])
        """The logo of the app."""
        self.background = CDNAsset(state, data["background"])
        """The background of the app."""
        self.created_at = (
            DateTime.parse_steam_date(data["release_date"]["date"], full_month=False)
            if data["release_date"]["date"]
            else None
        )
        """The time the app was uploaded at."""
        self.type = AppType.from_str(data["type"])
        """The type of the app."""

        self.categories = [
            Category(state, id=category["id"], name=category["description"]) for category in data["categories"]
        ]

        try:
            currency = Currency[data["price_overview"].pop("currency")]  # type: ignore
            self.price_overview = AppPriceOverview(currency=currency, **data["price_overview"])  # type: ignore
            """The price overview of the app."""
        except KeyError:
            self.price_overview = None

        self.partial_dlc = [PartialApp(state, id=dlc_id) for dlc_id in data.get("dlc", [])]
        """The app's downloadable content."""

        from .package import FetchedAppPackage

        self._packages = [
            FetchedAppPackage(state, package)
            for package_group in data["package_groups"]
            for package in package_group["subs"]
        ]
        current_package_ids = {package.id for package in self._packages}
        self._packages += [
            PartialPackage(state, id=package_id)
            for package_id in data.get("packages", [])
            if package_id not in current_package_ids
        ]

        self.website_url = data.get("website")
        """The website URL of the app."""
        self.developers = data["developers"]
        """The developers of the app."""
        self.publishers = data["publishers"]
        """The publishers of the app."""
        self.description = data["short_description"]
        """The short description of the app."""
        self.full_description = data["detailed_description"]
        """The full description of the app."""

        self.movies = [FetchedAppMovie(state, movie) for movie in data["movies"]] if "movies" in data else None
        """
        A list of the app's movies, each of which has ``name``\\, ``id``\\, ``url`` and optional ``created_at``
        attributes.
        """
        self.content_descriptors = [
            ContentDescriptor.try_value(descriptor) for descriptor in data.get("content_descriptors", {}).get("ids", [])
        ]
        """The app's content descriptors for explicit content"""

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


class UserInventoryInfoApp(PartialApp[str]):
    __slots__ = ("icon", "inventory_logo")

    def __init__(self, state: ConnectionState, id: int, name: str, icon_url: str, inventory_logo_url: str):
        super().__init__(state, id=id, name=name)
        self.icon = CDNAsset(state, icon_url)
        """The icon of the app."""
        self.inventory_logo = CDNAsset(state, inventory_logo_url)
        """The inventory logo of the app."""


class AppListApp(PartialApp[str]):
    """Represents an app returned by :class:`~steam.Client.all_apps`."""

    __slots__ = ("last_modified", "price_change_number")

    def __init__(self, state: ConnectionState, data: app.AppListApp):
        super().__init__(state, id=data["appid"], name=data["name"])
        self.last_modified = DateTime.from_timestamp(data["last_modified"])
        """The time the app was last modified at."""
        self.price_change_number = data["price_change_number"]
        """The price change number of the app."""
