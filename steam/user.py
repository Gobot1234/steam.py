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
import re

import aiohttp

from . import errors
from .abc import BaseUser, Messageable
from .enums import EType, EUniverse, EInstanceFlag, ETypeChar

ETypeChars = ''.join(ETypeChar.__members__.keys())


class SteamID(int):
    """Convert a Steam ID to its various representations."""

    def __new__(cls, *args, **kwargs):
        steam64 = make_steam64(*args, **kwargs)
        return super(SteamID, cls).__new__(cls, steam64)

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.EType = EType  #: reference to EType
        self.EUniverse = EUniverse  #: reference to EUniverse
        self.EInstanceFlag = EInstanceFlag  #: reference to EInstanceFlag

    def __repr__(self):
        return "<id={0.id}, type={1}, universe={2}, instance={0.instance}>".format(
            self,
            repr(self.type.name),
            repr(self.universe.name),
        )

    @property
    def id(self):
        """
        Returns
        -------
        account id: :class:`int`
        """
        return int(self) & 0xFFffFFff

    @property
    def instance(self):
        """
        Returns
        -------
        instance: :class:`int`
        """
        return (int(self) >> 32) & 0xFFffF

    @property
    def type(self):
        """
        Returns
        -------
        type: :class:`~steam.enum.EType`
        """
        return EType((int(self) >> 52) & 0xF)

    @property
    def universe(self):
        """
        Returns
        -------
        :class:`~steam.enum.EUniverse`
        """
        return EUniverse((int(self) >> 56) & 0xFF)

    @property
    def as_32(self):
        """
        Returns
        -------
        account id: :class:`int`
        """
        return self.id

    @property
    def as_64(self):
        """
        Returns
        -------
        steam64: :class:`int`
        """
        return int(self)

    @property
    def as_steam2(self):
        """
        Returns
        -------
        steam2: :class:`str`
            e.g ``STEAM_1:0:1234``.

        .. note::
            ``STEAM_X:Y:Z``. The value of ``X`` should represent the universe, or ``1``
            for ``Public``. However, there was a bug in GoldSrc and Orange Box games
            and ``X`` was ``0``. If you need that format use :attr:`SteamID.as_steam2_zero`
        """
        return f'STEAM_{int(self.universe)}:{self.id % 2}:{self.id >> 1}'

    @property
    def as_steam2_zero(self):
        """
        For GoldSrc and Orange Box games.
        See :attr:`SteamID.as_steam2`.

        Returns
        -------
        steam2: :class:`str`
            e.g ``STEAM_0:0:1234``.
        """
        return self.as_steam2.replace('_1', '_0')

    @property
    def as_steam3(self):
        """
        Returns
        -------
        steam3: :class:`str`
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
        """
        Returns
        -------
        url: :class:`str`
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
        """
        Check whether this SteamID is valid
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


class ClientUser(BaseUser):
    '''__slots__ = (
        '_name', '_avatar_url', '_level', '_steam_id', 'avatar_url', 'status',
        'profile_url', 'id64', 'id2', 'id3', '_state'
    )'''

    def __init__(self, state, data: dict):
        self._state = state
        self._update(data)

    def __repr__(self):
        return "<name='{0.name}' steam_id={0.steam_id!r} level={0.level}>".format(self)

    def __str__(self):
        return self.name

    def _update(self, data):
        self._name = data['persona_name']
        self._avatar_url = data['avatar_url']
        self._level = data['level']
        self._steam_id = self._state.http._steam_id

    @property
    def name(self):
        return self._name

    @property
    def level(self):
        return self._level

    @property
    def avatar_url(self):
        return self._avatar_url

    @property
    def id64(self):
        return self._steam_id.as_64

    @property
    def id2(self):
        return self._steam_id.as_steam2

    @property
    def id3(self):
        return self._steam_id.as_steam3

    @property
    def steam_id(self):
        return self._steam_id


class User(Messageable, BaseUser):
    '''__slots__ = (
        '_name', '_avatar_url', '_level', '_steam_id', 'avatar_url', 'status',
        'profile_url', 'id64', 'id2', 'id3', '_state'
    )'''

    def __init__(self, state, data: dict):
        self._state = state
        self._update(data)

    def __repr__(self):
        return "<name='{0.name}' steam_id={0.steam_id!r} level={0.level}>".format(self)

    def __str__(self):
        return self.name

    def _update(self, data):
        self._name = data['persona_name']
        self._avatar_url = data['avatar_url']
        self._level = data['level']
        self._steam_id = SteamID(data['id64'])

    @property
    def name(self):
        return self._name

    @property
    def level(self):
        return self._level

    @property
    def avatar_url(self):
        return self._avatar_url

    @property
    def id64(self):
        return self.steam_id.as_64

    @property
    def id2(self):
        return self._steam_id.as_steam2

    @property
    def id3(self):
        return self._steam_id.as_steam3

    @property
    def steam_id(self):
        return self._steam_id

    async def is_friend(self):
        """|coro|"""
        pass

    async def add(self):
        """|coro|"""
        request = await self._state.http.add_user(self)
        resp = await request.json()
        if not resp:
            raise errors.Forbidden('Adding the user failed')

    async def remove(self):
        """|coro|"""
        request = await self._state.http.remove_user(self)
        resp = await request.json()
        if not resp:
            raise errors.Forbidden('Removing the user failed')

    async def unblock(self):
        """|coro|"""
        request = await self._state.http.unblock_user(self)
        resp = await request.json()
        if not resp:
            raise errors.Forbidden('Unblocking the user failed')

    async def block(self):
        """|coro|"""
        request = await self._state.http.block_user(self)
        resp = await request.json()
        if not resp:
            raise errors.Forbidden('Blocking the user failed')

    async def accept_invite(self):
        """|coro|"""
        request = await self._state.http.accept_user_invite(self)
        resp = await request.json()
        if not resp:
            raise errors.Forbidden("Accepting the user's invite failed")

    async def decline_invite(self):
        """|coro|"""
        request = await self._state.http.decline_user_invite(self)
        resp = await request.json()
        if not resp:
            raise errors.Forbidden("Declining the user's invite failed")


def make_steam64(_id=0, *args, **kwargs):
    """Returns steam64 from various other representations.
    .. code:: python
        make_steam64()  # invalid steamid
        make_steam64(12345)  # accountid
        make_steam64('12345')
        make_steam64(id=12345, type='Invalid', universe='Invalid', instance=0)
        make_steam64(103582791429521412)  # steam64
        make_steam64('103582791429521412')
        make_steam64('STEAM_1:0:2')  # steam2
        make_steam64('[g:1:4]')  # steam3

    Raises
    ------
    TypeError: Too many arguments have been given.

    Returns
    -------
    id64: :class:`int`
    """

    account_id = _id
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
            raise TypeError(f'Takes at most 4 arguments ({length} given)')

    if len(kwargs) > 0:
        etype = kwargs.get('type', etype)
        universe = kwargs.get('universe', universe)
        instance = kwargs.get('instance', instance)

    etype = (
        EType(etype)
        if isinstance(etype, (int, EType))
        else EType[etype]
    )

    universe = (
        EUniverse(universe)
        if isinstance(universe, (int, EUniverse))
        else EUniverse[universe]
    )

    if instance is None:
        instance = 1 if etype in (EType.Individual, EType.GameServer) else 0

    assert instance <= 0xffffF, "instance larger than 20bits"

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
        Each call makes a http request to ``steamcommunity.com``
    .. note::
        For a reliable resolving of vanity urls use ``ISteamUser.ResolveVanityURL`` web api

    Parameters
    ----------
    url: :class:`str`
        The Steam community url.
    timeout: :class:`int`
        How long to wait on http request before turning ``None``.

    Returns
    -------
    steam64: Optional[:class:`int`]
        if ``steamcommunity.com`` is down returns ``None``

    Example URLs::
        https://steamcommunity.com/gid/[g:1:4]
        https://steamcommunity.com/gid/103582791429521412
        https://steamcommunity.com/groups/Valve
        https://steamcommunity.com/profiles/[U:1:12]
        https://steamcommunity.com/profiles/76561197960265740
        https://steamcommunity.com/id/johnc
    """

    match = re.match(r'^(?P<clean_url>https?://steamcommunity.com/'
                     r'(?P<type>profiles|id|gid|groups)/(?P<value>.*?))(?:/(?:.*)?)?$', url)

    if not match:
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
    SteamID: Optional[:class:`~steam.SteamID`]
        `SteamID` instance or ``None``.
    """

    steam64 = steam64_from_url(url, timeout)

    if steam64:
        return SteamID(steam64)

    return None


async def profile(user_id):
    """Formats a users mini profile from
    ``steamcommunity.com/miniprofile/ID3/json``.
    .. note::
        Each call makes a http request to ``steamcommunity.com``.

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
            url=f'https://steamcommunity.com/miniprofile/{SteamID(user_id).as_steam3[5:-1]}/json'
        )
        resp = await post.json()
        return resp if resp['persona_name'] else None


SteamID.from_url = staticmethod(from_url)
