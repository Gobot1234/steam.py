# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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

This contains a copy of
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
"""

import re
from datetime import timedelta
from typing import List, Optional, Union, TYPE_CHECKING

from .abc import BaseUser, Messageable
from .enums import *
from .models import URL
from .trade import Item, Asset

if TYPE_CHECKING:
    from .group import Group

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

    async def unblock(self) -> None:
        """|coro|
        Unblocks the :class:`User`.
        """
        await self._state.http.unblock_user(self.id64)

    async def block(self) -> None:
        """|coro|
        Blocks the :class:`User`.
        """
        await self._state.http.block_user(self.id64)

    async def send_trade(self, *, items_to_send: Union[List[Item], List[Asset]] = None,
                         items_to_receive: Union[List[Item], List[Asset]] = None,
                         token: str = None, message: str = None) -> None:
        """|coro|
        Sends a trade offer to an :class:`User`.

        Parameters
        -----------
        items_to_send: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        items_to_receive: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        token: Optional[:class:`str`]
            The the trade token used to send trades to users who aren't
            on the ClientUser's friend's list.
        message: Optional[:class:`str`]
             The offer message to send with the trade.

        Raises
        ------
        :exc:`.Forbidden`
            The offer failed to send. Likely due to
            too many offers being sent to this user.
        """
        items_to_send = [] if items_to_send is None else items_to_send
        items_to_receive = [] if items_to_receive is None else items_to_receive
        message = message if message is not None else ''
        resp = await self._state.http.send_trade_offer(self.id64, self.id, items_to_send,
                                                       items_to_receive, token, message)
        if resp.get('needs_mobile_confirmation', False):
            await self._state.get_and_confirm_confirmation(int(resp['tradeofferid']))

    async def fetch_escrow(self) -> Optional[timedelta]:
        """|coro|
        Check how long a :class:`User`'s escrow is.

        Returns
        --------
        Optional[:class:`datetime.timedelta`]
            The time at which any items sent/received would arrive
            ``None`` if the :class:`User` has no escrow.
        """
        resp = await self._state.http.fetch_user_escrow(self.id)
        seconds = resp['their_escrow']['escrow_end_duration_seconds']
        return timedelta(seconds=seconds) if seconds else None

    async def send(self, content: str = None):
        """Send a message to the user

        .. note::
            This does not currently function.

        Returns
        ---------
        :class:`~steam.Message`
            The send message.
        """
        return await self._state.send_message(user_id64=self.id64, content=str(content))

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

    def __init__(self, state, data):
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

    async def fetch_wallet_balance(self) -> Optional[float]:
        """|coro|
        Fetches the :class:`ClientUser`'s current wallet balance.

        Returns
        -------
        Optional[:class:`float`]
            The current wallet balance.
        """
        resp = await self._state.request('GET', f'{URL.STORE}/steamaccount/addfunds')
        search = re.search(r'Wallet <b>\([^\d]*(\d*)(?:[.,](\d*)|)[^\d]*\)</b>', resp, re.UNICODE)
        if search is None:
            return None

        return float(f'{search.group(1)}.{search.group(2)}') if search.group(2) else float(search.group(1))

    async def clear_nicks(self):
        """|coro|
        Clears the :class:`ClientUser`'s nickname/alias history.
        """
        await self._state.http.clear_nickname_history()

    async def edit(self, *, nick: str = None, real_name: str = None, country: str = None,
                   state: str = None, city: str = None, summary: str = None,
                   group: 'Group' = None):  # TODO check works
        self.name = nick if nick is not None else self.name
        self.real_name = real_name if real_name is not None else self.real_name if self.real_name else ''
        self.country = country if country is not None else self.country if self.country else ''
        self.city = city if city is not None else self.city if self.city else ''
        self.primary_group = group.id64 if group is not None else self.primary_group if self.primary_group else 0

        await self._state.http.edit_profile(self.name, real_name, country, state, city, summary, group)
