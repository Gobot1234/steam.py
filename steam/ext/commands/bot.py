# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz
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

import asyncio
import importlib
import inspect
import sys
import traceback
from copy import copy
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

from typing_extensions import Literal, Protocol, overload

from ... import utils
from ...client import Client, EventType, log
from .cog import Cog, ExtensionType, InjectedListener
from .commands import Command, GroupCommand, GroupMixin
from .context import Context
from .errors import CheckFailure, CommandDisabled, CommandNotFound, CommandOnCooldown
from .help import HelpCommand
from .utils import Shlex

if TYPE_CHECKING:
    import datetime

    import steam
    from steam.ext import commands

    from ...comment import Comment
    from ...gateway import Msgs
    from ...invite import ClanInvite, UserInvite
    from ...message import Message
    from ...trade import TradeOffer
    from ...user import User
    from .commands import CheckType
    from .cooldown import Cooldown

__all__ = (
    "Bot",
    "when_mentioned",
    "when_mentioned_or",
)


StrOrIterStr = Union[str, Iterable[str]]
CommandPrefixType = Union[StrOrIterStr, Callable[["Bot", "Message"], Union[StrOrIterStr, Awaitable[StrOrIterStr]]]]


def when_mentioned(bot: "Bot", message: "steam.Message") -> List[str]:
    """A callable that implements a command prefix equivalent to being mentioned.
    This is meant to be passed into the :attr:`.Bot.command_prefix` attribute.
    """
    return [bot.user.mention]


def when_mentioned_or(*prefixes: str) -> Callable[["Bot", "steam.Message"], List[str]]:
    """A callable that implements when mentioned or other prefixes provided. These are meant to be passed into the
    :attr:`.Bot.command_prefix` attribute.

    Example
    --------
    .. code-block:: python3

        bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'))

    .. note::
        This callable returns another callable, so if this is done inside a custom callable, you must call the
        returned callable, for example: ::

            async def get_prefix(bot, message):
                extras = await prefixes_for(message.guild)  # returns a list
                return commands.when_mentioned_or(*extras)(bot, message)

    See Also
    ---------
    :func:`.when_mentioned`
    """

    def inner(bot: "Bot", message: "steam.Message") -> List[str]:
        return list(prefixes) + when_mentioned(bot, message)

    return inner


class CommandFunctionType(Protocol):
    __commands_checks__: List["CheckType"]
    __commands_cooldown__: List["Cooldown"]

    @overload
    async def __call__(self, ctx: "Context", *args, **kwargs) -> None:
        ...

    @overload
    async def __call__(self, cog: "Cog", ctx: "Context", *args, **kwargs) -> None:
        ...


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

        .. note::

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
    owner_ids: Set[:class:`int`]
        The Steam IDs of the owners, these are converted to their 64 bit ID representations upon initialization.
    case_insensitive: :class:`bool`
        Whether or not to use CaseInsensitiveDict for registering commands.

    loop: Optional[:class:`asyncio.AbstractEventLoop`]
        The :class:`asyncio.AbstractEventLoop` used for asynchronous operations. Defaults to ``None``, in which case the
        default event loop is used via :func:`asyncio.get_event_loop()`.
    game: :class:`~steam.Game`
        A games to set your status as on connect.
    games: List[:class:`~steam.Game`]
        A list of games to set your status to on connect.
    state: :class:`~steam.EPersonaState`
        The state to show your account as on connect.

        .. note::
            Setting your status to :attr:`~steam.EPersonaState.Offline`, will stop you receiving persona state
            updates and by extension :meth:`on_user_update` will stop being dispatched.

    ui_mode: :class:`~steam.EUIMode`
        The UI mode to set your status to on connect.
    force_kick: :class:`bool`
        Whether or not to forcefully kick any other playing sessions on connect.

    Attributes
    -----------
    loop: :class:`asyncio.AbstractEventLoop`
        The event loop that the client uses for HTTP requests.
    ws:
        The connected websocket, this can be used to directly send messages
        to the connected CM.
    """

    __cogs__: Dict[str, Cog] = dict()
    __listeners__: Dict[str, List[Union["EventType", "InjectedListener"]]] = dict()
    __extensions__: Dict[str, "ExtensionType"] = dict()

    def __init__(self, *, command_prefix: CommandPrefixType, help_command: HelpCommand = HelpCommand(), **options):
        super().__init__(**options)
        self.command_prefix = command_prefix
        self.owner_id = utils.make_id64(options.get("owner_id", 0))
        owner_ids: Set[int] = options.get("owner_ids", ())
        self.owner_ids = set()
        for owner_id in owner_ids:
            self.owner_ids.add(utils.make_id64(owner_id))
        if self.owner_id and self.owner_ids:
            raise ValueError("You cannot have both owner_id and owner_ids")
        inline_commands = dict()
        for base in reversed(self.__class__.__mro__):
            for name, attr in tuple(base.__dict__.items()):
                if name in inline_commands:
                    del inline_commands[name]
                if isinstance(attr, Command):
                    if attr.parent:  # sub-command don't add it to the global commands
                        continue
                    inline_commands[name] = attr
                if name[:3] != "on_":  # not an event
                    continue
                if "error" in name or name == "on_message":
                    continue
                try:
                    if attr.__code__.co_filename == __file__:
                        delattr(base, name)
                except AttributeError:
                    pass

        for command in inline_commands.values():
            setattr(self, command.callback.__name__, command)
            if isinstance(command, GroupCommand):
                for child in command.children:
                    child.cog = self
            command.cog = self
            self.add_command(command)
        self.help_command = help_command

    @property
    def cogs(self) -> Mapping[str, Cog]:
        """Mapping[:class:`str`, :class:`.Cog`]: A read only mapping of any loaded cogs."""
        return MappingProxyType(self.__cogs__)

    @property
    def extensions(self) -> Mapping[str, "ExtensionType"]:
        """Mapping[:class:`str`, :class:`ExtensionType`]: A read only mapping of any loaded extensions."""
        return MappingProxyType(self.__extensions__)

    @property
    def help_command(self) -> HelpCommand:
        return self._help_command

    @help_command.setter
    def help_command(self, value: HelpCommand):
        if not isinstance(value, HelpCommand):
            raise TypeError("help_command should derive from commands.HelpCommand")
        self.add_command(value)
        self._help_command = value

    def dispatch(self, event: str, *args, **kwargs) -> None:
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

    def load_extension(self, extension: str) -> None:
        """Load an extension.

        Parameters
        ----------
        extension: :class:`str`
            The name of the extension to load.
        """
        if extension in self.__extensions__:
            return

        module: "ExtensionType" = importlib.import_module(extension)
        if hasattr(module, "setup"):
            module.setup(self)
        else:
            del module
            del sys.modules[extension]
            raise ImportError(f"Extension {extension} is missing a setup function")

        self.__extensions__[extension] = module

    def unload_extension(self, extension: str) -> None:
        """Unload an extension.

        Parameters
        ----------
        extension: :class:`str`
            The name of the extension to unload.
        """
        if extension not in self.__extensions__:
            raise ModuleNotFoundError(f"The extension {extension} was not found", name=extension, path=extension)

        module: "ExtensionType" = self.__extensions__[extension]
        for attr in tuple(module.__dict__.values()):
            if inspect.isclass(attr) and issubclass(attr, Cog):
                cog = self.get_cog(attr.qualified_name)
                self.remove_cog(cog)

        if hasattr(module, "teardown"):
            try:
                module.teardown(self)
            except Exception:
                pass

        del sys.modules[extension]
        del self.__extensions__[extension]

    def reload_extension(self, extension: str) -> None:
        """Atomically reload an extension. If any error occurs during the reload the extension will be reverted to its
        original state.

        Parameters
        ----------
        extension: :class:`str`
            The name of the extension to reload.
        """
        previous = self.__extensions__.get(extension)
        if previous is None:
            raise ModuleNotFoundError(f"The extension {extension} was not found", name=extension, path=extension)

        try:
            self.unload_extension(extension)
            self.load_extension(extension)
        except Exception:
            previous.setup(self)
            self.__extensions__[extension] = previous
            sys.modules[extension] = previous
            raise

    def add_cog(self, cog: "Cog") -> None:
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

    def remove_cog(self, cog: "Cog") -> None:
        """Remove a cog from the internal list.

        Parameters
        ----------
        cog: :class:`.Cog`
            The cog to remove.
        """
        cog._eject(self)
        del self.__cogs__[cog.qualified_name]

    def add_listener(self, func: Union["EventType", "InjectedListener"], name: Optional[str] = None) -> None:
        """Add a function from the internal listeners list.

        Parameters
        ----------
        func: Callable[..., Awaitable[None]]
            The listener event to listen for.
        name: Optional[:class:`str`]
            The name of the event to listen for. Defaults to ``func.__name__``.
        """
        name = name or func.__name__

        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Listeners must be coroutines, {name} is {type(func).__name__}")

        try:
            self.__listeners__[name].append(func)
        except KeyError:
            self.__listeners__[name] = [func]

    def remove_listener(self, func: Union["EventType", "InjectedListener"], name: Optional[str] = None) -> None:
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

    def listen(self, name: Optional[str] = None) -> Callable[..., "EventType"]:
        """Register a function as a listener. Calls :meth:`add_listener`. Similar to :meth:`.Cog.listener`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for. Will default to ``func.__name__``.
        """

        def decorator(func: "EventType") -> "EventType":
            self.add_listener(func, name)
            return func

        return decorator

    async def on_message(self, message: "steam.Message"):
        """|coro|
        Called when a message is created.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message that was received.
        """
        await self.process_commands(message)

    async def process_commands(self, message: "Message") -> None:
        """|coro|
        A method to process commands for a message.

        .. warning::
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

    async def invoke(self, ctx: "Context") -> None:
        """|coro|
        Invoke a command. This will parse arguments, checks, cooldowns etc. correctly.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.
        """
        try:
            if not ctx.prefix:
                return
            if ctx.command is None:
                raise CommandNotFound(f"The command {ctx.invoked_with} was not found")

            command = ctx.command

            if not command.enabled:
                raise CommandDisabled(command)

            self.dispatch("command", ctx)
            for cooldown in command.cooldown:
                cooldown(ctx)

            try:
                await command._parse_arguments(ctx)
            except Exception as exc:
                return await self.on_command_error(ctx, exc)

            if not await command.can_run(ctx):
                raise CheckFailure("You failed to pass one of the command checks")

            try:
                await command.callback(*ctx.args, **ctx.kwargs)
            except Exception as exc:
                await self.on_command_error(ctx, exc)

        except (CheckFailure, CommandDisabled, CommandOnCooldown) as exc:
            await self.on_command_error(ctx, exc)

        else:
            self.dispatch("command_completion", ctx)

    async def get_context(self, message: "Message", *, cls: Type[Context] = Context) -> Context:
        """|coro|
        Get context for a certain message.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message to get the context for.
        cls: Type[:class:`.Context`]
            The class to construct the context with.

        Returns
        -------
        :class:`.Context`
            The context for the message.
        """
        prefix = await self.get_prefix(message)
        if not prefix:
            return cls(message=message, prefix=prefix, bot=self)

        content = message.content[len(prefix) :].strip()
        if not content:
            return cls(message=message, prefix=prefix, bot=self)

        command = None
        for i in range(len(content.split())):
            command = self.get_command(content.rsplit(maxsplit=i)[0])
            if command is not None:
                break

        if command is None:
            return cls(message=message, prefix=prefix, bot=self, invoked_with=content.split()[0])

        command_name = " ".join(content.split(maxsplit=i + 1)[: i + 1])  # account for aliases
        lex = Shlex(content[len(command_name) :].strip())
        return cls(bot=self, message=message, shlex=lex, command=command, prefix=prefix, invoked_with=command_name)

    async def get_prefix(self, message: "Message") -> Optional[str]:
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
            prefixes = await utils.maybe_coroutine(prefixes, message)
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        else:
            try:
                prefixes = tuple(prefixes)
            except TypeError as exc:
                raise TypeError(f"command_prefix must return an iterable of strings not {type(prefixes)}") from exc

        for prefix in prefixes:
            if not isinstance(prefix, str):
                raise TypeError(f"command_prefix must return an iterable of strings not {type(prefix)}")
            if message.content.startswith(prefix):
                return prefix
        return None

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

    def get_extension(self, name: str) -> Optional["ExtensionType"]:
        """Get a copy of a loaded extension.

        Parameters
        ----------
        name: :class:`str`
            The name of the extension.

        Returns
        -------
        Optional[ExtensionType]
            A copy of the found extension or ``None``.
        """
        return copy(self.__extensions__.get(name))

    async def on_command_error(self, ctx: "commands.Context", error: Exception):
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
        default = self.__listeners__.get("on_command_error")
        if default != self.on_command_error and default is not None:
            for listener in default:
                await listener(ctx, error)
            return

        if hasattr(ctx.command, "on_error"):
            return await ctx.command.on_error(ctx, error)

        if ctx.cog and ctx.cog is not self:
            return await ctx.cog.cog_command_error(ctx, error)

        print(f"Ignoring exception in command {ctx.command.name}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def on_command(self, ctx: "commands.Context"):
        """|coro|
        A method that is called every time a command is dispatched.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.
        """

    async def on_command_completion(self, ctx: "commands.Context"):
        """|coro|
        A method that is called every time a command is dispatched and completed without error.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.
        """

    @overload
    def wait_for(
        self, event: Literal["connect"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[None]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["disconnect"],
        *,
        check: Optional[Callable[[], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[None]":
        ...

    @overload  # don't know why you'd do this
    def wait_for(
        self, event: Literal["ready"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[None]":
        ...

    @overload
    def wait_for(
        self, event: Literal["login"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[None]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["error"],
        *,
        check: Optional[Callable[[str, Exception, Any, Any], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[str, Exception, Any, Any]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["message"],
        *,
        check: Optional[Callable[["steam.Message"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[steam.Message]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["comment"],
        *,
        check: Optional[Callable[["Comment"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Comment]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["user_update"],
        *,
        check: Optional[Callable[["User", "User"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[User, User]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["typing"],
        *,
        check: Optional[Callable[["User", "datetime.datetime"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[User, datetime.datetime]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_receive"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_send"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_accept"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_decline"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_cancel"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_expire"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_counter"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["user_invite"],
        *,
        check: Optional[Callable[["UserInvite"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[UserInvite]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["clan_invite"],
        *,
        check: Optional[Callable[["ClanInvite"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[ClanInvite]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_receive"],
        *,
        check: Optional[Callable[["Msgs"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Msgs]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_raw_receive"],
        *,
        check: Optional[Callable[[bytes], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[bytes]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_send"],
        *,
        check: Optional[Callable[["Msgs"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Msgs]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_raw_send"],
        *,
        check: Optional[Callable[[bytes], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[bytes]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["command_error"],
        *,
        check: Optional[Callable[[Context, Exception], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[Context, Exception]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["command"],
        *,
        check: Optional[Callable[[Context], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Context]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["command_completion"],
        *,
        check: Optional[Callable[[Context], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Context]":
        ...

    def wait_for(
        self, event: str, *, check: Optional[Callable[..., bool]] = None, timeout: Optional[float] = None
    ) -> "asyncio.Future[Any]":
        return super().wait_for(event, check=check, timeout=timeout)

    wait_for.__doc__ = Client.wait_for.__doc__
