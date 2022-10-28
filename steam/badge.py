"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .app import PartialApp
from .utils import DateTime

if TYPE_CHECKING:
    from .abc import BaseUser
    from .state import ConnectionState


__all__ = (
    "FavouriteBadge",
    "UserBadge",
    "UserBadges",
)


class BaseBadge:
    __slots__ = ()
    id: int
    level: int
    app: PartialApp | None

    def __repr__(self) -> str:
        attrs = ("id", "level", "app")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return self.id == other.id and self.app == other.app if isinstance(other, BaseBadge) else NotImplemented


@dataclass(repr=False, slots=True)
class FavouriteBadge(BaseBadge):
    """Represents a User's favourite badge."""

    id: int
    """The badge's ID."""
    level: int
    """The badge's level."""
    app: PartialApp | None
    """The app associated with the badge."""
    community_item_id: int
    """The badge's community item ID."""
    type: int
    """The badge's type."""
    border_colour: int
    """The colour of the boarder of the badge."""


class UserBadge(BaseBadge):
    """Represents a Steam badge on a user's profile."""

    __slots__ = ("id", "xp", "app", "user", "level", "scarcity", "completion_time", "community_item_id")

    def __init__(self, state: ConnectionState, user: BaseUser, data: dict[str, Any]):
        self.id: int = data["badgeid"]
        """The badge's ID."""
        self.level: int = data["level"]
        """The badge's level."""
        self.xp: int = data["xp"]
        """The badge's XP."""
        self.completion_time = DateTime.from_timestamp(data["completion_time"])
        """The time the badge was completed at."""
        self.scarcity: int = data["scarcity"]
        """The scarcity of the badge."""
        self.app = PartialApp(state, id=data["appid"]) if "appid" in data else None
        """The app associated with the badge."""
        self.community_item_id: int | None = data.get("communityitemid")
        """The badge's community item ID."""
        self.user = user


class UserBadges(Sequence[UserBadge]):
    """Represents a Steam :class:`~steam.User`'s badges/level.

    .. container:: operations

        .. describe:: len(x)

            Returns the number of badges.

        .. describe:: iter(x)

            Returns an iterator over the badges.

        .. describe:: y in x

            Returns whether the badge is in the badges.

        .. describe:: x[y]

            Returns the badge at the given index.
    """

    __slots__ = (
        "user",
        "xp",
        "level",
        "badges",
        "xp_needed_to_level_up",
        "xp_needed_for_current_level",
    )

    def __init__(self, state: ConnectionState, user: BaseUser, data: dict[str, Any]):
        self.user = user
        self.level: int = data["player_level"]
        """The user's level."""
        self.xp: int = data["player_xp"]
        """The users's XP."""
        self.xp_needed_to_level_up: int = data["player_xp_needed_to_level_up"]
        """The amount of XP the user needs to level up."""
        self.xp_needed_for_current_level: int = data["player_xp_needed_current_level"]
        """The amount of XP the user's current level requires to achieve."""
        self.badges: Sequence[UserBadge] = [UserBadge(state, user, data) for data in data["badges"]]
        """A list of the user's badges."""

    def __repr__(self) -> str:
        attrs = ("level", "xp")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f'<UserBadges {" ".join(resolved)}>'

    def __len__(self) -> int:
        return len(self.badges)

    if not TYPE_CHECKING:

        def __getitem__(self, idx: Any) -> Any:
            return self.badges[idx]
