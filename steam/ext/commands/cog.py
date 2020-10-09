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

from __future__ import annotations

import asyncio
import inspect
import sys
import traceback
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Optional

from chardet import detect
from typing_extensions import Final

from ...client import EventType
from ...utils import cached_property
from .commands import Command, GroupMixin

if TYPE_CHECKING:
    from steam.ext import commands

    from .bot import Bot
    from .context import Context

__all__ = (
    "Cog",
    "ExtensionType",
)


class InjectedListener:
    """Injects the cog's "self" parameter into every event call auto-magically."""

    __slots__ = ("func", "cog", "_is_coroutine")

    def __init__(self, cog: Cog, func: EventType):
        self.func = func
        self.cog = cog
        self._is_coroutine = asyncio.coroutines._is_coroutine  # marker for asyncio.iscoroutinefunction

    def __call__(self, *args: Any, **kwargs: Any) -> Coroutine[None, None, None]:
        return self.func(self.cog, *args, **kwargs)


# for a bit of type hinting
class ExtensionType(ModuleType):
    """A class to mimic an extension's file structure."""

    def setup(self, bot: Bot) -> None:
        pass

    def teardown(self, bot: Bot) -> None:
        pass


class Cog:
    """A class from which Cogs can be created. These are used to separate commands and listeners into separate files.

    Attributes
    ----------
    qualified_name: :class:`str`
        The name of the cog. Can be set in a subclass e.g. ::

            class MyCog(commands.Cog, name='SpecialCogName'):
                ...

        Defaults to ``Cog.__name__``.

    command_attrs: dict[:class:`str`, Any]
        Attributes to pass to every command registered in the cog.
        Can be set in subclass e.g. ::

            class MyBrokenCog(commands.Cog, command_attrs=dict(enabled=False)):
                # all the commands by default would be disabled

                @commands.command()
                async def broken(self, ctx):  # disabled
                    ...

                @commands.command(enabled=True)
                async def working(self, ctx):  # enabled
                    ...
    """

    __commands__: Final[dict[str, Command]]
    __listeners__: Final[dict[str, list[InjectedListener]]]
    command_attrs: Final[dict[str, Any]]
    qualified_name: Final[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        cls.qualified_name = kwargs.get("name") or cls.__name__
        cls.command_attrs = kwargs.get("command_attrs", dict())

        cls.__listeners__ = {}
        cls.__commands__ = {}
        for name, attr in inspect.getmembers(cls):
            if isinstance(attr, Command):
                if attr.parent:  # ungrouped commands have no parent
                    continue
                cls.__commands__[name] = attr
            elif hasattr(attr, "__event_name__"):
                try:
                    cls.__listeners__[attr.__event_name__].append(attr)
                except KeyError:
                    cls.__listeners__[attr.__event_name__] = [attr]

    def __repr__(self) -> str:
        return f"<Cog {f'{self.__class__.__module__}.{self.__class__.__name__}'!r}>"

    @cached_property
    def description(self) -> Optional[str]:
        """Optional[:class:`str`]: The cleaned up docstring for the class."""
        help_doc = inspect.getdoc(self)
        if isinstance(help_doc, bytes):
            encoding = detect(help_doc)["encoding"]
            return help_doc.decode(encoding)

        return help_doc

    @property
    def commands(self) -> set[Command]:
        """set[:class:`Command`]: A set of the :class:`Cog`'s commands."""
        return set(self.__commands__.values())

    @classmethod
    def listener(cls, name: Optional[str] = None) -> Callable[[EventType], EventType]:
        """A decorator that registers a :ref:`coroutine <coroutine>` as a listener.
        Similar to :meth:`~steam.ext.commands.Bot.listen`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for. Defaults to ``func.__name__``.
        """

        def decorator(func: EventType) -> EventType:
            if not asyncio.iscoroutinefunction(func):
                raise TypeError(f"Listeners must be coroutines, {func.__name__} is {type(func).__name__}")
            func.__event_name__ = name or func.__name__
            return func

        return decorator

    async def cog_command_error(self, ctx: "commands.Context", error: Exception) -> None:
        """|coro|
        A special method that is called when an error is dispatched inside this cog. This is similar to
        :func:`~commands.Bot.on_command_error` except it only applies to the commands inside this cog.

        Parameters
        -----------
        ctx: :class:`~steam.ext.commands.Context`
            The invocation context where the error happened.
        error: :exc:`Exception`
            The error that happened.
        """
        print(f"Ignoring exception in command {ctx.command.name}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def cog_check(self, ctx: "commands.Context") -> bool:
        """|coro|
        A special method that registers as a :func:`commands.check` for every command and subcommand in this cog.
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

    def cog_unload(self) -> None:
        """A special method that is called when the cog gets removed.

        This is called before :func:`teardown`.
        """

    def _inject(self, bot: Bot) -> None:
        for idx, command in enumerate(self.__commands__.values()):
            command.cog = self
            command.checks.append(self.cog_check)
            for name, value in self.command_attrs.items():
                if name not in command.__original_kwargs__:
                    setattr(command, name, value)
            setattr(self, command.callback.__name__, command)
            if isinstance(command, GroupMixin):
                for child in command.children:
                    child.cog = self
            try:
                bot.add_command(command)
            except Exception:
                # undo our additions
                for to_undo in tuple(self.__commands__)[:idx]:
                    bot.remove_command(to_undo)
                raise

        for name, listeners in self.__listeners__.items():
            for idx, listener in enumerate(listeners):
                # we need to manually inject the "self" parameter
                listener = InjectedListener(self, listener)
                self.__listeners__[name][idx] = listener  # edit the original
                bot.add_listener(listener, name)

    def _eject(self, bot: Bot) -> None:
        for command in self.__commands__.values():
            if isinstance(command, GroupMixin):
                command.recursively_remove_all_commands()
            bot.remove_command(command.name)

        for name, listeners in self.__listeners__.items():
            for listener in listeners:
                bot.remove_listener(listener, name)

        self.cog_unload()
