"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Protocol, runtime_checkable

from typing_extensions import TypeVar

from .types.id import AssetID
from .types.user import UserT
from .utils import DateTime, get

if TYPE_CHECKING:
    from .app import STEAM, PartialApp
    from .models import CDNAsset
    from .state import ConnectionState
    from .trade import Item
    from .types import user


__all__ = (
    "AppBadge",
    "BadgeProgress",
    "FavouriteBadge",
    "UserBadge",
    "UserBadges",
)

AppT = TypeVar("AppT", bound="PartialApp", default="PartialApp", covariant=True)


@runtime_checkable
class BaseBadge(Protocol[AppT]):
    __slots__ = ("id", "level", "app", "_state")
    _state: ConnectionState
    id: int
    """The badge's ID."""
    level: float
    """The badge's level. :class:`int` or ``float("inf")``"""
    app: Final[AppT]
    """The app associated with the badge."""

    def __init__(self, state: ConnectionState, id: int, level: float, app: AppT) -> None:
        self._state = state
        self.id = id
        self.level = level
        self.app = app

    def __repr__(self) -> str:
        attrs = ("id", "level", "app")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, BaseBadge) and self.id == other.id and self.app == other.app and self.level == other.level
        )

    def __hash__(self) -> int:
        return hash((self.id, self.app, self.level))

    async def _fetch_app_badge(self) -> AppBadge[AppT]:
        badges = await self.app.badges()
        badge = get(badges, id=self.id)
        assert badge is not None
        return badge

    async def name(self) -> str:
        """Fetches the name of this badge."""
        app_badge = await self._fetch_app_badge()
        return app_badge._name

    async def icon(self) -> CDNAsset:
        """Fetches the URL of this badge."""
        app_badge = await self._fetch_app_badge()
        return app_badge._icon


class AppBadge(BaseBadge[AppT]):
    """Represents a badge for an app."""

    __slots__ = ("_name", "_icon")

    def __init__(self, state: ConnectionState, id: int, name: str, app: AppT, icon: CDNAsset, level: float = 1):
        super().__init__(state, id, level, app)
        self._name = name
        self._icon = icon

    async def name(self) -> str:
        return self._name

    async def icon(self) -> CDNAsset:
        return self._icon

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} name()={self._name!r} level={self.level} app={self.app!r}>"


class BadgeProgress(NamedTuple):
    quest_id: int
    complete: bool


@runtime_checkable
class BaseOwnedBadge(BaseBadge[AppT], Protocol[AppT, UserT]):
    __slots__ = ("owner", "community_item_id")
    owner: Final[UserT]
    """The user who owns this badge."""
    community_item_id: AssetID | None
    r"""The badge's community item ID. By itself this doesn't correspond to anything in the :attr:`owner`\s inventory.
     - ``-1`` is the associated emoticon created by crafting the badge.
     - ``-2`` is the associated background created by crafting the badge.
    """

    def __init__(
        self, state: ConnectionState, id: int, level: int, app: AppT, owner: UserT, community_item_id: int | str | None
    ):
        super().__init__(state, id, level, app)
        self.owner = owner
        self.community_item_id = AssetID(int(community_item_id)) if community_item_id is not None else None

    async def _from_inventory(self, offset: int) -> Item[UserT]:
        from .app import STEAM

        if self.community_item_id is None:
            raise ValueError("This badge doesn't have an associated item.")

        inventory = await self.owner.inventory(STEAM)
        item = get(inventory, id=self.community_item_id - offset)
        if item is None:
            raise ValueError("This badge doesn't have an associated item.")
        return item

    async def emoticon(self) -> Item[UserT]:
        """The emoticon for this badge as an :class:`Item`.

        Raises
        ------
        ValueError
            The emoticon for this badge doesn't exist.
        """
        return await self._from_inventory(1)

    async def background(self) -> Item[UserT]:
        """The background for this badge as an :class:`Item`.

        Raises
        ------
        ValueError
            The background for this badge doesn't exist.
        """
        return await self._from_inventory(2)

    async def progress(self: BaseOwnedBadge[Literal[STEAM]]) -> list[BadgeProgress]:
        """Get the progress

        Returns
        -------
        .. source:: BadgeProgress
        """
        data = await self._state.http.get_user_community_badge_progress(self.owner.id64, self.id)
        return [BadgeProgress(badge["questid"], badge["completed"]) for badge in data]


class FavouriteBadge(BaseOwnedBadge[AppT, UserT]):
    """Represents a User's favourite badge."""

    __slots__ = ("border_colour", "type")

    def __init__(
        self,
        state: ConnectionState,
        id: int,
        level: int,
        app: AppT,
        owner: UserT,
        community_item_id: int,
        type: int,
        border_colour: int,
    ):
        super().__init__(state, id, level, app, owner, community_item_id)
        self.type = type
        """The badge's type."""
        self.border_colour = border_colour
        """The badge's border colour."""


class UserBadge(BaseOwnedBadge["PartialApp | Literal[STEAM]", UserT]):
    """Represents a Steam badge on a user's profile."""

    __slots__ = ("xp", "scarcity", "completed_at")

    def __init__(self, state: ConnectionState, owner: UserT, data: user.UserBadgeBadge):
        from .app import STEAM, PartialApp

        super().__init__(
            state,
            data["badgeid"],
            data["level"],
            PartialApp(state, id=data["appid"]) if "appid" in data else STEAM,
            owner,
            data.get("communityitemid"),
        )
        self.xp = data["xp"]
        """The badge's XP."""
        self.completed_at = DateTime.from_timestamp(data["completion_time"])
        """The time the badge was completed at."""
        self.scarcity = data["scarcity"]
        """The scarcity of the badge. The lower this value, the rarer the badge."""


class UserBadges(Sequence[UserBadge[UserT]]):
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

    def __init__(self, state: ConnectionState, user: UserT, data: user.UserBadges):
        self.user = user
        self.level = data["player_level"]
        """The user's level."""
        self.xp = data["player_xp"]
        """The users's XP."""
        self.xp_needed_to_level_up = data["player_xp_needed_to_level_up"]
        """The amount of XP the user needs to level up."""
        self.xp_needed_for_current_level = data["player_xp_needed_current_level"]
        """The amount of XP the user's current level requires to achieve."""
        self.badges: Sequence[UserBadge[UserT]] = [UserBadge(state, user, data) for data in data["badges"]]
        """A list of the user's badges."""

    def __repr__(self) -> str:
        attrs = ("level", "xp")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f'<UserBadges {" ".join(resolved)}>'

    def __len__(self) -> int:
        return len(self.badges)

    if not TYPE_CHECKING:

        def __getitem__(self, idx):
            return self.badges[idx]
