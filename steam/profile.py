"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from . import utils
from .badge import Badge
from .enums import (
    Language,
    ProfileCustomisationStyle,
    ProfileItemClass,
    ProfileItemType,
    PublishedFileRevision,
    Result,
    UserBadge,
)
from .errors import WSException
from .game import StatefulGame
from .trade import Asset, Item

if TYPE_CHECKING:
    from .abc import BaseUser
    from .protobufs import player
    from .published_file import PublishedFile
    from .state import ConnectionState
    from .types import trade

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
    summary: str
    """The user's summary."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} real_name={self.real_name!r}>"


@dataclass
class ProfileMovie:
    url: str  # TODO add more attributes like maybe created_at?


class ProfileItem:
    """Represents an item on/in a user's profile."""

    __slots__ = (
        "id",
        "url",
        "name",
        "title",
        "description",
        "game",
        "type",
        "class_",
        "movie",
        "equipped_flags",
        "owner",
        "_state",
        "_um_name",
    )

    def __init__(
        self, state: ConnectionState, owner: BaseUser, item: player.ProfileItem, *, um_name: str | None = None
    ):
        self.id = item.communityitemid
        """The item's id."""
        self.url = item.image_large
        """The item's url."""
        self.name = item.name
        """The item's name."""
        self.title = item.item_title
        """The item's title."""
        self.description = item.item_description
        """The item's description."""
        self.game = StatefulGame(state, id=item.appid)
        """The game the item is from."""
        self.type = ProfileItemType.try_value(item.item_type)
        """The item's type."""
        self.class_ = ProfileItemClass.try_value(item.item_class)
        """The item's class."""
        self.movie = ProfileMovie(item.movie_mp4)
        """The movie associated with the item."""
        self.equipped_flags = item.equipped_flags  # TODO might be useful for item show case?
        """The item's equipped flags."""

        self.owner = owner
        self._state = state
        self._um_name = um_name

    def __repr__(self) -> str:
        return f"<ProfileItem id={self.id} name={self.name!r} game={self.game!r}>"

    async def equip(self) -> None:
        """Equip the profile item."""
        if self._um_name is None:
            raise ValueError(f"Cannot equip {self!r}")

        msg = await self._state.ws.send_um_and_wait(f"Player.Set{self._um_name}", communityitemid=self.id)
        if msg.result != Result.OK:
            raise WSException(msg)

    async def item(self, *, language: Language | None = None) -> Item:
        """Resolve this to an actual item in the owner's inventory."""
        inventory = await self.owner.inventory(self.game, language=language)
        item = utils.get(inventory, id=self.id)
        assert item
        return item


@dataclass
class OwnedProfileItems:
    r"""Represents the :class:`ClientUser`\'s owned items."""

    backgrounds: list[ProfileItem]
    """The backgrounds the client user owns."""
    mini_profile_backgrounds: list[ProfileItem]
    """The mini profile backgrounds the client user owns."""
    avatar_frames: list[ProfileItem]
    """The avatar frames the client user owns."""
    animated_avatars: list[ProfileItem]
    """The animated avatars the client user owns."""
    modifiers: list[ProfileItem]
    """The modifiers the client user owns."""


@dataclass
class EquippedProfileItems:
    """Represents the items the user has equipped."""

    background: ProfileItem | None
    """The equipped background."""
    mini_profile_background: ProfileItem | None
    """The equipped mini profile background for the user."""
    avatar_frame: ProfileItem | None
    """The equipped avatar frame for the user."""
    animated_avatar: ProfileItem | None
    """The equipped animated avatar for the user."""
    modifier: ProfileItem | None
    """The equipped modifier for the user."""


@dataclass
class ProfileShowcaseSlot:
    __slots__ = (
        "_state",
        "owner",
        "name",
        "content",
        "index",
        "game",
        "asset",
        "published_file_id",
        "badge_id",
        "border_colour",
    )
    _state: ConnectionState
    owner: BaseUser
    name: str | None
    """The slot's name."""
    content: str | None
    """ The slot's description."""
    index: int | None
    """The slot's index."""
    game: StatefulGame
    """The slot's associated game."""

    asset: Asset | None
    """The :class:`Asset` the slot is associated with."""
    published_file_id: int | None
    """The ID of the :class:`PublishedFile` the slot is associated with."""
    badge_id: UserBadge | None
    """The ID of the :class:`UserBadge` the slot is associated with."""
    border_colour: int | None
    """The border colour of the slot."""

    async def item(self, *, language: Language | None = None) -> Item:
        """Fetches the associated :class:`.Item` from :attr:`asset`.

        Parameters
        ----------
        language
            The language to fetch the item in. If ``None``, the current language is used.
        """
        if self.asset is None:
            raise ValueError
        key = (self.asset.class_id, self.asset.instance_id)
        resp = await self._state.http.get_item_info(self.game.id, [key], language)
        data: trade.Item = {
            **resp[key],
            **self.asset.to_dict(),
            "missing": False,
        }  # type: ignore  # I don't wanna type out this in full to make this type-safe
        return Item(self._state, data, self.owner)

    async def published_file(
        self, *, revision: PublishedFileRevision = PublishedFileRevision.Default, language: Language | None = None
    ) -> PublishedFile:
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
        (file,) = await self._state.fetch_published_files((self.published_file_id,), revision, language)
        assert file
        return file

    async def badge(self) -> Badge:
        """Fetches the associated :class:`.Badge` from :attr:`badge_id`."""
        if self.badge_id is None:
            raise ValueError
        badges = await self.owner.badges()
        badge = utils.get(badges.badges, id=self.badge_id)
        assert badge
        return badge


@dataclass
class ProfileShowcase:
    __slots__ = (
        "_state",
        "owner",
        "type",
        "large",
        "active",
        "purchase_id",
        "level",
        "style",
        "slots",
    )
    _state: ConnectionState
    owner: BaseUser
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
    slots: list[ProfileShowcaseSlot]
    """The slots in this showcase."""

    async def items(self, *, language: Language | None) -> list[Item]:
        """Fetches the associated :class:`.Item`s for the entire showcase.

        Parameters
        ----------
        language
            The language to fetch the items in. If ``None``, the current language is used.
        """
        asset_map: defaultdict[int, dict[tuple[int, int], Asset]] = defaultdict(dict)

        for slot in self.slots:
            if slot.asset:
                asset_map[slot.asset._app_id][(slot.asset.class_id, slot.asset.instance_id)] = slot.asset

        return [
            Item(self._state, {**description, **assets[key].to_dict(), "missing": False}, self.owner)
            for app_id, assets in asset_map.items()
            for key, description in (await self._state.http.get_item_info(app_id, assets, language)).items()
        ]

    async def published_file(
        self, *, revision: PublishedFileRevision = PublishedFileRevision.Default, language: Language | None = None
    ) -> PublishedFile:
        """Fetches the associated :class:`.PublishedFile` from :attr:`published_file_id`.

        Parameters
        ----------
        revision
            The revision of the file to fetch.
        language
            The language to fetch the file in. If ``None``, the current language is used.
        """
        return await self.slots[0].published_file(revision=revision)

    async def badges(self) -> list[Badge]:
        """Fetches the associated :class:`.Badge`s for the entire showcase."""
        all_badges = await self.owner.badges()
        badges = [utils.get(all_badges.badges, id=slot.badge_id) for slot in self.slots if slot.badge_id]
        assert all(badges)
        return badges  # type: ignore


@dataclass
class ProfileTheme:
    __slots__ = ("id", "name")
    id: str
    name: str


@dataclass
class PurchasedCustomisation:  # TODO should this be merged into ProfileCustomisationSlot.purchase_id if the ids match
    __slots__ = ("id", "type", "level")
    id: int
    type: ProfileCustomisationStyle
    level: int


class ProfileCustomisation:
    """Represents a user's profile customisations."""

    __slots__ = (
        "showcases",
        "slots_available",
        "profile_theme",
        "purchased_customisations",
        "owner",
        "_state",
    )

    def __init__(self, state: ConnectionState, user: BaseUser, proto: player.GetProfileCustomizationResponse):
        self.showcases = [
            ProfileShowcase(
                state,
                owner=user,
                slots=[
                    ProfileShowcaseSlot(
                        state,
                        owner=user,
                        index=slot.slot or None,
                        game=StatefulGame(state, id=slot.appid),
                        published_file_id=slot.publishedfileid or None,
                        name=slot.title or None,
                        content=slot.notes or None,
                        badge_id=UserBadge.try_value(slot.badgeid) if slot.badgeid else None,
                        border_colour=slot.border_color or None,
                        asset=Asset(
                            {
                                "assetid": slot.item_assetid,  # type: ignore  # this just gets cast to an int anyway
                                "appid": slot.appid,
                                "contextid": slot.item_contextid,
                                "instanceid": slot.item_instanceid,
                                "classid": slot.item_classid,
                                "amount": 1,
                                "missing": False,
                            },
                            user,
                        )
                        if slot.item_assetid
                        else None,
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


class Profile(EquippedProfileItems, ProfileCustomisation):
    """Represents a user's complete profile."""

    __slots__ = ()

    def __init__(self, equipped_items: EquippedProfileItems, customisation_info: ProfileCustomisation):
        utils.update_class(equipped_items, self)
        utils.update_class(customisation_info, self)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} owner={self.owner!r}>"


class FriendProfile(ProfileInfo, EquippedProfileItems, ProfileCustomisation):
    """Represents a friend's complete profile."""

    def __init__(
        self, equipped_items: EquippedProfileItems, info: ProfileInfo, customisation_info: ProfileCustomisation
    ):
        utils.update_class(equipped_items, self)
        utils.update_class(info, self)
        utils.update_class(customisation_info, self)


class ClientUserProfile(FriendProfile):
    """Represents a :class:`ClientUser`'s full profile."""

    __slots__ = ("owned_items",)

    def __init__(
        self,
        equipped_items: EquippedProfileItems,
        info: ProfileInfo,
        customisation_info: ProfileCustomisation,
        items: OwnedProfileItems,
    ):
        super().__init__(equipped_items, info, customisation_info)
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
