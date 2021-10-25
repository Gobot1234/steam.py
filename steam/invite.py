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


class UserInvite(Invite):
    """Represents a invite from a user to become their friend.

    Attributes
    ----------
    invitee
        The user who sent the invite.
    relationship
        The relationship you have with the invitee. This ``None`` if the invite was sent while the bot is online.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        attrs = ("invitee",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<UserInvite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """Accept the invite request."""
        await self._state.http.accept_user_invite(self.invitee.id64)
        self._state.client.user.friends.append(self.invitee)

    async def decline(self) -> None:
        """Decline the invite request."""
        await self._state.http.decline_user_invite(self.invitee.id64)


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
