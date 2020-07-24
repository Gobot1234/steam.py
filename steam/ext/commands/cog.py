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
from typing import TYPE_CHECKING, Any, Awaitable, Dict, List, Optional

from .commands import Command

if TYPE_CHECKING:
    from steam.ext import commands

    from ...client import EventType
    from .bot import Bot
    from .context import Context

__all__ = ("Cog",)


class InjectedListener:
    """Injects the cog's "self" parameter into every event call auto-magically."""

    __slots__ = ("func", "cog")

    def __init__(self, cog: "Cog", func: "EventType"):
        self.func = func
        self.cog = cog

    def __call__(self, *args, **kwargs) -> Awaitable[None]:
        return self.func(self.cog, *args, **kwargs)


# for a bit of type hinting
class ExtensionType(ModuleType):
    @staticmethod
    def setup(bot: "Bot") -> None:
        pass

    @staticmethod
    def teardown(bot: "Bot") -> None:
        pass


class Cog:
    """A class from which Cogs can be created.
    These are used to separate commands and listeners into separate files.

    Attributes
    ----------
    qualified_name: :class:`str`
        The name of the cog. Can be set in a subclass e.g. ::

            MyCog(commands.Cog, name='SpecialCogName'):
                pass

        Defaults to ``Cog.__name__``.

    command_attrs: Dict[str, Any]
        Attributes to pass to every command registered in the cog.
        Can be set in subclass e.g. ::

            MyBrokenCog(commands.Cog, command_attrs=dict(enabled=False)):
                # all the commands would now be disabled
    """

    __commands__: Dict[str, Command]
    __listeners__: Dict[str, List["InjectedListener"]]
    command_attrs: Dict[str, Any]
    qualified_name: str

    def __init_subclass__(cls, *args, **kwargs):
        cls.qualified_name = kwargs.get("name") or cls.__name__
        cls.command_attrs = kwargs.get("command_attrs", dict())

        cls.__listeners__ = dict()
        cls.__commands__ = dict()
        for base in reversed(cls.__mro__):
            for name, attr in inspect.getmembers(base):
                if name in cls.__commands__:
                    del cls.__commands__[name]
                if isinstance(attr, Command):
                    cls.__commands__[name] = attr
                elif hasattr(attr, "__event_name__"):
                    try:
                        cls.__listeners__[attr.__event_name__].append(attr)
                    except KeyError:
                        cls.__listeners__[attr.__event_name__] = [attr]

    @property
    def description(self) -> Optional[str]:
        """Optional[:class:`str`]: The cleaned up docstring for the class."""
        help_doc = inspect.getdoc(self)
        if isinstance(help_doc, bytes):
            return help_doc.decode("utf-8")

        return help_doc

    @classmethod
    def listener(cls, name: Optional[str] = None):
        """Register a function as a listener.
        Similar to :meth:`~steam.ext.commands.Bot.listen`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for.
            Defaults to ``func.__name__``.
        """

        def decorator(func: "EventType"):
            if not asyncio.iscoroutinefunction(func):
                raise TypeError(f"Listeners must be coroutines, {func.__name__} is {type(func).__name__}")
            func.__event_name__ = name or func.__name__
            return func

        return decorator

    async def cog_command_error(self, ctx: "commands.Context", error: Exception):
        """|coro|
        A special method that is called when an error
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

    def _inject(self, bot: "Bot") -> None:
        for idx, command in enumerate(self.__commands__.values()):
            old_attrs = command.__dict__
            for name, value in self.command_attrs.items():
                if (name, value) not in old_attrs.items():
                    setattr(command, name, value)
            command.cog = self
            command.checks.append(self.cog_check)
            try:
                bot.add_command(command)
            except Exception:
                # undo our additions
                for to_undo in tuple(self.__commands__.values())[:idx]:
                    bot.remove_command(to_undo)
                raise

        for name, listeners in self.__listeners__.items():
            for idx, listener in enumerate(listeners):
                # we need to manually inject the "self" parameter
                listener = InjectedListener(self, listener)
                self.__listeners__[name][idx] = listener  # edit the original
                bot.add_listener(listener, name)

    def _eject(self, bot: "Bot") -> None:
        for command in self.__commands__.values():
            bot.remove_command(command)

        for name, listeners in self.__listeners__.items():
            for listener in listeners:
                bot.remove_listener(listener, name)

        self.cog_unload()
