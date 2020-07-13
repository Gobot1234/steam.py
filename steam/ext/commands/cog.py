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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .command import Command

if TYPE_CHECKING:
    from steam.ext import commands

    from ...client import EventType
    from .bot import Bot
    from .context import Context

__all__ = ("Cog",)


class InjectedListener:
    """Injects the cog's "self" parameter into every event call
    auto-magically.
    """

    __slots__ = ("func", "cog")

    def __init__(self, cog: "Cog", func: "EventType"):
        self.func = func
        self.cog = cog

    def __call__(self, *args, **kwargs):
        return self.func(self.cog, *args, **kwargs)


# for a bit of type hinting
class ExtensionType(ModuleType):
    @staticmethod
    def setup(bot: "Bot"):
        pass

    @staticmethod
    def teardown(bot: "Bot"):
        pass


class Cog:
    """A class from which Cogs can be created.
    These are used to separate commands and listeners into separate files.

    Attributes
    ----------
    qualified_name: :class:`str`
        The name of the cog. Can be set in subclass e.g. ::

            MyCog(commands.Cog, name='SpecialCogName'):
                pass

        Defaults to ``MyCog.__name__``.

    command_attrs: :class:`Dict[str, Any]`
        Attributes to pass to every command registered in the cog.
        Can be set in subclass e.g. ::

            MyBrokenCog(commands.Cog, command_attrs=dict(enabled=False)):
                # all the commands would now be disabled
    """

    __commands__: Dict[str, Command] = dict()
    __listeners__: Dict[str, List["EventType"]] = dict()
    command_attrs: Dict[str, Any]
    qualified_name: str

    def __init_subclass__(cls, *args, **kwargs):
        cls.qualified_name = kwargs.get("name") or cls.__name__
        cls.command_attrs = kwargs.get("command_attrs", dict())
        for name, attr in inspect.getmembers(cls):
            if isinstance(attr, Command):
                cls.__commands__[name] = attr

    @property
    def description(self) -> Optional[str]:
        """Optional[:class:`str`]: The cleaned up docstring for the class"""
        help_doc = self.__doc__
        if help_doc is not None:
            help_doc = inspect.cleandoc(help_doc)
        else:
            help_doc = inspect.getdoc(self)
            if isinstance(help_doc, bytes):
                help_doc = help_doc.decode("utf-8")

        return help_doc

    @classmethod
    def listener(cls, name: str = None):
        """Register a function as a listener.
        Similar to :meth:`~steam.ext.commands.Bot.listen`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for.
            Defaults to ``func.__name__``.
        """

        def decorator(func: "EventType"):
            name_ = name or func.__name__
            if not asyncio.iscoroutinefunction(func):
                raise TypeError(f"listeners must be coroutines, {name_} is {type(func).__name__}")

            if name_ in cls.__listeners__:
                cls.__listeners__[name_].append(func)
            else:
                cls.__listeners__[name_] = [func]

        return decorator

    async def cog_command_error(self, ctx: "commands.Context", error: Exception):
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
        print(f"Ignoring exception in command {ctx.command.name}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def cog_check(self, ctx: "commands.Context"):
        """|coro|
        A special method that registers as a :func:`commands.check`
        for every command and subcommand in this cog.
        This should return a boolean result.

        Parameters
        -----------
        ctx: :class:`~commands.Context`
            The invocation context.

        Returns
        -------
        :class:`bool`
        """
        return True

    def cog_unload(self):
        """A special method that is called when the cog gets removed.

        This is called before :func:`teardown`.
        """

    def _inject(self, bot: "Bot"):
        for command in self.__commands__.values():
            for (name, value) in self.command_attrs.items():
                setattr(command, name, value)
            command.cog = self
            command.checks.append(self.cog_check)
            bot.add_command(command)

        for (name, listeners) in self.__listeners__.items():
            for listener in listeners:
                if not isinstance(listener, staticmethod):
                    # we need to manually inject the "self" parameter then
                    listener = InjectedListener(self, listener)
                bot.add_listener(listener, name)

    def _eject(self, bot: "Bot"):
        self.cog_unload()
        for command in self.__commands__.values():
            bot.remove_command(command)

        for (name, listener) in self.__listeners__.items():
            bot.remove_listener(listener, name)
