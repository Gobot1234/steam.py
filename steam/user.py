# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

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

import re
from datetime import timedelta
from typing import TYPE_CHECKING, List, Optional

from .abc import BaseUser, Messageable
from .enums import *
from .models import URL

if TYPE_CHECKING:
    from .group import Group
    from .state import ConnectionState
    from .image import Image
    from .trade import TradeOffer


__all__ = (
    'User',
    'ClientUser',
)

ETypeChars = ''.join([type_char.name for type_char in ETypeChar])

_ICODE_HEX = "0123456789abcdef"
_ICODE_CUSTOM = "bcdfghjkmnpqrtvw"
_ICODE_VALID = f'{_ICODE_HEX}{_ICODE_CUSTOM}'
_ICODE_MAPPING = dict(zip(_ICODE_HEX, _ICODE_CUSTOM))
_ICODE_INVERSE_MAPPING = dict(zip(_ICODE_CUSTOM, _ICODE_HEX))


class User(Messageable, BaseUser):
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
    steam_id: :class:`SteamID`
        The SteamID instance attached to the user.
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
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. Could be ``None`` (e.g. if they are currently online).
    country: Optional[:class:`str`]
        The country code of the account. Could be ``None``.
    flags: :class:`~steam.EPersonaStateFlag`
        The persona state flags of the account.
    id64: :class:`int`
        The 64 bit id of the user's account.
    id3: :class:`str`
        The id3 of the user's account. Used for newer steam games.
    id2: :class:`str`
        The id2 of the user's account. Used for older steam games.
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

    async def escrow(self, token: str = None) -> Optional[timedelta]:
        """|coro|
        Check how long a :class:`User`'s escrow is.

        Parameters
        ----------
        token: Optional[:class:`str`]
            The user's trade offer token.

        Returns
        --------
        Optional[:class:`datetime.timedelta`]
            The time at which any items sent/received would arrive
            ``None`` if the :class:`User` has no escrow or has a private inventory.
        """
        resp = await self._state.http.get_user_escrow(self.id64, token)
        their_escrow = resp['response'].get('their_escrow')
        if their_escrow is None:  # private
            return None
        seconds = their_escrow['escrow_end_duration_seconds']
        return timedelta(seconds=seconds) if seconds else None

    async def send(self, content: str = None, *, trade: 'TradeOffer' = None, image: 'Image' = None):
        """|coro|
        Send a message, trade or image to an :class:`User`.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The message to send to the user.
        trade: Optional[:class:`.TradeOffer`]
            The trade offer to send to the user.
        image: Optional[:class:`.Image`]
            The image to send to the user.

        Raises
        ------
        :exc:`~steam.HTTPException`
            Something failed to send.
        """

        if content is not None:
            await self._state.send_message(self.id64, str(content))
        if image is not None:
            await self._state.http.send_image(self.id64, image)
        if trade is not None:
            to_send = [item.to_dict() for item in trade.items_to_send]
            to_receive = [item.to_dict() for item in trade.items_to_receive]
            resp = await self._state.http.send_trade_offer(self.id64, self.id, to_send,
                                                           to_receive, trade.token, trade.message)
            if resp.get('needs_mobile_confirmation', False):
                await self._state.get_and_confirm_confirmation(int(resp['tradeofferid']))

    async def invite_to_group(self, group: 'Group'):
        """|coro|
        Invites a :class:`~steam.User` to a :class:`Group`.

        Parameters
        -----------
        group: :class:`~steam.Group`
            The group to invite the user to.
        """
        await self._state.http.invite_user_to_group(self.id64, group.id64)

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
        The Game instance attached to the user. Is ``None`` if the user
        isn't in a game or one that is recognised by the api.
    avatar_url: :class:`str`
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name: Optional[:class:`str`]
        The user's real name defined by them. Could be ``None``.
    primary_group: Optional[:class:`int`]
        The user's primary group. Could be ``None``
    created_at: Optional[:class:`datetime.datetime`]
        The time at which the user's account was created. Could be ``None``.
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. Could be ``None`` (e.g. if they are currently online).
    country: Optional[:class:`str`]
        The country code of the account. Could be ``None``.
    flags: :class:`~steam.EPersonaStateFlag`
        The persona state flags of the account.
    """
    # TODO more stuff to add https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/profile.js

    __slots__ = ('friends',)

    def __init__(self, state: 'ConnectionState', data: dict):
        super().__init__(state, data)
        self.friends = []

    async def __ainit__(self):
        await self.fetch_friends()

    def __repr__(self):
        attrs = (
            'name', 'state',
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        resolved.append(super().__repr__())
        return f"<ClientUser {' '.join(resolved)}>"

    async def fetch_friends(self) -> List[User]:
        self.friends = await super().fetch_friends()
        return self.friends

    async def wallet_balance(self) -> Optional[float]:
        """|coro|
        Fetches the :class:`ClientUser`'s current wallet balance.

        Returns
        -------
        Optional[:class:`float`]
            The current wallet balance.
        """
        resp = await self._state.request('GET', url=f'{URL.STORE}/steamaccount/addfunds')
        search = re.search(r'Wallet <b>\([^\d]*(\d*)(?:[.,](\d*)|)[^\d]*\)</b>', resp, re.UNICODE)
        if search is None:
            return None

        return float(f'{search.group(1)}.{search.group(2)}') if search.group(2) else float(search.group(1))

    async def setup_profile(self) -> None:
        if self.has_setup_profile():
            return

        params = {
            "welcomed": 1
        }
        await self._state.request('GET', url=f'{URL.COMMUNITY}/me/edit', params=params)

    async def clear_nicks(self) -> None:
        """|coro|
        Clears the :class:`ClientUser`'s nickname/alias history.
        """
        await self._state.http.clear_nickname_history()
