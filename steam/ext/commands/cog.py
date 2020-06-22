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

import asyncio
import inspect
import sys
import traceback
from types import ModuleType
from typing import TYPE_CHECKING, Dict, List

from .command import Command

if TYPE_CHECKING:
    from steam.ext import commands
    from ...client import event_type
    from .context import Context
    from .bot import Bot

__all__ = (
    'Cog',
)


# for a bit of type hinting
class ExtensionType(ModuleType):
    @staticmethod
    def setup(bot: 'Bot'):
        pass

    @staticmethod
    def teardown(bot: 'Bot'):
        pass


class Cog:
    """A class from which Cogs can be created.
    These are used to separate commands and listeners into separate files.
    """

    __commands__: Dict[str, Command] = dict()
    __listeners__: Dict[str, List['event_type']] = dict()

    def __init_subclass__(cls, *args, **kwargs):
        for name, attr in inspect.getmembers(cls):
            if isinstance(attr, Command):
                cls.__commands__[name] = attr

    @classmethod
    def listener(cls, name: str = None):
        """Register a function as a listener.
        Similar to :meth:`~steam.ext.commands.Bot.listen`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for.
            Will default to ``func.__name__``.
        """
        def decorator(func: 'event_type'):
            if not asyncio.iscoroutinefunction(func):
                raise TypeError('listeners must be coroutines')

            name_ = name or func.__name__
            if name in cls.__listeners__:
                cls.__listeners__[name_].append(func)
            else:
                cls.__listeners__[name_] = [func]
        return decorator

    async def cog_command_error(self, ctx: 'commands.Context', error: Exception):
        """|coro|
        A special method that is called whenever an error
        is dispatched inside this cog. This is similar to
        :func:`~commands.Bot.on_command_error` except only applying
        to the commands inside this cog.

        Parameters
        -----------
        ctx: :class:`~steam.ext.commands.Context`
            The invocation context where the error happened.
        error: :exc:`Exception`
            The error that happened.
        """
        print(f'Ignoring exception in command {ctx.command.name}:', file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    def cog_unload(self):
        """A special method that is called when the cog gets removed.

        This is called before :func:`teardown`.
        """

    def _inject(self, bot: 'Bot'):
        for command in self.__commands__.values():
            command.cog = self
            bot.add_command(command)

        for (name, listener) in self.__listeners__.items():
            bot.add_listener(listener, name)

    def _eject(self, bot: 'Bot'):
        self.cog_unload()
        for command in self.__commands__.values():
            bot.remove_command(command)

        for (name, listener) in self.__listeners__.items():
            bot.remove_listener(listener, name)
