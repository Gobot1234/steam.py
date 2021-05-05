"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz
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

Heavily inspired by
https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/bot.py
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
import traceback
from collections.abc import Callable, Coroutine, Iterable
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union

from typing_extensions import Literal, TypeAlias, overload

from ... import utils
from ...client import Client, E, EventType, log
from .cog import Cog
from .commands import CH, CHR, CheckReturnType, Command, GroupMixin, H, check
from .context import Context
from .converters import CONVERTERS, Converters
from .errors import CommandNotFound
from .help import DefaultHelpCommand, HelpCommand
from .utils import Shlex

if TYPE_CHECKING:
    import datetime

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


StrOrIterStr: TypeAlias = "Union[str, Iterable[str]]"
CommandPrefixType: TypeAlias = """Union[
    StrOrIterStr, Callable[[Bot, Message], Union[StrOrIterStr, Coroutine[Any, Any, StrOrIterStr]]]
]"""
C = TypeVar("C", bound="Context")


def when_mentioned(bot: Bot, message: Message) -> list[str]:
    """A callable that implements a command prefix equivalent to being mentioned.
    This is meant to be passed into the :attr:`.Bot.command_prefix` attribute.
    """
    return [bot.user.mention]


def when_mentioned_or(*prefixes: str) -> Callable[[Bot, Message], list[str]]:
    """A callable that implements when mentioned or other prefixes provided. These are meant to be passed into the
    :attr:`.Bot.command_prefix` attribute.

    Example
    --------
    .. code-block:: python3

        bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'))

    Note
    ----
    This callable returns another callable, so if this is done inside a custom callable, you must call the
    returned callable, for example: ::

        async def get_prefix(bot, message):
            extras = await prefixes_for(message.clan)  # returns a list
            return commands.when_mentioned_or(*extras)(bot, message)

    See Also
    ---------
    :func:`.when_mentioned`
    """

    def inner(bot: Bot, message: Message) -> list[str]:
        return list(prefixes) + when_mentioned(bot, message)

    return inner


def resolve_path(path: Path) -> str:
    return path.resolve().relative_to(Path.cwd()).with_suffix("").as_posix().replace("/", ".")
    # resolve cogs relative to where they are loaded as it's probably the most common use case for this


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
        e.g. ::

            bot = commands.Bot(command_prefix=('!', '!?'))
            # the '!?' prefix will never be matched as the previous
            # prefix would match the '!' at the start of the message

        This is especially important when passing an empty string,
        it should always be last as no prefix after it will be matched.

    owner_id: :class:`int`
        The Steam ID of the owner, this is converted to their 64 bit ID representation upon initialization.
    owner_ids: set[:class:`int`]
        The Steam IDs of the owners, these are converted to their 64 bit ID representations upon initialization.
    case_insensitive: :class:`bool`
        Whether or not to use CaseInsensitiveDict for registering commands.
    """

    def __init__(
        self, *, command_prefix: CommandPrefixType, help_command: HelpCommand = DefaultHelpCommand(), **options: Any
    ):
        super().__init__(**options)
        self.__cogs__: dict[str, Cog] = {}
        self.__listeners__: dict[str, list[EventType]] = {}
        self.__extensions__: dict[str, ModuleType] = {}

        self.command_prefix = command_prefix
        self.owner_id = utils.make_id64(options.get("owner_id", 0))
        self.owner_ids = {utils.make_id64(owner_id) for owner_id in options.get("owner_ids", ())}
        if self.owner_id and self.owner_ids:
            raise ValueError("You cannot have both owner_id and owner_ids")

        for _, command in inspect.getmembers(self, lambda attr: isinstance(attr, Command)):
            command.cog = self

            if isinstance(command, GroupMixin):
                continue
            self.add_command(command)

        self.help_command = help_command

        self.checks: list[CheckReturnType] = []
        self._before_hook = None
        self._after_hook = None

    @property
    def cogs(self) -> MappingProxyType[str, Cog]:
        """Mapping[:class:`str`, :class:`.Cog`]: A read only mapping of any loaded cogs."""
        return MappingProxyType(self.__cogs__)

    @property
    def extensions(self) -> MappingProxyType[str, ModuleType]:
        """Mapping[:class:`str`, :class:`types.ModuleType`]: A read only mapping of any loaded extensions."""
        return MappingProxyType(self.__extensions__)

    @property
    def converters(self) -> MappingProxyType[type, tuple[Converters, ...]]:
        """Mapping[:class:`type`, tuple[:class:`~steam.ext.commands.Converter`, ...]]:
        A read only mapping of registered converters."""
        return MappingProxyType(CONVERTERS)

    @property
    def help_command(self) -> HelpCommand:
        """:class:`.HelpCommand`: The bot's help command."""
        return self._help_command

    @help_command.setter
    def help_command(self, value: Optional[HelpCommand]) -> None:
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
            log.debug(f"Dispatching event {event}")
            self._schedule_event(ev, method, *args, **kwargs)

    async def close(self) -> None:
        """|coro|
        Unloads any extensions and cogs, then closes the connection to Steam.
        """
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

    def load_extension(self, extension: os.PathLike[str]) -> None:
        """Load an extension.

        Parameters
        ----------
        extension: :class:`os.PathLike`
            The name of the extension to load.

        Raises
        ------
        :exc:`ImportError`
            The ``extension`` is missing a setup function.
        """
        if isinstance(extension, Path):
            extension = resolve_path(extension)
        extension = os.fspath(extension)
        if extension in self.__extensions__:
            return

        module = importlib.import_module(extension)
        if not hasattr(module, "setup"):
            del sys.modules[extension]
            raise ImportError(f"{extension!r} is missing a setup function", path=module.__file__, name=module.__name__)

        module.setup(self)
        self.__extensions__[extension] = module

    def unload_extension(self, extension: os.PathLike[str]) -> None:
        """Unload an extension.

        Parameters
        ----------
        extension: :class:`os.PathLike`
            The name of the extension to unload.

        Raises
        ------
        :exc:`ModuleNotFoundError`
            The ``extension`` wasn't found in the loaded extensions.
        """
        if isinstance(extension, Path):
            extension = resolve_path(extension)
        extension = os.fspath(extension)

        try:
            module = self.__extensions__[extension]
        except KeyError:
            raise ModuleNotFoundError(
                f"The extension {extension!r} was not found", name=extension, path=extension
            ) from None

        for cog in tuple(self.cogs.values()):
            if cog.__module__ == module.__name__:
                self.remove_cog(cog)

        if hasattr(module, "teardown"):
            module.teardown(self)

        del sys.modules[extension]
        del self.__extensions__[extension]

    def reload_extension(self, extension: os.PathLike[str]) -> None:
        """Atomically reload an extension. If any error occurs during the reload the extension will be reverted to its
        original state.

        Parameters
        ----------
        extension: :class:`os.PathLike`
            The name of the extension to reload.

        Raises
        ------
        :exc:`ModuleNotFoundError`
            The ``extension`` wasn't found in the loaded extensions.
        """
        if isinstance(extension, Path):
            extension = resolve_path(extension)
        extension = os.fspath(extension)

        try:
            previous = self.__extensions__[extension]
        except KeyError:
            raise ModuleNotFoundError(
                f"The extension {extension!r} was not found", name=extension, path=extension
            ) from None

        try:
            self.unload_extension(extension)
            self.load_extension(extension)
        except Exception:
            previous.setup(self)
            self.__extensions__[extension] = previous
            sys.modules[extension] = previous
            raise

    def add_cog(self, cog: Cog) -> None:
        """Add a cog to the internal list.

        Parameters
        ----------
        cog: :class:`.Cog`
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
        cog: :class:`.Cog`
            The cog to remove.
        """
        cog._eject(self)
        del self.__cogs__[cog.qualified_name]

    def add_listener(self, func: EventType, name: Optional[str] = None) -> None:
        """Add a function from the internal listeners list.

        Parameters
        ----------
        func: Callable[..., Awaitable[None]]
            The listener event to listen for.
        name: Optional[:class:`str`]
            The name of the event to listen for. Defaults to ``func.__name__``.
        """
        name = name or func.__name__

        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"Listeners must be coroutines, {name} is {type(func).__name__}")

        try:
            self.__listeners__[name].append(func)
        except KeyError:
            self.__listeners__[name] = [func]

    def remove_listener(self, func: EventType, name: Optional[str] = None) -> None:
        """Remove a function from the internal listeners list.

        Parameters
        ----------
        func: Callable[..., Awaitable[None]]
            The listener to remove.
        name: Optional[:class:`str`]
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
    def listen(self, name: Optional[str] = None) -> Callable[[E], E]:
        ...

    def listen(self, name: Union[E, str, None] = None) -> Callable[[E], E]:
        """|maybecallabledeco|
        Register a function as a listener. Calls :meth:`add_listener`. Similar to :meth:`.Cog.listener`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for. Will default to ``func.__name__``.
        """

        def decorator(coro: E) -> E:
            self.add_listener(coro, name if not callable(name) else coro.__name__)
            return coro

        return decorator(name) if callable(name) else decorator

    def check(self, predicate: Optional[Union[CH, CHR]] = None) -> Union[CH, CHR]:
        """|maybecallabledeco|
        Register a global check for all commands. This is similar to :func:`commands.check`.
        """

        def decorator(predicate: CH) -> CHR:
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
        """|coro|
        Whether or not the context's command can be ran.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.

        Returns
        -------
        :class:`bool`
        """
        for check in self.checks:
            if not await utils.maybe_coroutine(check, ctx):
                return False
        return await ctx.command.can_run(ctx)

    @overload
    def before_invoke(self, coro: Literal[None] = ...) -> Callable[[H], H]:
        ...

    @overload
    def before_invoke(self, coro: H) -> H:
        ...

    def before_invoke(self, coro: Optional[H] = None) -> Union[Callable[[H], H], H]:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to be ran before any arguments are parsed.
        """

        def decorator(coro: H) -> H:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Hook for {coro.__name__} must be a coroutine")
            self._before_hook = coro
            return coro

        return decorator(coro) if coro is not None else decorator

    @overload
    def after_invoke(self, coro: Literal[None] = ...) -> Callable[[H], H]:
        ...

    @overload
    def after_invoke(self, coro: H) -> H:
        ...

    def after_invoke(self, coro: Optional[H] = None) -> Union[Callable[[H], H], H]:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to be ran after a command has been invoked.
        """

        def decorator(coro: H) -> H:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Hook for {coro.__name__} must be a coroutine")
            self._after_hook = coro
            return coro

        return decorator(coro) if coro is not None else decorator

    async def on_message(self, message: Message) -> None:
        """|coro|
        Called when a message is created.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message that was received.
        """
        await self.process_commands(message)

    async def process_commands(self, message: Message) -> None:
        """|coro|
        A method to process commands for a message.

        Warning
        -------
        This is vital for commands to function. If you have an :meth:`on_message` as a registered event using
        :meth:`event` commands will not be dispatched. Remember to add a call to this in your :meth:`on_message`
        event.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message to get the context for.
        """
        if message.author != self.user:
            ctx = await self.get_context(message)
            await self.invoke(ctx)

    async def invoke(self, ctx: Context) -> None:
        """|coro|
        Invoke a command. This will parse arguments, checks, cooldowns etc. correctly.

        Parameters
        ----------
        ctx: :class:`.Context`
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
        """|coro|
        Get context for a certain message.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message to get the context for.
        cls: type[:class:`.Context`]
            The class to construct the context with.

        Returns
        -------
        :class:`.Context`
            The context for the message.
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

    async def get_prefix(self, message: Message) -> Optional[str]:
        """|coro|
        Get a command prefix for a certain message.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message to get the prefix for.

        Returns
        -------
        Optional[:class:`str`]
            The prefix for the message.
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

    def get_cog(self, name: str) -> Optional[Cog]:
        """Get a loaded cog.

        Parameters
        ----------
        name: :class:`str`
            The name of the cog.

        Returns
        -------
        Optional[:class:`.Cog`]
            The found cog or ``None``.
        """
        return self.__cogs__.get(name)

    async def on_command_error(self, ctx: "commands.Context", error: Exception) -> None:
        """|coro|
        The default command error handler provided by the bot. This only fires if you do not specify any listeners for
        command error.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context where the error happened.
        error: :exc:`Exception`
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

    if TYPE_CHECKING:  # these methods shouldn't exist at runtime unless subclassed to prevent pollution of logs

        async def on_command(self, ctx: "commands.Context") -> None:
            """|coro|
            A method that is called every time a command is dispatched.

            Parameters
            ----------
            ctx: :class:`.Context`
                The invocation context.
            """

        async def on_command_completion(self, ctx: "commands.Context") -> None:
            """|coro|
            A method that is called every time a command is dispatched and completed without error.

            Parameters
            ----------
            ctx: :class:`.Context`
                The invocation context.
            """

    @overload
    async def wait_for(
        self,
        event: Literal[
            "connect",
            "disconnect",
            "ready",
            "login",
            "logout",
        ],
        *,
        check: Optional[Callable[[], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> None:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["error"],
        *,
        check: Optional[Callable[[str, Exception, tuple[Any, ...], dict[str, Any]], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> tuple[str, Exception, tuple, dict]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["message"],
        *,
        check: Optional[Callable[[Message], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Message:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["comment"],
        *,
        check: Optional[Callable[[Comment], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Comment:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["user_update"],
        *,
        check: Optional[Callable[[User, User], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> tuple[User, User]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["typing"],
        *,
        check: Optional[Callable[[User, datetime.datetime], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> tuple[User, datetime.datetime]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "trade_receive",
            "trade_send",
            "trade_accept",
            "trade_decline",
            "trade_cancel",
            "trade_expire",
            "trade_counter",
        ],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> TradeOffer:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["user_invite"],
        *,
        check: Optional[Callable[[UserInvite], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> UserInvite:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["clan_invite"],
        *,
        check: Optional[Callable[[ClanInvite], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> ClanInvite:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "socket_receive",
            "socket_send",
        ],
        *,
        check: Optional[Callable[[Msgs], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Msgs:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["command_error"],
        *,
        check: Optional[Callable[[Context, Exception], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> tuple[Context, Exception]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "command",
            "command_completion",
        ],
        *,
        check: Optional[Callable[[Context], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Context:
        ...

    async def wait_for(
        self,
        event: str,
        *,
        check: Optional[Callable[..., bool]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        return await super().wait_for(event, check=check, timeout=timeout)  # noqa
