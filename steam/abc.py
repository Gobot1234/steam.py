# -*- coding: utf-8 -*-

"""
MIT License

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

Loosely based on
https://github.com/Rapptz/discord.py/blob/master/discord/abc.py
"""

import abc
from datetime import datetime

from . import errors
from .enums import *
from .models import URL, Game, CommentsIterator
from .trade import Inventory


class BaseUser(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam user.
    The following implement this ABC:
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
    __slots__ = ('name', 'real_name', 'avatar_url', 'community_url', 'created_at', 'trade_url',
                 'last_logoff', 'state', 'game', 'flags', 'country', 'steam_id', 'id',
                 'id64', 'id2', 'id3', '_state', '_data', '__weakref__')

    def __init__(self, state, data):
        self._state = state
        self._update(data)

    def __repr__(self):
        attrs = (
            'name', 'steam_id', 'state'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<User {' '.join(resolved)}>"

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return isinstance(other, BaseUser) and self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    def _update(self, data):
        from .user import SteamID

        self._data = data
        self.steam_id = SteamID(data['steamid'])
        self.id = self.steam_id.id
        self.id64 = self.steam_id.as_64
        self.id2 = self.steam_id.as_steam2
        self.id3 = self.steam_id.as_steam3
        self.name = data['personaname']
        self.real_name = data.get('realname')
        self.avatar_url = data.get('avatarfull')
        self.community_url = data['profileurl']
        self.trade_url = f'{URL.COMMUNITY}/tradeoffer/new/?partner={self.id}'

        self.country = data.get('loccountrycode')
        self.created_at = datetime.utcfromtimestamp(data['timecreated']) if 'timecreated' in data else None
        # steam is dumb I have no clue why this sometimes isn't given sometimes
        self.last_logoff = datetime.utcfromtimestamp(data['lastlogoff']) if 'lastlogoff' in data else None
        self.state = EPersonaState(data.get('personastate', 0))
        self.flags = EPersonaStateFlag(data.get('personastateflags', 0))
        self.game = Game(title=data['gameextrainfo'], app_id=int(data['gameid']), is_steam_game=False) \
            if 'gameextrainfo' and 'gameid' in data else None
        # setting is_steam_game to False allows for fake game instances to be better without having them pre-defined
        # without making the defined ones being

    async def comment(self, comment: str):
        """|coro|
        Post a comment to an :class:`User`'s profile.

        Parameters
        -----------
        comment: :class:`str`
            The comment to add the :class:`User`'s profile.
        """
        if self.is_commentable():
            if len(comment) < 1000:
                return await self._state.http.post_comment(self.id64, comment)
            raise errors.Forbidden('Comment message is too large post')
        raise errors.Forbidden("We cannot post on this user's profile")

    async def fetch_inventory(self, game: Game):
        """|coro|
        Fetch an :class:`User`'s class:`~steam.trade.Inventory` for trading.

        Parameters
        -----------
        game: :class:`~steam.Game`
            The game to fetch the inventory for.

        Returns
        -------
        Inventory: :class:`Inventory`
        """
        resp = await self._state.http.fetch_user_inventory(self.id64, game.app_id, game.context_id)
        return Inventory(state=self._state, data=resp, owner=self)

    async def fetch_games(self):
        data = await self._state.http.fetch_user_games(self.id64)

    def is_commentable(self):
        """:class:`bool`: Specifies if the user's account is able to be commented on."""
        return bool(self._data.get('commentpermission'))

    def is_private(self):
        """:class:`bool`: Specifies if the user has a public profile."""
        state = self._data.get('communityvisibilitystate', 0)
        return state in {0, 1, 2}

    def has_setup_profile(self):
        """:class:`bool`: Specifies if the user has a setup their profile."""
        return bool(self._data.get('profilestate'))

    def comments(self, limit=None, before: datetime = None, after: datetime = None):
        """An iterator for accessing a :class:`~steam.User`'s :class:`~steam.Comment`s.

        Examples
        -----------

        Usage
        ~~~~~~~~~~
        .. code-block:: python3
            async for comment in user.comments(limit=10):
                print('Author:', comment.author, 'Said:', comment.content)

        Flattening into a list:
        ~~~~~~~~~
        .. code-block:: python3
            comments = await user.comments(limit=50).flatten()
            # comments is now a list of Comment

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


class Messageable(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Steam message.
    The following implement this ABC:
        - :class:`~steam.User`
        - :class:`~steam.Message`
    """

    __slots__ = ()

    async def send(self, content: str):
        """|coro|
        Send a message to a certain destination.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.

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
