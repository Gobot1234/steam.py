"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .abc import SteamID
    from .clan import Clan
    from .enums import FriendRelationship
    from .state import ConnectionState
    from .user import User


__all__ = (
    "Invite",
    "UserInvite",
    "ClanInvite",
)


class Invite:
    __slots__ = ("invitee", "relationship", "_state")

    def __init__(self, state: ConnectionState, invitee: User | SteamID, relationship: FriendRelationship | None):
        self._state = state
        self.invitee = invitee
        self.relationship = relationship

    async def accept(self) -> None:
        raise NotImplementedError()

    async def decline(self) -> None:
        raise NotImplementedError()


class UserInvite(Invite):
    """Represents a invite from a user to become their friend.

    Attributes
    ----------
    invitee
        The user who sent the invite.
    relationship
        The relationship you have with the invitee.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        attrs = ("invitee",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<UserInvite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """Accept the invite request."""
        await self._state.http.accept_user_invite(self.invitee.id64)

    async def decline(self) -> None:
        """Decline the invite request."""
        await self._state.http.decline_user_invite(self.invitee.id64)


class GroupInvite(Invite):
    ...


class ClanInvite(Invite):
    """Represents a invite to join a :class:`~steam.Clan` from a user.

    Attributes
    ----------
    clan
        The clan to join.
    invitee
        The user who sent the invite.
    relationship
        The relationship you have with the clan.
    """

    __slots__ = ("clan",)

    def __init__(
        self,
        state: ConnectionState,
        invitee: User | SteamID,
        clan: Clan | SteamID,
        relationship: FriendRelationship | None,
    ):
        super().__init__(state, invitee, relationship)
        self.clan = clan

    def __repr__(self) -> str:
        attrs = ("invitee", "clan")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<ClanInvite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """Accept the invite request."""
        await self._state.respond_to_clan_invite(self.clan.id64, True)

    async def decline(self) -> None:
        """Decline the invite request."""
        await self._state.respond_to_clan_invite(self.clan.id64, False)
