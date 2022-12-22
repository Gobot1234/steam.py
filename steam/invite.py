"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from typing_extensions import Self

from .enums import FriendRelationship, classproperty

if TYPE_CHECKING:
    from .abc import PartialUser
    from .app import PartialApp
    from .clan import Clan
    from .group import Group
    from .state import ConnectionState
    from .user import User


__all__ = (
    "Invite",
    "UserInvite",
    "ClanInvite",
    "GroupInvite",
)


@dataclass(slots=True)
class Invite(metaclass=ABCMeta):
    _state: ConnectionState
    invitee: User | PartialUser
    """The user who sent the invite."""
    relationship: FriendRelationship
    """The relationship you have with the invitee."""
    REPR_ATTRS: ClassVar[tuple[str, ...]]

    @abstractmethod
    async def accept(self) -> None:
        """Accept the invite request."""
        raise NotImplementedError()

    @abstractmethod
    async def decline(self) -> None:
        """Decline the invite request."""
        raise NotImplementedError()

    def __repr__(self) -> str:
        cls = self.__class__
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in cls.REPR_ATTRS]
        return f"<{cls.__name__} {' '.join(resolved)}>"


@dataclass(repr=False, slots=True)
class UserInvite(Invite):
    """Represents a invite from a user to become their friend."""

    REPR_ATTRS: Final = ("invitee", "relationship")

    async def accept(self) -> None:
        await self._state.add_user(self.invitee.id64)

    async def decline(self) -> None:
        await self._state.remove_user(self.invitee.id64)


@dataclass(repr=False, slots=True)
class GroupInvite(Invite):
    """Represents a invite from a user to join a group."""

    REPR_ATTRS: ClassVar = ("invitee", "relationship", "group")
    group: Group
    """The group to join."""

    async def accept(self) -> None:
        await self.group.join()

    async def decline(self) -> None:
        await self.group.leave()  # TODO this probably errors


@dataclass(repr=False, slots=True)
class ClanInvite(Invite):
    """Represents a invite to join a :class:`~steam.Clan` from a user."""

    REPR_ATTRS: ClassVar = ("invitee", "relationship", "clan")
    clan: Clan
    """The clan to join."""

    async def accept(self) -> None:
        await self._state.respond_to_clan_invite(self.clan.id64, True)

    async def decline(self) -> None:
        await self._state.respond_to_clan_invite(self.clan.id64, False)


@dataclass(repr=False, slots=True)
class AppInvite(Invite):
    """Represents a invite to join a :class:`~steam.App` from a user."""

    REPR_ATTRS: ClassVar = ("invitee", "app")
    app: PartialApp
    """The app to join."""

    @classproperty
    def relationship(cls: type[Self]) -> Literal[FriendRelationship.Friend]:  # type: ignore
        return FriendRelationship.Friend
