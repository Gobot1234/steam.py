"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of
https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/bot.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import inspect
import os
import sys
import traceback
import warnings
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypedDict, TypeVar, overload

from ... import _const, utils
from ...client import Client, CoroFunc, E, log
from ...id import parse_id64
from .cog import Cog
from .commands import CHR, CheckReturnType, CheckType, Command, GroupMixin, InvokeT, check
from .context import Context
from .converters import CONVERTERS, Converters
from .errors import CommandNotFound
from .help import DefaultHelpCommand, HelpCommand
from .utils import Shlex

if TYPE_CHECKING:
    import datetime
    from collections.abc import Callable, Coroutine, Iterable

    from typing_extensions import Required, Unpack

    from steam.ext import commands

    from ...comment import Comment
    from ...gateway import Msgs
    from ...invite import ClanInvite, UserInvite
    from ...message import Message
    from ...trade import TradeOffer
    from ...user import User

__all__ = (
    "Bot",
    "when_mentioned",
    "when_mentioned_or",
)


CommandPrefixType: TypeAlias = (
    "Iterable[str] | Callable[[Bot, Message], Iterable[str] | Coroutine[Any, Any, Iterable[str]]]"
)
C = TypeVar("C", bound="Context")
Check = TypeVar("Check", bound="Callable[[CheckType], CheckReturnType]")


def when_mentioned(bot: Bot, message: Message) -> list[str]:
    """A callable that implements a command prefix equivalent to being mentioned.
    This is meant to be passed into the :attr:`.Bot.command_prefix` attribute.
    """
    return [bot.user.mention]


def when_mentioned_or(*prefixes: str) -> Callable[[Bot, Message], list[str]]:
    """A callable that implements when mentioned or other prefixes provided. These are meant to be passed into the
    :attr:`.Bot.command_prefix` attribute.

    Example
    -------
    .. code:: python

        bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"))

    Note
    ----
    This callable returns another callable, so if this is done inside a custom callable, you must call the
    returned callable, for example:

    .. code:: python

        async def get_prefix(bot: commands.Bot, message: steam.Message) -> list[str]:
            extras = await prefixes_for(message.clan)  # a user defined function that returns a list
            return commands.when_mentioned_or(*extras)(bot, message)

    See Also
    --------
    :func:`.when_mentioned`
    """

    def inner(bot: Bot, message: Message) -> list[str]:
        return list(prefixes) + when_mentioned(bot, message)

    return inner


class BotKwargs(TypedDict, total=False):
    command_prefix: Required[CommandPrefixType]
    help_command: HelpCommand
    owner_id: int
    owner_ids: Iterable[int]
    case_insensitive: bool


class Bot(GroupMixin, Client):
    """Represents a Steam bot.

    This class is a subclass of :class:`~steam.Client` and as a result anything that you can do with
    :class:`~steam.Client` you can do with Bot.

    Parameters
    ----------
    command_prefix
        What the message content must initially contain to have a command invoked.

        Can be any one of:
            - :class:`str`
            - Iterable[:class:`str`]
            - Callable[[:class:`Bot`, :class:`~steam.Message`], Union[:class:`str`, Iterable[:class:`str`]]
            - Callable[[:class:`Bot`, :class:`~steam.Message`], Awaitable[Union[:class:`str`, Iterable[:class:`str`]]]

        Note
        ----
        The first prefix matched when getting context will always be returned,
        ensure that no prefix matches a longer prefix later in the sequence.
        e.g.

        .. code:: python

            bot = commands.Bot(command_prefix=("!", "!?"))
            # the "!?" prefix will never be matched as the previous
            # prefix would match the "!" at the start of the message

        This is especially important when passing an empty string,
        it should always be last as no prefix after it will be matched.

    owner_id
        The Steam ID of the owner, this is converted to their 64 bit ID representation upon initialization.
    owner_ids
        The Steam IDs of the owners, these are converted to their 64 bit ID representations upon initialization.
    case_insensitive
        Whether or not commands should be invoke-able case insensitively.
    """

    def __init__(
        self,
        **options: Unpack[BotKwargs],
    ):
        super().__init__(**options)
        self.__cogs__: dict[str, Cog] = {}
        self.__listeners__: dict[str, list[CoroFunc]] = {}
        self.__extensions__: dict[str, ModuleType] = {}

        self.command_prefix = options["command_prefix"]
        self.owner_id = parse_id64(options.get("owner_id", 0))
        self.owner_ids = {parse_id64(owner_id) for owner_id in options.get("owner_ids", ())}
        if self.owner_id and self.owner_ids:
            raise ValueError("You cannot have both owner_id and owner_ids")

        # for _, command in inspect.getmembers_static(self, predicate=lambda x: isinstance(x, Command)):  # 3.11
        for member in dir(self):
            try:
                command = inspect.getattr_static(self, member)
            except AttributeError:
                continue
            if isinstance(command, Command):
                command.cog = self
                if isinstance(command, GroupMixin):
                    continue
                self.add_command(command)

        self.help_command = options.get("help_command", DefaultHelpCommand())

        self.checks: list[CheckReturnType] = []
        self._before_hook = None
        self._after_hook = None

    @property
    def cogs(self) -> MappingProxyType[str, Cog]:
        """A read only mapping of any loaded cogs."""
        return MappingProxyType(self.__cogs__)

    @property
    def extensions(self) -> MappingProxyType[str, ModuleType]:
        """A read only mapping of any loaded extensions."""
        return MappingProxyType(self.__extensions__)

    @property
    def converters(self) -> MappingProxyType[type, tuple[Converters, ...]]:
        """A read only mapping of registered converters."""
        return MappingProxyType(CONVERTERS)

    @property
    def help_command(self) -> HelpCommand | None:
        """The bot's help command."""
        return self._help_command

    @help_command.setter
    def help_command(self, value: HelpCommand | None) -> None:
        if value is None:
            self.remove_command("help")
            self._help_command = None
            return

        if not isinstance(value, HelpCommand):
            raise TypeError("help_command should derive from commands.HelpCommand")
        self.add_command(value)
        self._help_command = value

    def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        super().dispatch(event, *args, **kwargs)
        method = f"on_{event}"
        for ev in self.__listeners__.get(method, []):
            log.debug("Dispatching event %s", event)
            self._schedule_event(ev, method, *args, **kwargs)

    async def close(self) -> None:
        """Unloads any extensions and cogs, then closes the connection to Steam."""
        for extension in tuple(self.extensions):
            try:
                self.unload_extension(extension)
            except Exception:
                pass

        for cog in tuple(self.cogs.values()):
            try:
                self.remove_cog(cog)
            except Exception:
                pass

        await super().close()

    def _spec_from_extension(self, extension: str | os.PathLike[str]) -> importlib.machinery.ModuleSpec:
        if isinstance(extension, os.PathLike):
            path = Path(extension)
            spec = importlib.util.spec_from_file_location(path.name, path)
        else:
            spec = importlib.util.find_spec(extension)
        if spec is None:
            raise ModuleNotFoundError(f"{extension!r} not found")
        return spec

    def load_extension(self, extension: str | os.PathLike[str]) -> None:
        """Load an extension.

        Parameters
        ----------
        extension
            The name of the extension to load.

        Raises
        ------
        :exc:`ImportError`
            The ``extension`` is missing a setup function.
        """
        spec = self._spec_from_extension(extension)
        if spec.origin in self.__extensions__:
            return

        module = importlib.util.module_from_spec(spec)
        sys.modules[module.__name__] = module
        try:
            spec.loader.exec_module(module)
        except:
            del sys.modules[module.__name__]
            raise
        if not hasattr(module, "setup"):
            del sys.modules[module.__name__]
            raise ImportError(
                f"{module.__name__!r} is missing a setup function", name=module.__name__, path=module.__file__
            )

        module.setup(self)
        self.__extensions__[module.__file__] = module

    def unload_extension(self, extension: str | os.PathLike[str]) -> None:
        """Unload an extension.

        Parameters
        ----------
        extension
            The name of the extension to unload.

        Raises
        ------
        :exc:`ModuleNotFoundError`
            The ``extension`` wasn't found in the loaded extensions.
        """
        spec = self._spec_from_extension(extension)

        try:
            module = self.__extensions__[spec.origin]
        except KeyError:
            raise ModuleNotFoundError(
                f"The extension {extension!r} is not loaded", name=spec.name, path=spec.origin
            ) from None

        for cog in tuple(self.cogs.values()):
            if cog.__module__ == module.__name__:
                self.remove_cog(cog)

        if hasattr(module, "teardown"):
            module.teardown(self)

        del sys.modules[module.__name__]
        del self.__extensions__[module.__file__]

    def reload_extension(self, extension: str | os.PathLike[str]) -> None:
        """Atomically reload an extension. If any error occurs during the reload the extension will be reverted to its
        original state.

        Parameters
        ----------
        extension
            The name of the extension to reload.

        Raises
        ------
        :exc:`ModuleNotFoundError`
            The ``extension`` wasn't found in the loaded extensions.
        """
        spec = self._spec_from_extension(extension)

        try:
            previous = self.__extensions__[spec.origin]
        except KeyError:
            raise ModuleNotFoundError(
                f"The extension {extension!r} is not loaded", name=spec.name, path=spec.origin
            ) from None

        try:
            self.unload_extension(extension)
            self.load_extension(extension)
        except:
            previous.setup(self)
            self.__extensions__[previous.__file__] = previous
            sys.modules[previous.__name__] = previous
            raise

    def add_cog(self, cog: Cog) -> None:
        """Add a cog to the internal list.

        Parameters
        ----------
        cog
            The cog to add.
        """
        if not isinstance(cog, Cog):
            raise TypeError("Cogs must derive from commands.Cog")

        cog._inject(self)
        self.__cogs__[cog.qualified_name] = cog

    def remove_cog(self, cog: Cog) -> None:
        """Remove a cog from the internal list.

        Parameters
        ----------
        cog
            The cog to remove.
        """
        cog._eject(self)
        del self.__cogs__[cog.qualified_name]

    def add_listener(self, func: CoroFunc, name: str | None = None) -> None:
        """Add a function from the internal listeners list.

        Parameters
        ----------
        func
            The listener event to listen for.
        name
            The name of the event to listen for. Defaults to ``func.__name__``.
        """
        name = name or func.__name__

        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"Listeners must be coroutines, {name} is {type(func).__name__}")

        try:
            self.__listeners__[name].append(func)
        except KeyError:
            self.__listeners__[name] = [func]

    def remove_listener(self, func: CoroFunc, name: str | None = None) -> None:
        """Remove a function from the internal listeners list.

        Parameters
        ----------
        func
            The listener to remove.
        name
            The name of the event to remove. Defaults to ``func.__name__``.
        """
        name = name or func.__name__

        try:
            self.__listeners__[name].remove(func)
        except (KeyError, ValueError):
            pass

    @overload
    def listen(self, coro: E) -> E:
        ...

    @overload
    def listen(self, name: str | None = None) -> Callable[[E], E]:
        ...

    def listen(self, name: E | str | None = None) -> Callable[[E], E]:
        """|maybecallabledeco|
        Register a function as a listener. Calls :meth:`add_listener`. Similar to :meth:`.Cog.listener`

        Parameters
        ----------
        name: :class:`str`
            The name of the event to listen for. Will default to ``func.__name__``.
        """

        def decorator(coro: E) -> E:
            self.add_listener(coro, coro.__name__ if callable(name) else name)
            return coro

        return decorator(name) if callable(name) else decorator

    def check(self, predicate: Check | CHR | None = None) -> Check | CHR:
        """|maybecallabledeco|
        Register a global check for all commands. This is similar to :func:`commands.check`.
        """

        def decorator(predicate: Check) -> CHR:
            predicate = check(predicate)
            self.add_check(predicate)
            return predicate

        return decorator(predicate) if predicate is not None else decorator

    def add_check(self, predicate: CheckReturnType) -> None:
        """Add a global check to the bot.

        Parameters
        ----------
        predicate
            The check to add.
        """
        self.checks.append(predicate)

    def remove_check(self, predicate: CheckReturnType) -> None:
        """Remove a global check from the bot.

        Parameters
        ----------
        predicate
            The check to remove.
        """
        try:
            self.checks.remove(predicate)
        except ValueError:
            pass

    async def can_run(self, ctx: Context) -> bool:
        """Whether or not the context's command can be ran.

        Parameters
        ----------
        ctx
            The invocation context.
        """
        for check in self.checks:
            if not await utils.maybe_coroutine(check, ctx):
                return False
        return await ctx.command.can_run(ctx)

    @overload
    def before_invoke(self, coro: None = ...) -> Callable[[InvokeT], InvokeT]:
        ...

    @overload
    def before_invoke(self, coro: InvokeT) -> InvokeT:
        ...

    def before_invoke(self, coro: InvokeT | None = None) -> Callable[[InvokeT], InvokeT] | InvokeT:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to be ran before any arguments are parsed.
        """

        def decorator(coro: InvokeT) -> InvokeT:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Hook for {coro.__name__} must be a coroutine")
            self._before_hook = coro
            return coro

        return decorator(coro) if coro is not None else decorator

    @overload
    def after_invoke(self, coro: None = ...) -> Callable[[InvokeT], InvokeT]:
        ...

    @overload
    def after_invoke(self, coro: InvokeT) -> InvokeT:
        ...

    def after_invoke(self, coro: InvokeT | None = None) -> Callable[[InvokeT], InvokeT] | InvokeT:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to be ran after a command has been invoked.
        """

        def decorator(coro: InvokeT) -> InvokeT:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Hook for {coro.__name__} must be a coroutine")
            self._after_hook = coro
            return coro

        return decorator(coro) if coro is not None else decorator

    async def on_message(self, message: Message) -> None:
        await self.process_commands(message)

    async def process_commands(self, message: Message) -> None:
        """A method to process commands for a message.

        Warning
        -------
        This is vital for commands to function. If you have an :meth:`on_message` as a registered event using
        :meth:`event` commands will not be dispatched. Remember to add a call to this in your :meth:`on_message`
        event.

        Parameters
        ----------
        message
            The message to get the context for.
        """
        if message.author != self.user:
            ctx = await self.get_context(message)
            await self.invoke(ctx)

    async def invoke(self, ctx: Context) -> None:
        """Invoke a command. This will parse arguments, checks, cooldowns etc. correctly.

        Parameters
        ----------
        ctx
            The invocation context.
        """
        if ctx.command is not None:
            self.dispatch("command", ctx)
            try:
                await ctx.command.invoke(ctx)
            except Exception as exc:
                self.dispatch("command_error", ctx, exc)
            else:
                self.dispatch("command_completion", ctx)
        elif ctx.invoked_with:
            self.dispatch("command_error", ctx, CommandNotFound(f"The command {ctx.invoked_with!r} was not found"))

    async def get_context(self, message: Message, *, cls: type[C] = Context) -> C:
        """Get the context for a certain message.

        Parameters
        ----------
        message
            The message to get the context for.
        cls
            The class to construct the context with, this is the type of the return type
        """
        lex = Shlex(message.clean_content)

        prefix = await self.get_prefix(message)
        if prefix is None:
            return cls(bot=self, message=message, lex=lex, prefix=prefix)

        lex.position = len(prefix)
        invoked_with = lex.read()
        command = self.__commands__.get(invoked_with)

        return cls(
            bot=self,
            message=message,
            lex=lex,
            prefix=prefix,
            invoked_with=invoked_with,
            command=command,
        )

    async def get_prefix(self, message: Message) -> str | None:
        """Get the command prefix for a certain message.

        Parameters
        ----------
        message
            The message to get the prefix for.
        """
        prefixes = self.command_prefix
        if callable(prefixes):
            prefixes = await utils.maybe_coroutine(prefixes, self, message)
        if isinstance(prefixes, str):
            prefixes = (prefixes,)

        try:
            for prefix in prefixes:
                if not isinstance(prefix, str):
                    raise TypeError(f"command_prefix must return an iterable of strings not {type(prefix)}")
                if message.content.startswith(prefix):
                    return prefix
        except TypeError as exc:
            raise TypeError(f"command_prefix must return an iterable of strings not {type(prefixes)}") from exc

    def get_cog(self, name: str) -> Cog | None:
        """Get a loaded cog or ``None``.

        Parameters
        ----------
        name
            The name of the cog.
        """
        return self.__cogs__.get(name)

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """The default command error handler provided by the bot. This only fires if you do not specify any listeners for
        command error.

        Parameters
        ----------
        ctx
            The invocation context where the error happened.
        error
            The error that was raised.
        """
        if self.__listeners__.get("on_command_error"):
            return

        if hasattr(ctx.command, "on_error"):
            return await ctx.command.on_error(ctx, error)

        if ctx.cog and ctx.cog is not self:
            return await ctx.cog.cog_command_error(ctx, error)

        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if TYPE_CHECKING or _const.DOCS_BUILDING:

        async def on_command(self, ctx: commands.Context, /) -> None:
            """A method that is called every time a command is dispatched.

            Parameters
            ----------
            ctx
                The invocation context.
            """

        async def on_command_completion(self, ctx: commands.Context, /) -> None:
            """A method that is called every time a command is dispatched and completed without error.

            Parameters
            ----------
            ctx
                The invocation context.
            """
