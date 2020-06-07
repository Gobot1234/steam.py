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

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Union

from .game import Game

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

    from .abc import BaseUser
    from .group import Group
    from .state import ConnectionState


__all__ = (
    'Ban',
    'Badge',
    'Invite',
    'Comment',
    'UserBadges',
)


class URL:
    API = 'https://api.steampowered.com'
    COMMUNITY = 'https://steamcommunity.com'
    STORE = 'https://store.steampowered.com'


class Comment:
    """Represents a comment on a Steam profile.

    Attributes
    -----------
    id: :class:`int`
        The comment's id.
    content: :class:`str`
        The comment's content.
    author: :class:`~steam.User`
        The author of the comment.
    created_at: :class:`datetime.datetime`
        The time the comment was posted at.
    owner: Union[:class:`~steam.Group`, :class:`~steam.User`]
        The comment sections owner. If the comment section is for a group
        it will be a :class:`~steam.Group` instance otherwise it
        will be an `~steam.User` instance.
    """

    __slots__ = ('content', 'id', 'created_at', 'author', 'owner', '_state')

    def __init__(self, state: 'ConnectionState',
                 id: int, content: str, timestamp: datetime,
                 author: 'BaseUser', owner: Union['Group', 'BaseUser']):
        self._state = state
        self.content = content
        self.id = id
        self.created_at = timestamp
        self.author = author
        self.owner = owner

    def __repr__(self):
        attrs = (
            'id', 'author'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f"<Comment {' '.join(resolved)}>"

    async def report(self) -> None:
        """|coro|
        Reports the :class:`Comment`.
        """
        from .user import BaseUser

        await self._state.http.report_comment(
            id64=self.owner.id64, comment_id=self.id,
            comment_type='Profile' if isinstance(self.owner, BaseUser) else 'Clan',
        )

    async def delete(self) -> None:
        """|coro|
        Deletes the :class:`Comment`.
        """
        from .abc import BaseUser

        await self._state.http.delete_comment(
            id64=self.owner.id64, comment_id=self.id,
            comment_type='Profile' if isinstance(self.owner, BaseUser) else 'Clan',
        )


class Invite:
    """Represents a invite from a Steam user.

    Attributes
    -----------
    type: :class:`str`
        The type of invite either 'Profile'
        or 'Clan'.
    invitee: :class:`~steam.User`
        The user who sent the invite. For type
        'Profile', this is the user you would end up adding.
    group: Optional[:class:`~steam.Group`]
        The group the invite pertains to,
        only relevant if type is 'Clan'.
    """

    __slots__ = ('type', 'group', 'invitee', '_data', '_state')

    def __init__(self, state: 'ConnectionState', data: 'BeautifulSoup.Tag'):
        self._state = state
        self._data = str(data)

    async def __ainit__(self) -> None:
        search = re.search(r"href=\"javascript:OpenGroupChat\( '(\d+)' \)\"", self._data)
        invitee_id = re.search(r'data-miniprofile="(\d+)"', self._data)
        client = self._state.client

        self.type = 'Clan' if search is not None else 'Profile'
        self.invitee = await client.fetch_user(invitee_id.group(1))
        self.group = await client.fetch_group(search.group(1)) if self.type == 'Clan' else None

    def __repr__(self):
        attrs = (
            'type', 'invitee', 'group'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f"<Invite {' '.join(resolved)}>"

    async def accept(self) -> None:
        """|coro|
        Accepts the invite request.
        """
        if self.type == 'Profile':
            await self._state.http.accept_user_invite(self.invitee.id64)
        else:
            await self._state.http.accept_group_invite(self.group.id64)

    async def decline(self) -> None:
        """|coro|
        Declines the invite request.
        """
        if self.type == 'Profile':
            await self._state.http.decline_user_invite(self.invitee.id64)
        else:
            await self._state.http.decline_group_invite(self.group.id64)


class Ban:
    """Represents a Steam ban.

    Attributes
    -----------
    since_last_ban: :class:`datetime.timedelta`
        How many days since the user was last banned
    number_of_game_bans: :class:`int`
        The number of game bans the User has.
    """

    __slots__ = ('since_last_ban', 'number_of_game_bans', '_vac_banned', '_community_banned', '_market_banned')

    def __init__(self, data: dict):
        self._vac_banned = data['VACBanned']
        self._community_banned = data['CommunityBanned']
        self._market_banned = data['EconomyBan']
        self.since_last_ban = timedelta(days=data['DaysSinceLastBan'])
        self.number_of_game_bans = data['NumberOfGameBans']

    def __repr__(self):
        attrs = [
            ('is_banned', self.is_banned()),
            ('is_vac_banned', self.is_vac_banned())
        ]
        resolved = [f'{method}={value!r}' for method, value in attrs]
        return f'<Ban {" ".join(resolved)}>'

    def is_banned(self) -> bool:
        """:class:`bool`: Species if the user is banned from any part of Steam."""
        return True in (self.is_vac_banned(), self.is_community_banned(), self.is_market_banned())

    def is_vac_banned(self) -> bool:
        """:class:`bool`: Species if the user is VAC banned."""
        return self._vac_banned

    def is_community_banned(self) -> bool:
        """:class:`bool`: Species if the user is community banned."""
        return self._community_banned

    def is_market_banned(self) -> bool:
        """:class:`bool`: Species if the user is market banned."""
        return self._market_banned


class Badge:
    """Represents a Steam badge.

    Attributes
    ----------
    id: :class:`int`
        The badge's ID.
    level: :class:`int`
        The badge's level.
    xp: :class:`int`
        The badges's XP.
    completion_time: :class:`datetime.datetime`
        The time the badge was completed at.
    scarcity: :class:`int`
        The scarcity of the badge.
    game: Optional[:class:`~steam.Game`]
        The game associated with the badge.
    """

    __slots__ = ('id', 'xp', 'game', 'level', 'scarcity', 'completion_time')

    def __init__(self, data: dict):
        self.id = data['badgeid']
        self.level = data['level']
        self.xp = data['xp']
        self.completion_time = datetime.utcfromtimestamp(data['completion_time'])
        self.scarcity = data['scarcity']
        self.game = Game(data['appid']) if 'appid' in data else None

    def __repr__(self):
        attrs = (
            'id', 'level', 'xp', 'game'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f'<Badge {" ".join(resolved)}>'


class UserBadges:
    """Represents a Steam :class:`~steam.User`'s badges/level.

    Attributes
    ----------
    level: :class:`int`
        The badge's level.
    xp: :class:`int`
        The badges's XP.
    xp_needed_to_level_up: :class:`int`
        The amount of XP the user needs to level up.
    xp_needed_for_current_level: :class:`int`
        The amount of XP the user's current level requires
        to achieve.
    badges: List[:class:`Badge`]
        A list of the user's badges.
    """

    __slots__ = ('xp', 'level', 'badges', 'xp_needed_to_level_up', 'xp_needed_for_current_level')

    def __init__(self, data: dict):
        self.level = data['player_level']
        self.xp = data['player_xp']
        self.xp_needed_to_level_up = data['player_xp_needed_to_level_up']
        self.xp_needed_for_current_level = data['player_xp_needed_current_level']
        self.badges = [Badge(data) for data in data['badges']]

    def __repr__(self):
        attrs = (
            'level', 'xp'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f'<UserBadges {" ".join(resolved)}>'

    def __len__(self):
        return len(self.badges)
