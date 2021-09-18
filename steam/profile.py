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

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from . import utils
from .enums import ProfileItemType, Result
from .errors import WSException
from .game import StatefulGame

if TYPE_CHECKING:
    from .protobufs import player
    from .state import ConnectionState

__all__ = (
    "ProfileInfo",
    "ProfileItem",
    "OwnedProfileItems",
    "EquippedProfileItems",
    "Profile",
)


@dataclass
class ProfileInfo:
    """Represents the user's profile info.

    Attributes
    ----------
    created_at
        The time at which the user was created at.
    real_name
        The real name of the user.
    city_name
        The city the user is located in.
    state_name
        The name of the state the user is located in.
    country_name
        The name of the country the user is located in.
    headline
        The profile's headline.
    summary
        The user's summary.
    """

    created_at: datetime
    real_name: str | None
    city_name: str | None
    state_name: str | None
    country_name: str | None
    headline: str | None
    summary: str


@dataclass
class ProfileMovie:
    url: str  # TODO add more attributes like maybe created_at?


class ProfileItem:
    """Represents an item on/in a user's profile.

    Attributes
    ----------
    id
        The item's id.
    url
        The item's url.
    name
        The item's name.
    title
        The item's title.
    description
        The item's description.
    game
        The game the item is from.
    type
        The item's type.
    class_
        The item's class.
    movie
        The movie associated with the item.
    equipped_flags
        The item's equipped flags.
    """

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
        "_state",
        "_um_name",
    )

    def __init__(self, state: ConnectionState, item: player.ProfileItem, *, um_name: str | None = None):
        self.id = item.communityitemid
        self.url = item.image_large
        self.name = item.name
        self.title = item.item_title
        self.description = item.item_description
        self.game = StatefulGame(state, id=item.appid)
        self.type = ProfileItemType.try_value(item.item_type)
        self.class_ = item.item_class
        self.movie = ProfileMovie(item.movie_mp4)
        self.equipped_flags = item.equipped_flags  # TODO might be useful for item show case?
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


@dataclass
class OwnedProfileItems:
    r"""Represents the :class:`ClientUser`\'s owned items.

    Attributes
    ----------
    backgrounds
        The backgrounds the client user owns.
    mini_profile_backgrounds
        The mini profile backgrounds the client user owns.
    avatar_frames
        The avatar frames the client user owns.
    animated_avatars
        The animated avatars the client user owns.
    modifiers
        The modifiers the client user owns.
    """
    __slots__ = ("backgrounds", "mini_profile_backgrounds", "avatar_frames", "animated_avatars", "modifiers")
    backgrounds: list[ProfileItem]
    mini_profile_backgrounds: list[ProfileItem]
    avatar_frames: list[ProfileItem]
    animated_avatars: list[ProfileItem]
    modifiers: list[ProfileItem]


@dataclass
class EquippedProfileItems:
    """Represents the items the user has equipped.

    Attributes
    ----------
    background
        The equipped background.
    mini_profile_background
        The equipped mini profile background for the user.
    avatar_frame
        The equipped avatar frame for the user.
    animated_avatar
        The equipped animated avatar for the user.
    modifier
        The equipped modifier for the user.
    """

    background: ProfileItem | None
    mini_profile_background: ProfileItem | None
    avatar_frame: ProfileItem | None
    animated_avatar: ProfileItem | None
    modifier: ProfileItem | None


class Profile(ProfileInfo, EquippedProfileItems):
    r"""Represents a user's complete profile.

    Attributes
    ----------
    background
        The equipped background.
    mini_profile_background
        The equipped mini profile background for the user.
    avatar_frame
        The equipped avatar frame for the user.
    animated_avatar
        The equipped animated avatar for the user.
    modifier
        The equipped modifier for the user.
    items
        The account's owned profile items.

        Note
        ----
        This is only available for the :class:`ClientUser`\'s profile otherwise it is ``None``.
    """

    def __init__(self, equipped_items: EquippedProfileItems, info: ProfileInfo, items: OwnedProfileItems | None = None):
        utils.update_class(equipped_items, self)
        utils.update_class(info, self)
        self.items = items

    def __repr__(self) -> str:
        return f"<Profile real_name={self.real_name!r}>"
