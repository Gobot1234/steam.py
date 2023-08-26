"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, TypeAlias

from .chat import ChatGroup

if TYPE_CHECKING:
    from .abc import PartialUser
    from .app import PartialApp
    from .clan import Clan, PartialClan
    from .enums import FriendRelationship
    from .game_server import GameServer
    from .group import Group
    from .state import ConnectionState
    from .user import ClientUser, User


__all__ = (
    "Invite",
    "UserInvite",
    "ClanInvite",
    "GroupInvite",
    "AppInvite",
)


@dataclass(slots=True)
class _Invite(metaclass=ABCMeta):
    _state: ConnectionState
    user: User | ClientUser | PartialUser
    """The user that was invited."""
    author: User | ClientUser | PartialUser
    """The user who sent the invite."""
    relationship: FriendRelationship | None
    """The relationship you have with the invitee."""
    REPR_ATTRS: ClassVar[tuple[str, ...]]

    @abstractmethod
    async def accept(self) -> None:
        """Accept the invite request."""
        raise NotImplementedError()

    def __repr__(self) -> str:
        cls = self.__class__
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in cls.REPR_ATTRS]
        return f"<{cls.__name__} {' '.join(resolved)}>"


@dataclass(repr=False, slots=True)
class UserInvite(_Invite):
    """Represents a invite from a user to become their friend."""

    REPR_ATTRS: ClassVar = ("author", "relationship")

    async def accept(self) -> None:
        await self._state.add_user(self.author.id64)

    async def decline(self) -> None:
        """Decline the invite request."""
        await self._state.remove_user(self.author.id64)


@dataclass(repr=False, slots=True)
class ChatGroupInvite(_Invite):
    if TYPE_CHECKING:
        code: str | None
        clan: Clan | PartialClan | None
        group: Group | None

    async def revoke(self) -> None:
        """Revoke the invite request."""
        await self._state.revoke_chat_group_invite(self.user.id64, self._chat_group._id)

    @property
    def _chat_group(self) -> Clan | Group:
        chat_group = self.clan or self.group
        assert chat_group is not None
        if not isinstance(chat_group, ChatGroup):
            # should be unreachable, but just in case
            raise ValueError(f"Expected a ChatGroup, got {chat_group.__class__.__name__}")
        return chat_group


@dataclass(repr=False, slots=True)
class ClanInvite(ChatGroupInvite):
    """Represents an invitation to join a :class:`~steam.Clan` from a user."""

    REPR_ATTRS: ClassVar = ("author", "relationship", "clan")
    clan: Clan | PartialClan
    """The clan to join."""
    relationship: FriendRelationship
    group: None = None
    code: str | None = None

    async def accept(self) -> None:
        await self._state.respond_to_clan_invite(self.clan.id64, True)

    async def decline(self) -> None:
        """Decline the invite request."""
        await self._state.respond_to_clan_invite(self.clan.id64, False)


@dataclass(repr=False, slots=True)
class GroupInvite(ChatGroupInvite):
    """Represents an invitation from a user to join a group."""

    REPR_ATTRS: ClassVar = ("author", "relationship", "group")
    group: Group
    """The group to join."""
    code: str
    clan: None = None

    async def accept(self) -> None:
        await self.group.join(invite_code=self.code)


@dataclass(repr=False, slots=True)
class AppInvite(_Invite):
    """Represents an invitation to join a :class:`~steam.App` from a user."""

    REPR_ATTRS: ClassVar = ("author", "app")
    app: PartialApp
    """The app to join."""
    server: GameServer | None
    """The server you being requested to join"""
    connect: str
    """A string containing information about the invite."""

    async def accept(self) -> None:
        return await super().accept()


Invite: TypeAlias = UserInvite | ClanInvite | GroupInvite | AppInvite
"""Represents an invite from a user to become their friend, join a clan, join a group, or join an app."""
