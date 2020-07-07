# -*- coding: utf-8 -*-

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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .clan import Clan
    from .state import ConnectionState
    from .user import User


__all__ = (
    "Invite",
    "UserInvite",
    "ClanInvite",
)


class Invite:
    """Represents a invite from a user.

    Attributes
    ----------
    invitee: Union[:class:`~steam.User`, :class:`~steam.SteamID`]
        The user who sent the invite.
    """

    __slots__ = ("invitee", "_state")

    def __init__(self, state: "ConnectionState", invitee: "User"):
        self._state = state
        self.invitee = invitee


class UserInvite(Invite):
    """Represents a invite from a user.

    Attributes
    ----------
    invitee: Union[:class:`~steam.User`, :class:`~steam.SteamID`]
        The user who sent the invite.
    """

    def __repr__(self):
        attrs = ("invitee",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<UserInvite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """|coro|
        Accepts the invite request.
        """
        await self._state.http.accept_user_invite(self.invitee.id64)
        self._state.client.user.friends.append(self.invitee)

    async def decline(self) -> None:
        """|coro|
        Declines the invite request.
        """
        await self._state.http.decline_user_invite(self.invitee.id64)


class ClanInvite(Invite):
    """Represents a invite from a user.

    Attributes
    ----------
    clan: Union[:class:`~steam.Clan`, :class:`~steam.SteamID`]
        The clan to join.
    invitee: Union[:class:`~steam.User`, :class:`~steam.SteamID`]
        The user who sent the invite.
    """

    __slots__ = ("clan",)

    def __init__(self, state: "ConnectionState", invitee: "User", clan: "Clan"):
        super().__init__(state, invitee)
        self.clan = clan

    def __repr__(self):
        attrs = (
            "invitee",
            "clan",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<ClanInvite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """|coro|
        Accepts the invite request.
        """
        await self._state.http.accept_clan_invite(self.clan.id64)

    async def decline(self) -> None:
        """|coro|
        Declines the invite request.
        """
        await self._state.http.decline_clan_invite(self.clan.id64)
