# -*- coding: utf-8 -*-

"""
MIT License

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
with some extra doc-strings
"""

import json
from typing import List

import aiohttp

from .abc import BaseUser, Messageable
from .enums import *
from .models import *
from .trade import Item, TradeOffer

ETypeChars = ''.join([type_char.name for type_char in ETypeChar])


class SteamID(int):
    """Convert a Steam ID to its various representations.

    This takes a steam 64 bit account id, however, :meth:`make_steam64`
    is called on this class's initialization"""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.EType = EType
        self.EUniverse = EUniverse
        self.EInstanceFlag = EInstanceFlag

    def __new__(cls, *args, **kwargs):
        steam64 = make_steam64(*args, **kwargs)
        return super(SteamID, cls).__new__(cls, steam64)

    def __repr__(self):
        attrs = (
            'id', 'type', 'universe', 'instance'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<SteamID {' '.join(resolved)}>"

    @property
    def id(self):
        """:class:`int`: Represents the account id.
        This is also known as the 32 bit id"""
        return int(self) & 0xFFffFFff

    @property
    def instance(self):
        """:class:`int`: Returns the instance of the account."""
        return (int(self) >> 32) & 0xFFffF

    @property
    def type(self):
        """:class:`~steam.EType`:
        Represents the steam type of the account.
        """
        return EType((int(self) >> 52) & 0xF)

    @property
    def universe(self):
        """:class:`~steam.enum.EUniverse`:
        Represents the steam universe of the account.
        """
        return EUniverse((int(self) >> 56) & 0xFF)

    @property
    def as_32(self):
        """:class:`int`: The account's id.
        An alias to :attr:`SteamID.id`
        """
        return self.id

    @property
    def as_64(self):
        """:class:`int`: The steam 64 bit id of the account.
        Used for community profiles along with other useful things.
        """
        return int(self)

    @property
    def as_steam2(self):
        """class:`str`: The steam2 id of the account.
            e.g ``STEAM_1:0:1234``.
        .. note::
            ``STEAM_X:Y:Z``. The value of ``X`` should represent the universe, or ``1``
            for ``Public``. However, there was a bug in GoldSrc and Orange Box games
            and ``X`` was ``0``. If you need that format use :attr:`SteamID.as_steam2_zero`
        """
        return f'STEAM_{int(self.universe)}:{self.id % 2}:{self.id >> 1}'

    @property
    def as_steam2_zero(self):
        """:class:`str`: The steam2 id of the account.
        For GoldSrc and Orange Box games.
        See :class:`SteamID`:attr:`as_steam2`.
            e.g ``STEAM_0:0:1234``.
        """
        return self.as_steam2.replace('_1', '_0')

    @property
    def as_steam3(self):
        """:class:`str`: The steam3 id of the account.
        This is used for more recent games
            e.g ``[U:1:1234]``.
        """
        typechar = str(ETypeChar(self.type))
        instance = None

        if self.type in (EType.AnonGameServer, EType.Multiseat):
            instance = self.instance
        elif self.type == EType.Individual:
            if self.instance != 1:
                instance = self.instance
        elif self.type == EType.Chat:
            if self.instance & EInstanceFlag.Clan:
                typechar = 'c'
            elif self.instance & EInstanceFlag.Lobby:
                typechar = 'L'
            else:
                typechar = 'T'

        parts = [typechar, int(self.universe), self.id]

        if instance is not None:
            parts.append(instance)

        return f'[{":".join(map(str, parts))}]'

    @property
    def community_url(self):
        """:class:`str`: The community url of the account
            e.g https://steamcommunity.com/profiles/123456789.
        """
        suffix = {
            EType.Individual: 'profiles',
            EType.Clan: 'gid',
        }
        if self.type in suffix:
            return f'https://steamcommunity.com/{suffix[self.type]}/{self.as_64}'

        return None

    def is_valid(self):
        """Check whether this SteamID is valid.

        Returns
        -------
        :class:`bool`
        """
        if self.type == EType.Invalid or self.type >= EType.Max:
            return False

        if self.universe == EUniverse.Invalid or self.universe >= EUniverse.Max:
            return False

        if self.type == EType.Individual:
            if self.id == 0 or self.instance > 4:
                return False

        if self.type == EType.Clan:
            if self.id == 0 or self.instance != 0:
                return False

        if self.type == EType.GameServer:
            if self.id == 0:
                return False

        if self.type == EType.AnonGameServer:
            if self.id == 0 and self.instance == 0:
                return False

        return True


class User(Messageable, BaseUser):
    """Represents a Steam user's account."""

    def __init__(self, state, data):
        self._state = state
        super().__init__(state, data)

    async def add(self):
        """|coro|
        Add an :class:`User` to your friends list.
        """
        return await self._state.http.add_user(self.id64)

    async def remove(self):
        """|coro|
        Remove an :class:`User` from your friends list.
        """
        return await self._state.http.remove_user(self.id64)

    async def unblock(self):
        """|coro|
        Unblock an :class:`User`.
        """
        return await self._state.http.unblock_user(self.id64)

    async def block(self):
        """|coro|
        Block an :class:`User`.
        """
        return await self._state.http.block_user(self.id64)

    async def accept_invite(self):
        """|coro|
        Accept a friend invite from an :class:`User`.
        """
        return await self._state.http.accept_user_invite(self.id64)

    async def decline_invite(self):
        """|coro|
        Decline a friend invite from an :class:`User`.
        """
        return await self._state.http.decline_user_invite(self.id64)

    async def send_trade(self, items_to_send: List[Item] = None, items_to_receive: List[Item] = None,
                         message: str = None):
        """|coro|
        Sends a trade offer to an :class:`User`.

        Parameters
        -----------
        items_to_send: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        items_to_receive: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        message: :class:`str`
             The offer message to send with the trade.

        Raises
        ------
        :exc:`.Forbidden`
            The offer failed to send.
        """
        items_to_send = [] if items_to_send is None else items_to_send
        items_to_receive = [] if items_to_receive is None else items_to_receive
        resp = await self._state.http.send_trade_offer(self.id64, self.id, items_to_send, items_to_receive, message)
        trade_id = int(resp['tradeofferid'])
        if resp.get('needsconfirmation'):
            confirmation = await self._state.confirmation_manager.get_trade_confirmation(trade_id)
            await confirmation.confirm()
        resp = await self._state.http.fetch_trade(trade_id)
        data = resp['response']['offer']
        trade = TradeOffer(state=self._state, data=data, partner=self)
        self._state.client.dispatch('trade_send', trade)

    async def fetch_escrow(self):
        """|coro|
        Check how long a :class:`User`'s escrow is.
        """
        unix = self._state.http.fetch_user_escrow(url=self.community_url)
        return datetime.utcfromtimestamp(unix) if unix else None

    def is_friend(self):
        """:class:`bool`: Species if the user is in the ClientUser's friends"""
        return self in self._state.client.user.friends

    async def send(self, content: str = None):
        """Send a message to the user
        .. note::
            This does not currently function.
        """
        self._state.send_message(user_id64=self.id64, content=content)


class ClientUser(BaseUser):
    """Represents your account."""

    __slots__ = ('name', 'real_name', 'avatar_url', 'created_at', 'last_logoff',
                 'state', 'game', 'flags', 'country', 'id', 'steam_id',
                 'id64', 'id2', 'id3', 'friends', '_state', '_data')

    def __init__(self, state, data):
        self.friends = []
        self._state = state
        super().__init__(state, data)

    def __repr__(self):
        attrs = (
            'name', 'steam_id', 'state'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<ClientUser {' '.join(resolved)}>"

    async def __ainit__(self):
        await self.fetch_friends()

    async def fetch_friends(self):
        friends = await self._state.http.fetch_friends(self.id64)
        for friend in friends:
            if friend not in self.friends:
                self._state._store_user(friend)
                self.friends.append(User(state=self._state, data=friend))

    async def trades(self, limit=None, before: datetime = None, after: datetime = None):
        """An iterator for accessing a :class:`ClientUser`'s :class:`~steam.TradeOffer`s.

        Examples
        -----------

        Usage
        ~~~~~~~~~~
        .. code-block:: python3
            async for trade in client.user.trades(limit=10):
                print('Partner:', trade.partner, 'Sent:')
                print('\n'.join([item.name if item.name else item.asset_id for item in trade.items_to_receive])
                      if trade.items_to_receive else 'Nothing')

        Flattening into a list:
        ~~~~~~~~~
        .. code-block:: python3
            trades = await client.user.trades(limit=50).flatten()
            # trades is now a list of TradeOffer

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum comments to search through.
            Default is ``None`` which will fetch all the user's comments.
        before: Optional[:class:`datetime.datetime`]
            A time to search for trades before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for trades after.

        Yields
        ---------
        :class:`~steam.TradeOffer`
        """
        return TradesIterator(state=self._state, limit=limit, before=before, after=after)


def make_steam64(account_id=0, *args, **kwargs):
    """Returns steam64 from various other representations.

    .. code:: python

        make_steam64()  # invalid steam_id
        make_steam64(12345)  # account_id
        make_steam64('12345')
        make_steam64(id=12345, type='Invalid', universe='Invalid', instance=0)
        make_steam64(103582791429521412)  # steam64
        make_steam64('103582791429521412')
        make_steam64('STEAM_1:0:2')  # steam2
        make_steam64('[g:1:4]')  # steam3

    Raises
    ------
    :exc:`TypeError`
        Too many arguments have been given.
    :exc:`ValueError`
        Instance is too large.

    Returns
    -------
    id64: :class:`int`
    """

    etype = EType.Invalid
    universe = EUniverse.Invalid
    instance = None

    if len(args) == 0 and len(kwargs) == 0:
        value = str(account_id)

        # numeric input
        if value.isdigit():
            value = int(value)

            # 32 bit account id
            if 0 < value < 2 ** 32:
                account_id = value
                etype = EType.Individual
                universe = EUniverse.Public
            # 64 bit
            elif value < 2 ** 64:
                return value

        # textual input e.g. [g:1:4]
        else:
            result = steam2_to_tuple(value) or steam3_to_tuple(value)

            if result:
                (
                    account_id,
                    etype,
                    universe,
                    instance,
                ) = result
            else:
                account_id = 0

    elif len(args) > 0:
        length = len(args)
        if length == 1:
            etype, = args
        elif length == 2:
            etype, universe = args
        elif length == 3:
            etype, universe, instance = args
        else:
            raise TypeError(f"Takes at most 4 arguments ({length} given)")

    if len(kwargs) > 0:
        etype = kwargs.get('type', etype)
        universe = kwargs.get('universe', universe)
        instance = kwargs.get('instance', instance)

    etype = (EType(etype) if isinstance(etype, (int, EType)) else EType[etype])
    universe = (EUniverse(universe) if isinstance(universe, (int, EUniverse)) else EUniverse[universe])

    if instance is None:
        instance = 1 if etype in (EType.Individual, EType.GameServer) else 0

    return (universe << 56) | (etype << 52) | (instance << 32) | account_id


def steam2_to_tuple(value: str):
    """
    Parameters
    ----------
    value: :class:`str`
        steam2 e.g. ``STEAM_1:0:1234``.

    Returns
    -------
    steam2: Optional[:class:`tuple`]
        e.g. (account_id, type, universe, instance) or ``None``.
    .. note::
        The universe will be always set to ``1``. See :attr:`SteamID.as_steam2`.
    """
    match = re.match(
        r"^STEAM_(?P<universe>\d+)"
        r":(?P<reminder>[0-1])"
        r":(?P<id>\d+)$", value
    )

    if not match:
        return None

    steam32 = (int(match.group('id')) << 1) | int(match.group('reminder'))
    universe = int(match.group('universe'))

    # Games before orange box used to incorrectly display universe as 0, we support that
    if universe == 0:
        universe = 1

    return steam32, EType(1), EUniverse(universe), 1


def steam3_to_tuple(value: str):
    """
    Parameters
    ----------
    value: :class:`str`
        steam3 e.g. ``[U:1:1234]``.

    Returns
    -------
    steam2: Optional[:class:`tuple`]
        e.g. (account_id, type, universe, instance) or ``None``.
    """
    match = re.match(
        r"^\["
        r"(?P<type>[i%s]):"  # type char
        r"(?P<universe>[0-4]):"  # universe
        r"(?P<id>\d{1,10})"  # accountid
        r"(:(?P<instance>\d+))?"  # instance
        r"\]$" % ETypeChars,
        value
    )
    if not match:
        return None

    steam32 = int(match.group('id'))
    universe = EUniverse(int(match.group('universe')))
    typechar = match.group('type').replace('i', 'I')
    etype = EType(ETypeChar[typechar])
    instance = match.group('instance')

    if typechar in 'gT':
        instance = 0
    elif instance is not None:
        instance = int(instance)
    elif typechar == 'L':
        instance = EInstanceFlag.Lobby
    elif typechar == 'c':
        instance = EInstanceFlag.Clan
    elif etype in (EType.Individual, EType.GameServer):
        instance = 1
    else:
        instance = 0

    instance = int(instance)

    return steam32, etype, universe, instance


async def steam64_from_url(url: str, timeout=30):
    """Takes a Steam Community url and returns steam64 or None
    .. note::
        Each call makes a http request to steamcommunity.com
        For a reliable resolving of vanity urls use ``ISteamUser.ResolveVanityURL`` web api.
    .. note::
        Example URLs
            https://steamcommunity.com/gid/[g:1:4]

            https://steamcommunity.com/gid/103582791429521412

            https://steamcommunity.com/groups/Valve

            https://steamcommunity.com/profiles/[U:1:12]

            https://steamcommunity.com/profiles/76561197960265740

            https://steamcommunity.com/id/johnc

    Parameters
    ----------
    url: :class:`str`
        The Steam community url.
    timeout: :class:`int`
        How long to wait on http request before turning ``None``.

    Returns
    -------
    steam64: Optional[:class:`int`]
        If ``steamcommunity.com`` is down or no matching account is found returns ``None``
    """

    match = re.match(r'^(?P<clean_url>https?://steamcommunity.com/'
                     r'(?P<type>profiles|id|gid|groups)/(?P<value>.*?))(?:/(?:.*)?)?$', url)

    if match is None:
        return None

    session = aiohttp.ClientSession()

    try:
        # user profiles
        if match.group('type') in ('id', 'profiles'):
            async with session.get(match.group('clean_url'), timeout=timeout) as r:
                text = await r.text()
            data_match = re.search("g_rgProfileData = (?P<json>{.*?});[ \t\r]*\n", text)

            if data_match:
                data = json.loads(data_match.group('json'))
                return int(data['steamid'])
        # group profiles
        else:
            async with session.get(match.group('clean_url'), timeout=timeout) as r:
                text = await r.text()
            data_match = re.search(r"'steam://friends/joinchat/(?P<steamid>\d+)'", text)

            if data_match:
                return int(data_match.group('steamid'))
    except aiohttp.InvalidURL:
        return None


async def from_url(url, timeout=30):
    """Takes Steam community url and returns a SteamID instance or ``None``.
    See :func:`steam64_from_url` for details.

    Parameters
    ----------
    url: :class:`str`
        The Steam community url.
    timeout: :class:`int`
        How long to wait for the http request before turning ``None``.

    Returns
    -------
    SteamID: Optional[:class:`SteamID`]
        `SteamID` instance or ``None``.
    """

    steam64 = steam64_from_url(url, timeout)

    if steam64:
        return SteamID(steam64)

    return None


SteamID.from_url = staticmethod(from_url)


async def mini_profile(user_id):
    """Formats a users mini profile from
    ``steamcommunity.com/miniprofile/ID/json``.

    .. note::
        Each call makes a http request to steamcommunity.com.

    Parameters
    ----------
    user_id: Union[:class:`int`, :class:`str`]
        The ID to search for. For accepted IDs see :meth:`make_steam64`.

    Returns
    -------
    Optional[:class:`dict`]
        The user's miniprofile or ``None`` if no profile
        is found or its a private account.
    """
    async with aiohttp.ClientSession() as session:
        post = await session.get(
            url=f'https://steamcommunity.com/miniprofile/{SteamID(user_id).id}/json'
        )
        resp = await post.json()
        return resp if resp['persona_name'] else None
