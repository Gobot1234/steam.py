# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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

This contains a copy of
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
"""

import abc
import asyncio
import re
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from .enums import (
    EInstanceFlag,
    EPersonaState,
    EPersonaStateFlag,
    EType,
    ETypeChar,
    EUniverse
)
from .errors import HTTPException
from .game import Game
from .iterators import CommentsIterator
from .models import URL, Ban, Comment, UserBadges
from .trade import Inventory
from .utils import make_steam64, steam64_from_url

if TYPE_CHECKING:
    from .user import User
    from .group import Group
    from .state import ConnectionState
    from .image import Image


__all__ = (
    'SteamID',
)

_ICODE_HEX = "0123456789abcdef"
_ICODE_CUSTOM = "bcdfghjkmnpqrtvw"
_ICODE_VALID = f'{_ICODE_HEX}{_ICODE_CUSTOM}'
_ICODE_MAPPING = dict(zip(_ICODE_HEX, _ICODE_CUSTOM))
_ICODE_INVERSE_MAPPING = dict(zip(_ICODE_CUSTOM, _ICODE_HEX))


class SteamID(metaclass=abc.ABCMeta):
    """Convert a Steam ID between its various representations."""

    __slots__ = ('_BASE', '__weakref__')

    def __init__(self, *args, **kwargs):
        self._BASE = make_steam64(*args, **kwargs)

    def __repr__(self):
        attrs = (
            'id', 'type', 'universe', 'instance'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<SteamID {' '.join(resolved)}>"

    def __int__(self):
        # the reason I moved away from a direct implementation of this
        # is due to not being able to use __slots__ for an int subclass
        # this is currently the best implementation I can think of
        return self._BASE

    def __bool__(self):
        return bool(self._BASE)

    def __str__(self):
        return str(self._BASE)

    def __hash__(self):
        return hash(self._BASE)

    def __eq__(self, other):
        return self._BASE == other

    @property
    def id(self) -> int:
        """:class:`int`: Represents the account id.
        This is also known as the 32 bit id.
        """
        return int(self) & 0xFFffFFff

    @property
    def instance(self) -> int:
        """:class:`int`: Returns the instance of the account."""
        return (int(self) >> 32) & 0xFFffF

    @property
    def type(self) -> EType:
        """:class:`~steam.EType`: Represents the Steam type of the account."""
        return EType((int(self) >> 52) & 0xF)

    @property
    def universe(self) -> EUniverse:
        """:class:`~steam.EUniverse`: Represents the Steam universe of the account."""
        return EUniverse((int(self) >> 56) & 0xFF)

    @property
    def as_32(self) -> int:
        """:class:`int`: The account's id.
        An alias to :attr:`SteamID.id`.
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
        An alias to :attr:`SteamID.id64`.
        """
        return self.id64

    @property
    def id2(self) -> str:
        """class:`str`: The Steam2 id of the account.
            e.g ``STEAM_1:0:1234``.

        .. note::
            ``STEAM_X:Y:Z``. The value of ``X`` should represent the universe, or ``1``
            for ``Public``. However, there was a bug in GoldSrc and Orange Box games
            and ``X`` was ``0``. If you need that format use :attr:`SteamID.as_steam2_zero`.
        """
        return f'STEAM_{int(self.universe)}:{self.id % 2}:{self.id >> 1}'

    @property
    def as_steam2(self) -> str:
        """class:`str`: The Steam2 id of the account.
            e.g ``STEAM_1:0:1234``.

        .. note::
            ``STEAM_X:Y:Z``. The value of ``X`` should represent the universe, or ``1``
            for ``Public``. However, there was a bug in GoldSrc and Orange Box games
            and ``X`` was ``0``. If you need that format use :attr:`SteamID.as_steam2_zero`.

        An alias to :attr:`SteamID.id2`.
        """
        return self.id2

    @property
    def as_steam2_zero(self) -> str:
        """:class:`str`: The Steam2 id of the account.
            e.g ``STEAM_0:0:1234``.

        For GoldSrc and Orange Box games.
        See :attr:`SteamID.as_steam2`.
        """
        return self.as_steam2.replace('_1', '_0')

    @property
    def id3(self) -> str:
        """:class:`str`: The Steam3 id of the account.
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
        """:class:`str`: The Steam3 id of the account.
        An alias to :attr:`SteamID.id3`.
        """
        return self.id3

    @property
    def invite_code(self) -> Optional[str]:
        """Optional[:class:`str`]: s.team invite code format
            e.g. ``cv-dgb``
        """
        if self.type == EType.Individual and self.is_valid():
            def repl_mapper(x):
                return _ICODE_MAPPING[x.group()]

            invite_code = re.sub(f"[{_ICODE_HEX}]", repl_mapper, f"{self.id:x}")
            split_idx = len(invite_code) // 2

            if split_idx:
                invite_code = f'{invite_code[:split_idx]}-{invite_code[split_idx:]}'

            return invite_code

    @property
    def invite_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The user's full invite code URL.
            e.g ``https://s.team/p/cv-dgb``
        """
        code = self.invite_code
        if code:
            return f'https://s.team/p/{code}'

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
            return f'https://steamcommunity.com/{suffix[self.type]}/{self.id64}'

        return None

    def is_valid(self) -> bool:
        """:class:`bool`: Check whether this SteamID is valid.
        This doesn't however mean that a matching profile can be found.
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

    @classmethod
    async def from_url(cls, url, timeout=30) -> Optional['SteamID']:
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
            return cls(steam64)
        return None


class BaseUser(SteamID, metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam user.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClientUser`

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
        The Game instance attached to the user. Is None if the user
        isn't in a game or one that is recognised by the api.
    primary_group: Optional[:class:`SteamID`]
        The primary group the User displays on their profile.
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
    """

    __slots__ = ('name', 'game', 'state', 'flags', 'country', 'primary_group',
                 'trade_url', 'real_name', 'avatar_url',
                 'created_at', 'last_logoff', '_state', '_data')

    def __init__(self, state: 'ConnectionState', data: dict):
        super().__init__(data['steamid'])
        self._state = state
        self._update(data)

    def __repr__(self):
        attrs = (
            'name', 'state',
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        resolved.append(super().__repr__())
        return f"<User {' '.join(resolved)}>"

    def __str__(self):
        return self.name

    def _update(self, data) -> None:
        self._data = data
        self.name = data['personaname']
        self.real_name = data.get('realname')
        self.avatar_url = data.get('avatarfull')
        self.trade_url = f'{URL.COMMUNITY}/tradeoffer/new/?partner={self.id}'

        self.primary_group = SteamID(data['primaryclanid']) if 'primaryclanid' in data else None
        self.country = data.get('loccountrycode')
        self.created_at = datetime.utcfromtimestamp(data['timecreated']) if 'timecreated' in data else None
        # steam is dumb I have no clue why this sometimes isn't given sometimes
        self.last_logoff = datetime.utcfromtimestamp(data['lastlogoff']) if 'lastlogoff' in data else None
        self.state = EPersonaState(data.get('personastate', 0))
        self.flags = EPersonaStateFlag(data.get('personastateflags', 0))
        self.game = Game(title=data['gameextrainfo'], app_id=int(data['gameid'])) if 'gameextrainfo' in data else None

    async def update(self) -> None:
        data = self._state.http.fetch_user(self.id64)
        self._update(data)

    async def comment(self, content: str) -> Comment:
        """|coro|
        Post a comment to an :class:`User`'s profile.

        Parameters
        -----------
        content: :class:`str`
            The message to add to the user's profile.

        Returns
        -------
        :class:`~steam.Comment`
            The created comment.
        """
        resp = await self._state.http.post_comment(self.id64, 'Profile', content)
        id = int(re.findall(r'id="comment_(\d+)"', resp['comments_html'])[0])
        timestamp = datetime.utcfromtimestamp(resp['timelastpost'])
        return Comment(
            state=self._state, id=id, owner=self,
            timestamp=timestamp, content=content,
            author=self._state.client.user
        )

    async def inventory(self, game: Game) -> Inventory:
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
            The user's inventory.
        """
        resp = await self._state.http.get_user_inventory(self.id64, game.app_id, game.context_id)
        return Inventory(state=self._state, data=resp, owner=self)

    async def fetch_friends(self) -> List['User']:
        """|coro|
        Fetch the list of :class:`~steam.User`'s friends from the API.

        Returns
        -------
        List[:class:`~steam.User`]
            The list of user's friends from the API.
        """
        friends = await self._state.http.get_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def games(self) -> List[Game]:
        """|coro|
        Fetches the list of :class:`~steam.Game`
        objects the :class:`User` owns from the API.

        Returns
        -------
        List[:class:`~steam.Game`]
            The list of game objects from the API.
        """
        data = await self._state.http.get_user_games(self.id64)
        games = data['response'].get('games', [])
        return [Game._from_api(game) for game in games]

    async def groups(self) -> List['Group']:
        """|coro|
        Fetches a list of the :class:`User`'s :class:`~steam.Group`
        objects the :class:`User` is in from the API.

        Returns
        -------
        List[:class:`~steam.Group`]
            The user's groups.
        """
        groups = []

        async def getter(gid):
            try:
                group = await self._state.client.fetch_group(gid)
            except HTTPException:
                await asyncio.sleep(20)
                await getter(gid)
            else:
                groups.append(group)
        resp = await self._state.http.get_user_groups(self.id64)
        for group in resp['response']['groups']:
            await getter(group['gid'])
        return groups

    async def bans(self) -> Ban:
        """|coro|
        Fetches the :class:`User`'s :class:`~steam.Ban` objects.

        Returns
        -------
        :class:`~steam.Ban`
            The user's bans.
        """
        resp = await self._state.http.get_user_bans(self.id64)
        resp = resp['players'][0]
        resp['EconomyBan'] = False if resp['EconomyBan'] == 'none' else True
        return Ban(data=resp)

    async def badges(self) -> UserBadges:
        """|coro|
        Fetches the :class:`User`'s :class:`~steam.UserBadges` objects.

        Returns
        -------
        :class:`~steam.UserBadges`
            The user's badges.
        """
        resp = await self._state.http.get_user_badges(self.id64)
        return UserBadges(data=resp['response'])

    async def level(self) -> int:
        """|coro|
        Fetches the :class:`User`'s level.

        Returns
        -------
        :class:`int`
            The user's level.
        """
        resp = await self._state.http.get_user_level(self.id64)
        return resp['response']['player_level']

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

    async def is_banned(self) -> bool:
        """|coro|
        Specifies if the user is banned from any part of Steam.

        Returns
        -------
        :class:`bool`
            Whether or not the user is banned.

        This is equivalent to::

            bans = await user.bans()
            bans.is_banned()
        """
        bans = await self.bans()
        return bans.is_banned()

    def comments(self, limit: Optional[int] = None,
                 before: datetime = None, after: datetime = None) -> CommentsIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a
        :class:`~steam.User`'s :class:`~steam.Comment` objects.

        Examples
        -----------

        Usage: ::

            async for comment in user.comments(limit=10):
                print('Author:', comment.author, 'Said:', comment.content)

        Flattening into a list: ::

            comments = await user.comments(limit=50).flatten()
            # comments is now a list of Comment

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of comments to search through.
            Default is ``None`` which will fetch the user's entire comments section.
        before: Optional[:class:`datetime.datetime`]
            A time to search for comments before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for comments after.

        Yields
        ---------
        :class:`~steam.Comment`
            The comment with the comment information parsed.
        """
        return CommentsIterator(state=self._state, owner=self, limit=limit, before=before, after=after)


class BaseChannel(metaclass=abc.ABCMeta):
    pass


class Messageable(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam message.
    The following classes implement this ABC:

        - :class:`~steam.User`
    """

    __slots__ = ()

    async def send(self, content: str = None, image: 'Image' = None):
        """|coro|
        Send a message to a certain destination.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content of the message to send.
        image: Optional[:class:`.Image`]
            The image to send to the user. This doesn't fully work yet.

        Raises
        ------
        ~steam.HTTPException
            Sending the message failed.
        ~steam.Forbidden
            You do not have permission to send the message.

        Returns
        -------
        :class:`~steam.Message`
            The message that was sent.
        """
        # ret = state.create_message(channel=channel, data=data)
        # return ret
        pass
