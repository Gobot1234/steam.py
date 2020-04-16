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
"""

from __future__ import annotations

import json
import re
from datetime import timedelta, datetime
from typing import List, Optional, Union

import aiohttp

from .abc import BaseUser, Messageable
from .enums import *
from .game import Game
from .group import Group
from .iterators import CommentsIterator, TradesIterator
from .models import URL
from .trade import Item, Inventory, Asset

__all__ = (
    'User',
    'SteamID',
    'from_url',
    'ClientUser',
    'make_steam64',
    'steam64_from_url'
)

ETypeChars = ''.join([type_char.name for type_char in ETypeChar])


class SteamID(int):
    """Convert a Steam ID to its various representations.

    This takes a steam 64 bit account id, however, :meth:`make_steam64`
    is called on this class's initialization.
    """

    EType = EType
    EUniverse = EUniverse
    EInstanceFlag = EInstanceFlag

    def __new__(cls, *args, **kwargs):
        user_id64 = make_steam64(*args, **kwargs)
        return super().__new__(cls, user_id64)

    def __repr__(self):
        attrs = (
            'id', 'type', 'universe', 'instance'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<SteamID {' '.join(resolved)}>"

    @property
    def id(self) -> int:
        """:class:`int`: Represents the account id.
        This is also known as the 32 bit id"""
        return int(self) & 0xFFffFFff

    @property
    def instance(self) -> int:
        """:class:`int`: Returns the instance of the account."""
        return (int(self) >> 32) & 0xFFffF

    @property
    def type(self) -> EType:
        """:class:`~steam.EType`:
        Represents the steam type of the account.
        """
        return EType((int(self) >> 52) & 0xF)

    @property
    def universe(self) -> EUniverse:
        """:class:`~steam.EUniverse`:
        Represents the steam universe of the account.
        """
        return EUniverse((int(self) >> 56) & 0xFF)

    @property
    def as_32(self) -> int:
        """:class:`int`: The account's id.
        An alias to :attr:`SteamID.id`
        """
        return self.id

    @property
    def id64(self) -> int:
        """:class:`int`: The steam 64 bit id of the account.
        Used for community profiles along with other useful things.
        """
        return int(self)

    @property
    def as_64(self) -> int:
        """:class:`int`: The steam 64 bit id of the account.
        Used for community profiles along with other useful things.

        An alias to :attr:`SteamID.id64`
        """
        return self.id64

    @property
    def id2(self) -> str:
        """class:`str`: The steam2 id of the account.
            e.g ``STEAM_1:0:1234``.

        .. note::
            ``STEAM_X:Y:Z``. The value of ``X`` should represent the universe, or ``1``
            for ``Public``. However, there was a bug in GoldSrc and Orange Box games
            and ``X`` was ``0``. If you need that format use :attr:`SteamID.as_steam2_zero`
        """
        return f'STEAM_{int(self.universe)}:{self.id % 2}:{self.id >> 1}'

    @property
    def as_steam2(self) -> str:
        """class:`str`: The steam2 id of the account.
            e.g ``STEAM_1:0:1234``.

        .. note::
            ``STEAM_X:Y:Z``. The value of ``X`` should represent the universe, or ``1``
            for ``Public``. However, there was a bug in GoldSrc and Orange Box games
            and ``X`` was ``0``. If you need that format use :attr:`SteamID.as_steam2_zero`

        An alias to :attr:`SteamID.id2`
        """
        return self.id2

    @property
    def as_steam2_zero(self) -> str:
        """:class:`str`: The steam2 id of the account.
            e.g ``STEAM_0:0:1234``.

        For GoldSrc and Orange Box games.
        See :attr:`SteamID.as_steam2`.
        """
        return self.as_steam2.replace('_1', '_0')

    @property
    def id3(self) -> str:
        """:class:`str`: The steam3 id of the account.
            e.g ``[U:1:1234]``.

        This is used for more recent games.
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
    def as_steam3(self) -> str:
        """:class:`str`: The steam3 id of the account.
            e.g ``[U:1:1234]``.

        This is used for more recent games.
        An alias to :attr:`SteamID.id3`
        """
        return self.id3

    @property
    def community_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The community url of the account
            e.g https://steamcommunity.com/profiles/123456789.
        """
        suffix = {
            EType.Individual: 'profiles',
            EType.Clan: 'gid',
        }
        if self.type in suffix:
            return f'https://steamcommunity.com/{suffix[self.type]}/{self.as_64}'

        return None

    def is_valid(self) -> bool:
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


class _BaseUser(BaseUser):
    __slots__ = ('id', 'id2', 'id3', 'name', 'game', 'id64', 'state', 'flags',
                 'country', 'steam_id', 'trade_url', 'real_name', 'avatar_url',
                 'created_at', 'last_logoff', 'community_url', '_state', '_data')

    def __init__(self, state, data):
        self._state = state
        self._update(data)

    def __repr__(self):
        attrs = (
            'name', 'state', 'steam_id'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<User {' '.join(resolved)}>"

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, _BaseUser) and self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    def _update(self, data):
        self._data = data
        self.steam_id = SteamID(data['steamid'])
        self.id = self.steam_id.id
        self.id64 = self.steam_id.id64
        self.id2 = self.steam_id.id2
        self.id3 = self.steam_id.id3
        self.name = data['personaname']
        self.real_name = data.get('realname')
        self.avatar_url = data.get('avatarfull')
        self.community_url = data['profileurl'][:-1]
        self.trade_url = f'{URL.COMMUNITY}/tradeoffer/new/?partner={self.id}'

        self.country = data.get('loccountrycode')
        self.created_at = datetime.utcfromtimestamp(data['timecreated']) if 'timecreated' in data else None
        # steam is dumb I have no clue why this sometimes isn't given sometimes
        self.last_logoff = datetime.utcfromtimestamp(data['lastlogoff']) if 'lastlogoff' in data else None
        self.state = EPersonaState(data.get('personastate', 0))
        self.flags = EPersonaStateFlag(data.get('personastateflags', 0))
        self.game = Game(title=data['gameextrainfo'], app_id=int(data['gameid'])) if 'gameextrainfo' in data else None
        # setting is_steam_game to False allows for fake game instances to be better without having them pre-defined
        # without making the defined ones being

    async def comment(self, comment: str) -> None:
        """|coro|
        Post a comment to an :class:`User`'s profile.

        Parameters
        -----------
        comment: :class:`str`
            The comment to add the :class:`User`'s profile.
        """
        await self._state.http.post_comment(self.id64, comment)

    async def fetch_inventory(self, game: Game) -> Inventory:
        """|coro|
        Fetch an :class:`User`'s :class:`~steam.Inventory` for trading.

        Parameters
        -----------
        game: :class:`~steam.Game`
            The game to fetch the inventory for.

        Raises
        ------
        :class:`~steam.Forbidden`
            The user's inventory is private.

        Returns
        -------
        :class:`Inventory`
            The inventory.
        """
        resp = await self._state.http.fetch_user_inventory(self.id64, game.app_id, game.context_id)
        return Inventory(state=self._state, data=resp, owner=self)

    async def fetch_friends(self) -> List[User]:
        """|coro|
        Fetch the list of :class:`~steam.User`'s friends from the API.

        Returns
        -------
        List[:class:`~steam.User`]
            The list of :class:`~steam.User`'s friends from the API
        """
        friends = await self._state.http.fetch_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def fetch_games(self) -> List[Game]:
        """|coro|
        Fetches the list of :class:`~steam.Game` objects from the API.

        Returns
        -------
        List[:class:`~steam.Game`]
            The list of :class:`~steam.Game` objects from the API.
        """
        data = await self._state.http.fetch_user_games(self.id64)
        games = data['response'].get('games', [])
        return [Game(0, _data=game) for game in games]

    async def fetch_groups(self) -> List[Group]:
        """|coro|
        Fetches a list of the :class:`User`'s :class:`~steam.Group` objects.

        Returns
        -------
        List[:class:`~steam.Group`]
            The user's groups.
        """
        from .group import Group
        data = await self._state.request('GET', f'https://steamcommunity.com/profiles/{self.id64}/groups')
        ret = []
        group_urls = re.findall(r'<a class="linkTitle" href="(.*?)">', data)
        for group_url in group_urls:
            group = Group(state=self._state, url=group_url)
            await group.__ainit__()
            ret.append(group)
        return ret

    def is_commentable(self) -> bool:
        """:class:`bool`: Specifies if the user's account is able to be commented on."""
        return bool(self._data.get('commentpermission'))

    def is_private(self) -> bool:
        """:class:`bool`: Specifies if the user has a public profile."""
        state = self._data.get('communityvisibilitystate', 0)
        return state in {0, 1, 2}

    def has_setup_profile(self) -> bool:
        """:class:`bool`: Specifies if the user has a setup their profile."""
        return bool(self._data.get('profilestate'))

    def comments(self, limit=None, before: datetime = None, after: datetime = None) -> CommentsIterator:
        """An iterator for accessing a :class:`~steam.User`'s :class:`~steam.Comment` objects.

        Examples
        -----------

        Usage::

            async for comment in user.comments(limit=10):
                print('Author:', comment.author, 'Said:', comment.content)

        Flattening into a list::

            comments = await user.comments(limit=50).flatten()
            # comments is now a list of Comment

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum comments to search through.
            Default is ``None`` which will fetch all the user's comments.
        before: Optional[:class:`datetime.datetime`]
            A time to search for comments before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for comments after.

        Yields
        ---------
        :class:`~steam.Comment`
            The comment with the comment information parsed.
        """
        return CommentsIterator(state=self._state, user_id=self.id64, limit=limit, before=before, after=after)


class User(Messageable, _BaseUser):
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
        The Game instance attached to the user. Is None if the user
        isn't in a game or one that is recognised by the api.
    avatar_url: :class:`str`
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name: Optional[:class:`str`]
        The user's real name defined by them. Could be None.
    created_at: Optional[:class:`datetime.datetime`]
        The time at which the user's account was created. Could be None.
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. Could be None (e.g. if they are currently online).
    country: Optional[:class:`str`]
        The country code of the account. Could be None.
    flags: :class:`~steam.EPersonaStateFlag`
        The persona state flags of the account.
    id64: :class:`int`
        The 64 bit id of the user's account.
    id3: :class:`str`
        The id3 of the user's account. Used for newer steam games.
    id2: :class:`str`
        The id2 of the user's account. Used for older steam games.
    """

    def __init__(self, state, data):
        super().__init__(state, data)

    async def add(self) -> None:
        """|coro|
        Add an :class:`User` to your friends list.
        """
        await self._state.http.add_user(self.id64)

    async def remove(self) -> None:
        """|coro|
        Remove an :class:`User` from your friends list.
        """
        await self._state.http.remove_user(self.id64)

    async def unblock(self) -> None:
        """|coro|
        Unblock an :class:`User`.
        """
        await self._state.http.unblock_user(self.id64)

    async def block(self) -> None:
        """|coro|
        Block an :class:`User`.
        """
        await self._state.http.block_user(self.id64)

    async def accept_invite(self) -> None:
        """|coro|
        Accept a friend invite from an :class:`User`.
        """
        return await self._state.http.accept_user_invite(self.id64)

    async def decline_invite(self) -> None:
        """|coro|
        Decline a friend invite from an :class:`User`.
        """
        await self._state.http.decline_user_invite(self.id64)

    async def send_trade(self, items_to_send: Union[List[Item], List[Asset]] = None,
                         items_to_receive: Union[List[Item], List[Asset]] = None, *,
                         message: str = None) -> None:
        """|coro|
        Sends a trade offer to an :class:`User`.

        Parameters
        -----------
        items_to_send: Optional[Union[List[:class:`steam.Item`], List[:class:`steam.Asset`]]
            The items you are sending to the other user.
        items_to_receive: Optional[Union[List[:class:`steam.Item`], List[:class:`steam.Asset`]]
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
        message = message if message is not None else ''
        resp = await self._state.http.send_trade_offer(self.id64, self.id, items_to_send, items_to_receive, message)
        if resp.get('needs_mobile_confirmation', False):
            confirmation = await self._state.confirmation_manager.get_trade_confirmation(int(resp['tradeofferid']))
            await confirmation.confirm()

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
        days = int(re.search(r'var g_daysTheirEscrow = (\d+);', resp).group(1))
        return timedelta(days=days) if days else None

    def is_friend(self) -> bool:
        """:class:`bool`: Species if the user is in the ClientUser's friends"""
        return self in self._state.client.user.friends

    async def send(self, content: str = None):
        """Send a message to the user

        .. note::
            This does not currently function.

        Returns
        ---------
        :class:`~steam.Message`
            The send message
        """
        return await self._state.send_message(user_id64=self.id64, content=str(content))

    async def invite_to_group(self, group: Group):
        """|coro|
        Invites a :class:`~steam.User` to a :class:`Group`.

        Parameters
        -----------
        group: :class:`~steam.Group`
            The group to invite the user to.
        """
        await self._state.http.invite_user_to_group(self.id64, group.id)


class ClientUser(_BaseUser):
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
    steam_id: :class:`SteamID`
        The SteamID instance attached to the user.
    friends: List[:class:`User`]
        A list of the :class:`ClientUser`'s friends.
    state: :class:`~steam.EPersonaState`
        The current persona state of the account (e.g. LookingToTrade).
    game: Optional[:class:`~steam.Game`]
        The Game instance attached to the user. Is None if the user
        isn't in a game or one that is recognised by the api.
    avatar_url: :class:`str`
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name: Optional[:class:`str`]
        The user's real name defined by them. Could be None.
    created_at: Optional[:class:`datetime.datetime`]
        The time at which the user's account was created. Could be None.
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. Could be None (e.g. if they are currently online).
    country: Optional[:class:`str`]
        The country code of the account. Could be None.
    flags: :class:`~steam.EPersonaStateFlag`
        The persona state flags of the account.
    id64: :class:`int`
        The 64 bit id of the user's account.
    id3: :class:`str`
        The id3 of the user's account. Used for newer steam games.
    id2: :class:`str`
        The id2 of the user's account. Used for older steam games.
    """

    __slots__ = ('friends', 'groups') + _BaseUser.__slots__

    def __init__(self, state, data):
        self.friends = []
        super().__init__(state, data)

    def __repr__(self):
        attrs = (
            'name', 'steam_id', 'state'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<ClientUser {' '.join(resolved)}>"

    async def __ainit__(self):
        await self.fetch_friends()

    async def fetch_friends(self) -> List[User]:
        self.friends = await super().fetch_friends()
        return self.friends

    async def fetch_wallet_balance(self) -> Optional[float]:
        """|coro|
        Fetches the :class:ClientUser`'s current wallet balance.

        Returns
        -------
        Optional[:class:`float`]
            The current wallet balance.
        """
        resp = await self._state.request('GET', f'{URL.STORE}/steamaccount/addfunds')
        search = re.search(r'Wallet <b>\(.(\d*)(?:[.,](\d*)|)\)</b>', resp, re.UNICODE)
        if search is None:
            return None
        if search.group(2):
            return float(f'{search.group(1)}.{search.group(2)}')
        else:
            return float(search.group())

    def trades(self, limit=None, before: datetime = None, after: datetime = None,
               active_only: bool = True, include_sent: bool = True,
               include_received: bool = True) -> TradesIterator:
        """An iterator for accessing a :class:`ClientUser`'s :class:`~steam.TradeOffer` objects.

        Examples
        -----------

        Usage: ::

            async for trade in client.user.trades(limit=10):
                print('Partner:', trade.partner, 'Sent:')
                print(', '.join([item.name if item.name else str(item.asset_id) for item in trade.items_to_receive])
                      if trade.items_to_receive else 'Nothing')

        Flattening into a list: ::

            trades = await client.user.trades(limit=50).flatten()
            # trades is now a list of TradeOffer

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum comments to search through.
            Default is ``None`` which will fetch all the user's comments.
        before: Optional[:class:`datetime.datetime`]
            A time to search for trades before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for trades after.
        active_only: Optional[:class:`bool`]
            The option passed when fetching trades defaults to ``True``.
        include_sent: Optional[:class:`bool`]
            The option passed when fetching trades defaults to ``True``.
        include_received: Optional[:class:`bool`]
            The option passed when fetching trades defaults to ``True``.

        Yields
        ---------
        :class:`~steam.TradeOffer`
        """
        return TradesIterator(state=self._state, limit=limit, before=before, after=after,
                              active_only=active_only, sent=include_sent, received=include_received)


def make_steam64(account_id=0, *args, **kwargs) -> int:
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

    etype = (EType(etype.value if isinstance(etype, EType) else etype)
             if isinstance(etype, (int, EType)) else EType[etype])
    universe = (EUniverse(universe.value if isinstance(universe, EUniverse) else etype)
                if isinstance(universe, (int, EUniverse)) else EUniverse[universe])

    if instance is None:
        instance = 1 if etype in (EType.Individual, EType.GameServer) else 0

    return (universe.value << 56) | (etype.value << 52) | (instance << 32) | account_id


def steam2_to_tuple(value: str):
    """
    Parameters
    ----------
    value: :class:`str`
        steam2 e.g. ``STEAM_1:0:1234``.

    Returns
    -------
    Optional[:class:`tuple`]
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
    Optional[:class:`tuple`]
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
                await session.close()
            data_match = re.search("g_rgProfileData = (?P<json>{.*?});\s*", text)

            if data_match:
                data = json.loads(data_match.group('json'))
                return int(data['steamid'])
        # group profiles
        else:
            async with session.get(match.group('clean_url'), timeout=timeout) as r:
                text = await r.text()
                await session.close()
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

    steam64 = await steam64_from_url(url, timeout)

    if steam64:
        return SteamID(steam64)

    return None


SteamID.from_url = classmethod(from_url)