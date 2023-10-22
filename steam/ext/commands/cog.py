"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import inspect
import sys
import traceback
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Final, Generic, TypeAlias, overload

from typing_extensions import Concatenate, TypeVar

from .commands import CogT, Command, Group, check
from .utils import Coro

if TYPE_CHECKING:
    from steam.ext import commands

    from .bot import Bot

__all__ = ("Cog",)

ListenerType: TypeAlias = Callable[..., Coro[None]]
UnboundListenerType: TypeAlias = "Callable[Concatenate[CogT, ...], Coro[None]]"
F = TypeVar("F", bound=UnboundListenerType)


class CogCommands:
    @overload
    def __get__(self, instance: None, owner: type[Cog]) -> set[Command[None]]:
        ...

    @overload
    def __get__(self, instance: CogT, owner: type[CogT]) -> set[Command[CogT]]:  # type: ignore
        ...

    def __get__(self, instance: Cog | None, owner: type[Cog]) -> Any:
        commands = owner.__commands__
        if instance is None:
            return {command for command in commands.values() if command.parent is None}
        cog_qualified_names = {command.qualified_name for command in commands.values()}
        return {command for command in instance.bot.commands if command.qualified_name in cog_qualified_names}


class CogListeners:
    @overload
    def __get__(self, instance: None, owner: type[CogT]) -> list[tuple[str, UnboundListenerType[CogT]]]:  # type: ignore
        ...

    @overload
    def __get__(self, instance: Cog, owner: type[Cog]) -> list[tuple[str, ListenerType]]:
        ...

    def __get__(self, instance: Cog | None, owner: type[Cog]) -> Any:
        if instance is None:
            return [
                (listener.__name__, listener) for listeners in owner.__listeners__.values() for listener in listeners
            ]

        return [
            (listener.__name__, getattr(instance, listener.__name__))
            for listeners in owner.__listeners__.values()
            for listener in listeners
        ]


BotT = TypeVar("BotT", bound="Bot", default="Bot", covariant=True)


class Cog(Generic[BotT]):
    """A class from which Cogs can be created. These are used to separate commands and listeners into separate files.

    Attributes
    ----------
    qualified_name
        The name of the cog. Can be set in a subclass e.g.

        .. code:: python

            class MyCog(commands.Cog, name="SpecialCogName"):
                ...

        Defaults to ``Cog.__name__``.

    command_attrs
        Attributes to pass to every command registered in the cog.
        Can be set in subclass e.g.

        .. code:: python

            class MyBrokenCog(commands.Cog, command_attrs=dict(enabled=False)):
                # all the commands by default would be disabled

                @commands.command()
                async def broken(self, ctx):  # disabled
                    ...

                @commands.command(enabled=True)
                async def working(self, ctx):  # enabled
                    ...

    description
        The cleaned up doc-string for the cog.
    """

    __commands__: Final[Mapping[str, Command[None]]]
    __listeners__: Final[Mapping[str, list[UnboundListenerType]]]
    command_attrs: Final[Mapping[str, Any]]
    qualified_name: Final[str]
    description: Final[str | None]
    bot: Final[BotT]

    def __init_subclass__(
        cls, name: str | None = None, command_attrs: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        cls.qualified_name = name or cls.__name__  # type: ignore
        cls.command_attrs = command_attrs or {}  # type: ignore
        cls.description = inspect.cleandoc(cls.__doc__) if cls.__doc__ is not None else None  # type: ignore

        cls.__listeners__ = {}  # type: ignore
        cls.__commands__ = {}  # type: ignore
        for name, attr in inspect.getmembers(cls):
            if name.startswith(("bot_", "cog_")) and getattr(Cog, name, None) is None:
                raise TypeError(
                    (
                        f'Methods prefixed with "bot_" or "cog_" are reserved for future use, {attr.__qualname__} is '
                        f"therefore not allowed"
                    )
                )
            if isinstance(attr, Command):
                if isinstance(attr, Group):
                    for name, value in cls.command_attrs.items():
                        for child in attr.children:
                            if name not in child.__original_kwargs__:
                                setattr(child, name, value)
                else:
                    cls.__commands__[name] = attr  # type: ignore

                for name, value in cls.command_attrs.items():
                    if name not in attr.__original_kwargs__:
                        setattr(attr, name, value)

            elif hasattr(attr, "__event_name__"):
                try:
                    cls.__listeners__[attr.__event_name__].append(attr)
                except KeyError:
                    cls.__listeners__[attr.__event_name__] = [attr]
        super().__init_subclass__(**kwargs)

    def __repr__(self) -> str:
        return f"<Cog {f'{self.__class__.__module__}.{self.__class__.__name__}'!r}>"

    commands: Final = CogCommands()
    """A set of the cog's commands."""

    listeners: Final = CogListeners()
    """A list of tuples of the events registered with the format (name, listener)"""

    @classmethod
    @overload
    def listener(cls, coro: F, /) -> F:
        ...

    @classmethod
    @overload
    def listener(cls, name: str | None = None, /) -> Callable[[F], F]:
        ...

    @classmethod
    def listener(cls, name: F | str | None = None, /) -> Callable[[F], F] | F:
        """|maybecallabledeco|
        Register a :term:`coroutine function` as a listener. Similar to :meth:`~steam.ext.commands.Bot.listen`.

        Parameters
        ----------
        name
            The name of the event to listen for. Defaults to ``func.__name__``.
        """

        def decorator(coro: F) -> F:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Listeners must be coroutine functions, {coro.__name__} is {type(coro).__name__}")
            coro.__event_name__ = coro.__name__ if callable(name) else name  # type: ignore
            return coro

        return decorator(name) if callable(name) else decorator

    async def cog_command_error(self, ctx: commands.Context[Bot], error: Exception) -> None:
        """A special method that is called when an error is dispatched inside this cog. This is similar to
        :func:`~commands.Bot.on_command_error` except it only applies to the commands inside this cog.

        Parameters
        -----------
        ctx
            The invocation context where the error happened.
        error
            The error that happened.
        """
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def cog_check(self, ctx: commands.Context[Bot]) -> bool:
        """A special method that registers as a :func:`commands.check` for every command and subcommand in this cog.

        Parameters
        -----------
        ctx
            The invocation context.
        """
        raise NotImplementedError

    async def bot_check(self, ctx: commands.Context[Bot]) -> bool:
        """A special method that registers as a :meth:`commands.Bot.check` globally.

        Parameters
        -----------
        ctx
            The invocation context.
        """
        raise NotImplementedError

    async def cog_unload(self) -> None:
        """A special method that is called when the cog gets removed.

        This is called before :func:`teardown`.
        """

    async def _inject(self, bot: BotT) -> None:  # type: ignore
        cls = self.__class__
        self.bot = bot  # type: ignore
        if cls.bot_check is not Cog.bot_check:
            bot.add_check(check(self.bot_check))

        for idx, command in enumerate(self.__commands__.values()):
            command = deepcopy(command)
            command.cog = self

            if cls.cog_check is not Cog.cog_check:
                command.checks.append(check(self.cog_check))

            if isinstance(command, Group):
                for child in command.children:
                    child.cog = self

            try:
                bot.add_command(command)
            except Exception:
                # undo our additions
                for to_undo in tuple(self.__commands__)[:idx]:
                    bot.remove_command(to_undo)
                raise

        for name, listener in self.listeners:
            bot.add_listener(listener, name)

    async def _eject(self, bot: Bot) -> None:
        for command in self.__commands__.values():
            if isinstance(command, Group):
                command.remove_all_commands()
            else:
                bot.remove_command(command.name)

        for name, listener in self.listeners:
            bot.remove_listener(listener, name)

        await self.cog_unload()
