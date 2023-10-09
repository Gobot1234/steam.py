"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol

from typing_extensions import TypeVar

from . import utils
from .app import STEAM, PartialApp
from .enums import *
from .errors import WSException
from .models import _IOMixin
from .protobufs import UnifiedMessage, econ
from .trade import Asset, Item
from .types.id import ID32, AppID, AssetID, PublishedFileID

if TYPE_CHECKING:
    from datetime import datetime

    from ._const import ReadOnly
    from .abc import PartialUser
    from .badge import UserBadge
    from .clan import Clan, PartialClan
    from .friend import Friend
    from .protobufs import player
    from .published_file import PublishedFile
    from .state import ConnectionState
    from .types import id
    from .user import ClientUser, User

__all__ = (
    "ProfileInfo",
    "ProfileItem",
    "OwnedProfileItems",
    "EquippedProfileItems",
    "ProfileShowcaseSlot",
    "ProfileCustomisation",
    "ProfileShowcase",
    "Profile",
)


@dataclass
class ProfileInfo:
    """Represents the user's profile info."""

    created_at: datetime
    """The time at which the user was created at."""
    real_name: str | None
    """The real name of the user."""
    city_name: str | None
    """The city the user is located in."""
    state_name: str | None
    """The name of the state the user is located in."""
    country_name: str | None
    """The name of the country the user is located in."""
    headline: str | None
    """The profile's headline."""
    summary: utils.BBCodeStr
    """The user's summary."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} real_name={self.real_name!r}>"


@dataclass
class ProfileMovie(_IOMixin):
    __slots__ = ("url", "_state")
    _state: ConnectionState
    url: ReadOnly[str]  # TODO add more attributes like maybe created_at?


class SupportsEquip(Protocol):
    def __init__(self, *, communityitemid: int) -> None:
        ...


UserT = TypeVar("UserT", bound="PartialUser", default="User", covariant=True)


class ProfileItem(Generic[UserT]):
    """Represents an item on/in a user's profile."""

    __slots__ = (
        "id",
        "url",
        "name",
        "title",
        "description",
        "app",
        "type",
        "class_",
        "movie",
        "equipped_flags",
        "owner",
        "_state",
        "_um",
    )

    def __init__(
        self,
        state: ConnectionState,
        owner: UserT,
        item: player.ProfileItem,
        *,
        um: type[SupportsEquip] | None = None,
    ):
        self.id = AssetID(item.communityitemid)
        """The item's id."""
        self.url = item.image_large
        """The item's url."""
        self.name = item.name
        """The item's name."""
        self.title = item.item_title
        """The item's title."""
        self.description = item.item_description
        """The item's description."""
        self.app = PartialApp(state, id=item.appid)
        """The app the item is from."""
        self.type = ProfileItemType.try_value(item.item_type)
        """The item's type."""
        self.class_ = CommunityItemClass.try_value(item.item_class)
        """The item's class."""
        self.movie = ProfileMovie(state, item.movie_mp4)
        """The movie associated with the item."""
        self.equipped_flags = ProfileItemEquippedFlag.try_value(item.equipped_flags)
        """The item's equipped flags."""

        self.owner = owner
        self._state = state
        if um is not None:
            assert issubclass(um, UnifiedMessage)  # until we have intersections this works with pyright
        self._um = um

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} name={self.name!r} app={self.app!r}>"

    async def equip(self) -> None:
        """Equip the profile item."""
        if self._um is None:
            raise ValueError(f"Cannot equip {self!r}")

        msg = await self._state.ws.send_um_and_wait(self._um(communityitemid=self.id))
        if msg.result != Result.OK:
            raise WSException(msg)

    async def item(self, *, language: Language | None = None) -> Item[UserT]:
        """Resolve this to an actual item in the owner's inventory."""
        inventory = await self.owner.inventory(STEAM, language=language)
        item = utils.get(inventory, id=self.id)
        assert item
        return item


@dataclass
class OwnedProfileItems(Generic[UserT]):
    r"""Represents the :class:`ClientUser`\'s owned items."""

    backgrounds: list[ProfileItem[UserT]]
    """The backgrounds the client user owns."""
    mini_profile_backgrounds: list[ProfileItem[UserT]]
    """The mini profile backgrounds the client user owns."""
    avatar_frames: list[ProfileItem[UserT]]
    """The avatar frames the client user owns."""
    animated_avatars: list[ProfileItem[UserT]]
    """The animated avatars the client user owns."""
    modifiers: list[ProfileItem[UserT]]
    """The modifiers the client user owns."""


@dataclass
class EquippedProfileItems(Generic[UserT]):
    """Represents the items the user has equipped."""

    background: ProfileItem[UserT] | None
    """The equipped background."""
    mini_profile_background: ProfileItem[UserT] | None
    """The equipped mini profile background for the user."""
    avatar_frame: ProfileItem[UserT] | None
    """The equipped avatar frame for the user."""
    animated_avatar: ProfileItem[UserT] | None
    """The equipped animated avatar for the user."""
    modifier: ProfileItem[UserT] | None
    """The equipped modifier for the user."""


@dataclass(repr=False, slots=True)
class ProfileShowcaseSlot(Generic[UserT]):
    """Represents a showcase slot."""

    _state: ConnectionState
    owner: UserT
    name: str | None
    """The slot's name."""
    content: str | None
    """ The slot's description."""
    index: int | None
    """The slot's index."""
    app: PartialApp | None
    """The slot's associated app."""

    asset: Asset[UserT] | None
    """The :class:`Asset` the slot is associated with."""
    published_file_id: PublishedFileID | None
    """The ID of the :class:`PublishedFile` the slot is associated with."""
    badge_id: int | None
    """The ID of the :class:`UserBadge` the slot is associated with."""
    border_colour: int | None
    """The border colour of the slot."""
    clan: Clan | PartialClan | None
    """The Steam ID of the clan the slot is associated with."""
    replay_year: int | None
    """If the :attr:`ProfileShowcase.type` is :attr:`ProfileItemType.Replay` the year the replay is for"""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} index={self.index!r} app={self.app!r}>"

    async def item(self, *, language: Language | None = None) -> Item[UserT]:
        """Fetches the associated :class:`.Item` from :attr:`asset`.

        Parameters
        ----------
        language
            The language to fetch the item in. If ``None``, the current language is used.
        """
        if self.asset is None:
            raise ValueError
        assert self.app is not None
        key = (self.asset.class_id, self.asset.instance_id)
        resp = await self._state.fetch_item_info(self.app.id, [key], language)
        return Item(self._state, self.asset.to_proto(), resp[key], self.owner)

    async def published_file(
        self, *, revision: PublishedFileRevision = PublishedFileRevision.Default, language: Language | None = None
    ) -> PublishedFile[UserT]:
        """Fetches the associated :class:`.PublishedFile` from :attr:`published_file_id`.

        Parameters
        ----------
        revision
            The revision of the published file to fetch.
        language
            The language to fetch the published file in. If ``None``, the current language is used.
        """
        if self.published_file_id is None:
            raise ValueError
        (file,) = await self._state.fetch_published_files_with_author(
            (self.published_file_id,), self.owner, revision, language
        )
        assert file
        return file

    async def badge(self) -> UserBadge[UserT]:
        """Fetches the associated :class:`.Badge` from :attr:`badge_id`."""
        if self.badge_id is None:
            raise ValueError
        badges = await self.owner.badges()
        badge = utils.get(
            badges.badges, id=self.badge_id, app__id=self.app.id if self.app and self.app.id != 753 else None
        )  # TODO manual

        assert badge
        return badge


@dataclass(repr=False, slots=True)
class ProfileShowcase(Generic[UserT]):
    """Represents a user's profile showcase."""

    _state: ConnectionState
    owner: UserT
    """The showcase's owner."""
    type: ProfileItemType
    """The showcase type."""
    large: bool
    """Whether the showcase is large."""
    active: bool
    """Whether the showcase is active."""
    purchase_id: int
    """The purchase id."""
    level: int
    """The level of the the showcase."""
    style: ProfileCustomisationStyle
    """The style of the showcase."""
    slots: list[ProfileShowcaseSlot[UserT]]
    """The slots in this showcase."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.type!r} active={self.active!r} level={self.level!r} style={self.style!r}>"

    async def items(self, *, language: Language | None = None) -> list[Item[UserT]]:
        """Fetches the associated :class:`.Item`\\s for the entire showcase.

        Parameters
        ----------
        language
            The language to fetch the items in. If ``None``, the current language is used.
        """
        asset_map: defaultdict[AppID, dict[id.CacheKey, Asset[UserT]]] = defaultdict(dict)

        for slot in self.slots:
            if slot.asset:
                asset_map[slot.asset._app_id][(slot.asset.class_id, slot.asset.instance_id)] = slot.asset

        return [
            Item(self._state, assets[key].to_proto(), description, self.owner)
            for app_id, assets in asset_map.items()
            for key, description in (await self._state.fetch_item_info(app_id, assets, language)).items()
        ]

    async def published_files(
        self, *, revision: PublishedFileRevision = PublishedFileRevision.Default, language: Language | None = None
    ) -> list[PublishedFile[UserT]]:
        """Fetches the associated :class:`.PublishedFile` for the entire showcase.

        Parameters
        ----------
        revision
            The revision of the file to fetch.
        language
            The language to fetch the file in. If ``None``, the current language is used.
        """
        published_files = await self._state.fetch_published_files_with_author(
            (slot.published_file_id for slot in self.slots if slot.published_file_id), self.owner, revision, language
        )
        assert all(published_files)
        return published_files  # type: ignore  # needs HKT to be fixed

    async def badges(self) -> list[UserBadge[UserT]]:
        """Fetches the associated :class:`.Badge`\\s for the entire showcase."""
        all_badges = await self.owner.badges()
        badges = [
            utils.get(all_badges, id=slot.badge_id, app__id=slot.app.id)
            for slot in self.slots
            if slot.badge_id and slot.app
        ]
        assert all(badges)
        return badges  # type: ignore


@dataclass(slots=True)
class ProfileTheme:
    id: str
    name: str


@dataclass(slots=True)
class PurchasedCustomisation:  # TODO should this be merged into ProfileCustomisationSlot.purchase_id if the ids match
    id: int
    type: ProfileCustomisationStyle
    level: int


class ProfileCustomisation(Generic[UserT]):
    """Represents a user's profile customisations."""

    __slots__ = (
        "showcases",
        "slots_available",
        "profile_theme",
        "purchased_customisations",
        "owner",
        "_state",
    )

    def __init__(self, state: ConnectionState, user: UserT, proto: player.GetProfileCustomizationResponse):
        from .clan import PartialClan

        self.showcases = [
            ProfileShowcase(
                state,
                owner=user,
                slots=[
                    ProfileShowcaseSlot(
                        state,
                        owner=user,
                        index=slot.slot,
                        app=PartialApp(state, id=slot.appid) if slot.appid else None,
                        published_file_id=PublishedFileID(slot.publishedfileid) or None,
                        name=slot.title or None,
                        content=slot.notes or None,
                        badge_id=slot.badgeid or None,
                        border_colour=slot.border_color or None,
                        asset=Asset(
                            state,
                            econ.Asset(
                                assetid=slot.item_assetid,
                                appid=slot.appid,
                                contextid=slot.item_contextid,
                                instanceid=slot.item_instanceid,
                                classid=slot.item_classid,
                                amount=1,
                            ),
                            user,
                        )
                        if slot.item_assetid
                        else None,
                        clan=(state.get_clan(ID32(slot.accountid)) or PartialClan(state, slot.accountid))
                        if slot.accountid
                        else None,
                        replay_year=slot.replay_year or None,
                    )
                    for slot in customisation.slots
                ],
                type=ProfileItemType.try_value(customisation.customization_type),
                large=customisation.large,
                active=customisation.active,
                style=ProfileCustomisationStyle.try_value(customisation.customization_style),
                purchase_id=customisation.purchaseid,
                level=customisation.level,
            )
            for customisation in proto.customizations
        ]
        self.slots_available = proto.slots_available
        self.profile_theme = ProfileTheme(proto.profile_theme.theme_id, proto.profile_theme.title)
        self.purchased_customisations = [
            PurchasedCustomisation(
                customisation.purchaseid,
                ProfileCustomisationStyle.try_value(customisation.customization_type),
                customisation.level,
            )
            for customisation in proto.purchased_customizations
        ]
        self.owner = user
        self._state = state

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} owner={self.owner!r}>"


class Profile(EquippedProfileItems[UserT], ProfileCustomisation[UserT]):
    """Represents a user's complete profile."""

    __slots__ = ()

    def __init__(self, equipped_items: EquippedProfileItems[UserT], customisation_info: ProfileCustomisation[UserT]):
        utils.update_class(equipped_items, self)
        utils.update_class(customisation_info, self)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} owner={self.owner!r}>"


class FriendProfile(ProfileInfo, Profile["Friend"]):
    """Represents a friend's complete profile."""

    def __init__(
        self, equipped_items: EquippedProfileItems, info: ProfileInfo, customisation_info: ProfileCustomisation
    ):
        utils.update_class(equipped_items, self)
        utils.update_class(info, self)
        utils.update_class(customisation_info, self)


class ClientUserProfile(ProfileInfo, Profile["ClientUser"]):
    """Represents a :class:`ClientUser`'s full profile."""

    def __init__(
        self,
        equipped_items: EquippedProfileItems[ClientUser],
        info: ProfileInfo,
        customisation_info: ProfileCustomisation[ClientUser],
        items: OwnedProfileItems[ClientUser],
    ):
        utils.update_class(equipped_items, self)
        utils.update_class(info, self)
        utils.update_class(customisation_info, self)

        self.owned_backgrounds = items.backgrounds
        """The backgrounds the client user owns."""
        self.owned_mini_profile_backgrounds = items.mini_profile_backgrounds
        """The mini profile backgrounds the client user owns."""
        self.owned_avatar_frames = items.avatar_frames
        """The avatar frames the client user owns."""
        self.owned_animated_avatars = items.animated_avatars
        """The animated avatars the client user owns."""
        self.owned_modifiers = items.modifiers
        """The modifiers the client user owns."""
