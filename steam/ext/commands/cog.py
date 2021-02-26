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

import inspect
import sys
import traceback
from typing import TYPE_CHECKING, Any, Callable, Optional, overload

from chardet import detect
from typing_extensions import Final

from ... import ClientException
from .commands import Command, GroupMixin

if TYPE_CHECKING:
    from steam.ext import commands

    from ...client import E, EventType
    from .bot import Bot
    from .context import Context

__all__ = ("Cog",)


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

    description: Optional[:class:`str`]
        The cleaned up doc-string for the cog.
    """

    __commands__: Final[dict[str, Command]]  # type: ignore
    __listeners__: Final[dict[str, list[EventType]]]  # type: ignore
    command_attrs: Final[dict[str, Any]]  # type: ignore
    qualified_name: Final[str]  # type: ignore
    description: Final[Optional[str]]  # type: ignore

    def __init_subclass__(cls, name: Optional[str] = None, command_attrs: Optional[dict[str, Any]] = None) -> None:
        cls.qualified_name = name or cls.__name__  # type: ignore
        cls.command_attrs = command_attrs or {}  # type: ignore

        if cls.__doc__ is not None:
            help_doc = inspect.cleandoc(cls.__doc__)
            if isinstance(help_doc, bytes):
                encoding = detect(help_doc)["encoding"]
                help_doc.decode(encoding)

            cls.description = help_doc  # type: ignore
        else:
            cls.description = None  # type: ignore

        cls.__listeners__ = {}  # type: ignore
        cls.__commands__ = {}  # type: ignore
        for name, attr in inspect.getmembers(cls):
            if name.startswith(("bot_", "cog_")) and getattr(Cog, name, None) is None:
                raise ClientException(
                    f'Methods prefixed with "bot_" or "cog_" are reserved for future use, {attr.__qualname__} is '
                    f"therefore not allowed"
                )
            if isinstance(attr, Command):
                if isinstance(attr, GroupMixin):
                    for name, value in cls.command_attrs.items():
                        for child in attr.children:
                            if name not in child.__original_kwargs__:
                                setattr(child, name, value)
                else:
                    cls.__commands__[name] = attr

                for name, value in cls.command_attrs.items():
                    if name not in attr.__original_kwargs__:
                        setattr(attr, name, value)

            elif hasattr(attr, "__event_name__"):
                try:
                    cls.__listeners__[attr.__event_name__].append(attr)
                except KeyError:
                    cls.__listeners__[attr.__event_name__] = [attr]

    def __repr__(self) -> str:
        return f"<Cog {f'{self.__class__.__module__}.{self.__class__.__name__}'!r}>"

    @property
    def commands(self) -> set[Command]:
        """set[:class:`Command`]: A set of the :class:`Cog`'s commands."""
        return set(self.__commands__.values())

    @property
    def listeners(self) -> list[tuple[str, EventType]]:
        """list[tuple[:class:`str`, Callable[..., Awaitable]]]:
        A list of tuples of the events registered with the format (name, listener)"""
        return [(listener.__name__, listener) for listeners in self.__listeners__.values() for listener in listeners]

    @classmethod
    @overload
    def listener(cls, coro: E) -> E:
        ...

    @classmethod
    @overload
    def listener(cls, name: Optional[str] = None) -> Callable[[E], E]:
        ...

    @classmethod
    def listener(cls, name: Optional[str] = None) -> Callable[[E], E]:
        """|maybecallabledeco|
        A decorator that registers a :term:`coroutine function` as a listener. Similar to
        :meth:`~steam.ext.commands.Bot.listen`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for. Defaults to ``func.__name__``.
        """

        def decorator(coro: E) -> E:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Listeners must be coroutine functions, {coro.__name__} is {type(coro).__name__}")
            coro.__event_name__ = name if not callable(name) else coro.__name__
            return coro

        return decorator(name) if callable(name) else decorator

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
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def cog_check(self, ctx: "commands.Context") -> bool:
        """|maybecoro|
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

    async def bot_check(self, ctx: "commands.Context") -> bool:
        """|maybecoro|
        A special method that registers as a :meth:`commands.Bot.check` globally. This should return a boolean result.

        Parameters
        -----------
        ctx: :class:`~commands.Context`
            The invocation context.

        Returns
        -------
        :class:`bool`
        """

    def cog_unload(self) -> None:
        """A special method that is called when the cog gets removed.

        This is called before :func:`teardown`.
        """

    def _inject(self, bot: Bot) -> None:
        cls = self.__class__
        if cls.bot_check is not Cog.bot_check:
            bot.add_check(self.bot_check)

        for idx, command in enumerate(self.__commands__.values()):
            del command.clean_params  # clear any previous params
            command.cog = self
            child.clean_params  # check the new params

            if cls.cog_check is not Cog.cog_check:
                command.checks.append(self.cog_check)

            if isinstance(command, GroupMixin):
                for child in command.children:
                    del child.clean_params
                    child.cog = self
                    child.clean_params

            for decorator in Command.DECORATORS:
                command_deco = getattr(command, decorator, None)
                if command_deco is not None:  # update any unbound decorators
                    setattr(command, command_deco.__name__, getattr(self, command_deco.__name__))

            try:
                bot.add_command(command)
            except Exception:
                # undo our additions
                for to_undo in tuple(self.__commands__)[:idx]:
                    bot.remove_command(to_undo)
                raise

        for name, listeners in self.__listeners__.items():
            for listener in listeners:
                listener = getattr(self, listener.__name__)  # get the bound method version
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
