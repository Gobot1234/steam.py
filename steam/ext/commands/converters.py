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

from typing import TYPE_CHECKING, Any

from ... import utils
from ...game import Game
from .errors import BadArgument

if TYPE_CHECKING:
    from steam.ext import commands
    from ...clan import Clan
    from ...group import Group
    from ...user import User
    from .context import Context

__all__ = (
    'Converter',
    'Default',
    'Author',
    'DefaultClan',
    'DefaultGroup',
    'DefaultGame',
)


class Converter:
    async def convert(self, ctx: 'commands.Context', param: str):
        raise NotImplementedError('Derived classes must implement this')

    def __repr__(self):
        return f'{self.__class__.__name__.rstrip("Converter")}'


class UserConverter(Converter):
    async def convert(self, ctx: 'commands.Context', param: str) -> 'User':
        user = ctx.bot.get_user(param) or await ctx.bot.fetch_user(param)
        if user is None:
            user = utils.get(ctx.bot.users, name=param)
        if user is None:
            raise BadArgument(f'Failed to convert "{param}" to a Steam user')
        return user


class ClanConverter(Converter):
    async def convert(self, ctx: 'commands.Context', param: str) -> 'Clan':
        clan = ctx.bot.get_clan(param)
        if clan is None:
            clan = utils.get(ctx.bot.clans, name=param)
        if clan is None:
            raise BadArgument(f'Failed to convert "{param}" to a Steam clan')
        return clan


class GroupConverter(Converter):
    async def convert(self, ctx: 'commands.Context', param: str) -> 'Group':
        if param.isdigit():
            group = ctx.bot.get_group(int(param))
        else:
            group = utils.get(ctx.bot.clans, name=param)
        if group is None:
            raise BadArgument(f'Failed to convert "{param}" to a Steam group')
        return group


class GameConverter(Converter):
    async def convert(self, ctx: 'commands.Context', param: str):
        return Game(app_id=int(param)) if param.isdigit() else Game(title=param)


class Default:
    async def default(self, ctx: 'commands.Context'):
        raise NotImplementedError('derived classes need to implement this')


class Author(Default):
    async def default(self, ctx: 'commands.Context'):
        return ctx.author


class DefaultGroup(Default):
    async def default(self, ctx: 'commands.Context'):
        return ctx.group


class DefaultClan(Default):
    async def default(self, ctx: 'commands.Context'):
        return ctx.clan


class DefaultGame(Default):
    async def default(self, ctx: 'commands.Context'):
        return ctx.author.game
