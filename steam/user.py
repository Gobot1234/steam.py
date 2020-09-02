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

from datetime import timedelta
from typing import TYPE_CHECKING, List, Optional

from .abc import BaseUser, Messageable
from .errors import ConfirmationError
from .models import community_route

if TYPE_CHECKING:
    from .clan import Clan
    from .group import Group
    from .image import Image
    from .state import ConnectionState
    from .trade import TradeOffer


__all__ = (
    "User",
    "ClientUser",
)


class User(BaseUser, Messageable):
    """Represents a Steam user's account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: x != y

            Checks if two users are not equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name: :class:`str`
        The user's username.
    state: :class:`~steam.EPersonaState`
        The current persona state of the account (e.g. LookingToTrade).
    game: Optional[:class:`~steam.Game`]
        The Game instance attached to the user. Is ``None`` if the user
        isn't in a game or one that is recognised by the api.
    avatar_url: :class:`str`
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name: Optional[:class:`str`]
        The user's real name defined by them. Could be ``None``.
    primary_group: Optional[:class:`int`]
        The user's primary group.
    created_at: Optional[:class:`datetime.datetime`]
        The time at which the user's account was created. Could be ``None``.
    last_logon: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. This is only ``None`` if user hasn't been updated from the websocket.
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged off from steam. Could be ``None`` (e.g. if they are currently online).
    last_seen_online: Optional[:class:`datetime.datetime`]
        The last time the user could be seen online. This is only ``None`` if user hasn't been updated from the
        websocket.
    country: Optional[:class:`str`]
        The country code of the account. Could be ``None``.
    flags: :class:`~steam.EPersonaStateFlag`
        The persona state flags of the account.
    """

    async def add(self) -> None:
        """|coro|
        Sends a friend invite to an :class:`User` to your friends list.
        """
        await self._state.http.add_user(self.id64)

    async def remove(self) -> None:
        """|coro|
        Remove an :class:`User` from your friends list.
        """
        await self._state.http.remove_user(self.id64)
        try:
            self._state.client.user.friends.remove(self)
        except ValueError:
            pass

    async def cancel_invite(self):
        """|coro|
        Cancels an invite sent to an :class:`User`. This effectively does the same thing as :meth:`remove`.
        """
        await self._state.http.remove_user(self.id64)

    async def block(self) -> None:
        """|coro|
        Blocks the :class:`User`.
        """
        await self._state.http.block_user(self.id64)

    async def unblock(self) -> None:
        """|coro|
        Unblocks the :class:`User`.
        """
        await self._state.http.unblock_user(self.id64)

    async def escrow(self, token: Optional[str] = None) -> Optional[timedelta]:
        """|coro|
        Check how long a :class:`User`'s escrow is.

        Parameters
        ----------
        token: Optional[:class:`str`]
            The user's trade offer token.

        Returns
        --------
        Optional[:class:`datetime.timedelta`]
            The time at which any items sent/received would arrive ``None`` if the :class:`User` has no escrow or has a
            private inventory.
        """
        resp = await self._state.http.get_user_escrow(self.id64, token)
        their_escrow = resp["response"].get("their_escrow")
        if their_escrow is None:  # private
            return None
        seconds = their_escrow["escrow_end_duration_seconds"]
        return timedelta(seconds=seconds) if seconds else None

    def _get_message_endpoint(self):
        return self.id64, self._state.send_user_message

    def _get_image_endpoint(self):
        return self.id64, self._state.http.send_user_image

    async def send(
        self, content: Optional[str] = None, *, trade: Optional["TradeOffer"] = None, image: Optional["Image"] = None
    ) -> None:
        """|coro|
        Send a message, trade or image to an :class:`User`.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The message to send to the user.
        trade: Optional[:class:`.TradeOffer`]
            The trade offer to send to the user.

            .. note::
                This will have its :attr:`~steam.TradeOffer.id` attribute updated after being sent.
        image: Optional[:class:`.Image`]
            The image to send to the user.

        Raises
        ------
        :exc:`~steam.HTTPException`
            Sending the message failed.
        :exc:`~steam.Forbidden`
            You do not have permission to send the message.
        """

        await super().send(content, image)
        if trade is not None:
            to_send = [item.to_dict() for item in trade.items_to_send]
            to_receive = [item.to_dict() for item in trade.items_to_receive]
            resp = await self._state.http.send_trade_offer(self, to_send, to_receive, trade.token, trade.message or "")
            trade._has_been_sent = True
            if resp.get("needs_mobile_confirmation", False):
                for tries in range(5):
                    try:
                        await trade.confirm()
                    except ConfirmationError:
                        break
            trade.id = int(resp["tradeofferid"])

    async def invite_to_group(self, group: "Group"):
        """|coro|
        Invites a :class:`~steam.User` to a :class:`Group`.

        Parameters
        -----------
        group: :class:`~steam.Group`
            The group to invite the user to.
        """
        await self._state.invite_user_to_group(self.id64, group.id)

    async def invite_to_clan(self, clan: "Clan"):
        """|coro|
        Invites a :class:`~steam.User` to a :class:`Clan`.

        Parameters
        -----------
        clan: :class:`~steam.Clan`
            The clan to invite the user to.
        """
        await self._state.http.invite_user_to_clan(self.id64, clan.id64)

    def is_friend(self) -> bool:
        """:class:`bool`: Species if the user is in the :class:`ClientUser`'s friends."""
        return self in self._state.client.user.friends


class ClientUser(BaseUser):
    """Represents your account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: x != y

            Checks if two users are not equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name: :class:`str`
        The user's username.
    friends: List[:class:`User`]
        A list of the :class:`ClientUser`'s friends.
    state: :class:`~steam.EPersonaState`
        The current persona state of the account (e.g. LookingToTrade).
    game: Optional[:class:`~steam.Game`]
        The Game instance attached to the user. Is ``None`` if the user isn't in a game or one that is recognised by
        the api.
    avatar_url: :class:`str`
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name: Optional[:class:`str`]
        The user's real name defined by them. Could be ``None``.
    primary_group: Optional[:class:`int`]
        The user's primary group. Could be ``None``
    created_at: Optional[:class:`datetime.datetime`]
        The time at which the user's account was created. Could be ``None``.
    last_logon: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. This is only ``None`` if user hasn't been updated from the websocket.
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged off from steam. Could be ``None`` (e.g. if they are currently online).
    last_seen_online: Optional[:class:`datetime.datetime`]
        The last time the user could be seen online. This is only ``None`` if user hasn't been updated from the
        websocket.
    country: Optional[:class:`str`]
        The country code of the account. Could be ``None``.
    flags: Union[:class:`~steam.EPersonaStateFlag`, :class:`int`]
        The persona state flags of the account.
    """

    # TODO more stuff to add https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/profile.js

    __slots__ = ("friends",)

    def __init__(self, state: "ConnectionState", data: dict):
        super().__init__(state, data)
        self.friends: List[User] = []

    def __repr__(self):
        attrs = ("name", "state", "id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<ClientUser {' '.join(resolved)}>"

    async def setup_profile(self) -> None:
        """|coro|
        Set up your profile if possible.
        """
        if self.has_setup_profile():
            return

        params = {"welcomed": 1}
        await self._state.request("GET", community_route("/me/edit"), params=params)

    async def clear_nicks(self) -> None:
        """|coro|
        Clears the :class:`ClientUser`'s nickname/alias history.
        """
        await self._state.http.clear_nickname_history()

    async def edit(
        self,
        *,
        name: Optional[str] = None,
        real_name: Optional[str] = None,
        url: Optional[str] = None,
        summary: Optional[str] = None,
        country: Optional[str] = None,
        state: Optional[str] = None,
        city: Optional[str] = None,
        avatar: Optional["Image"] = None,
    ):
        """|coro|
        Edit the :class:`ClientUser`'s profile.
        Any values that aren't set will use their defaults.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The new name you wish to go by.
        real_name: Optional[:class:`str`]
            The real name you wish to go by.
        url: Optional[:class:`str`]
            The custom url ending/path you wish to use.
        summary: Optional[:class:`str`]
            The summary/description you wish to use.
        country: Optional[:class:`str`]
            The country you want to be from.
        state: Optional[:class:`str`]
            The state you want to be from.
        city: Optional[:class:`str`]
            The city you want to be from.
        avatar: Optional[:class:`~steam.Image`]
            The avatar you wish to use.

            .. note::
                This needs to be at least 184px x 184px.

        Raises
        -------
        :exc:`~steam.HTTPException`
            Editing your profile failed.
        """
        await self._state.http.edit_profile(name, real_name, url, summary, country, state, city, avatar)
