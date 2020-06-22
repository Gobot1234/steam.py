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
import sys
import traceback
from copy import copy
from shlex import shlex as Shlex
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Type,
    Union,
)

from .cog import Cog, ExtensionType
from .command import Command, command
from .context import Context
from .errors import CommandNotFound
from ... import utils
from ...client import Client, event_type
from ...errors import ClientException

if TYPE_CHECKING:
    from steam.ext import commands
    from ...message import Message

__all__ = (
    'Bot',
)


str_or_iter_str = Union[str, Iterable[str]]
command_prefix_type = Union[
    str_or_iter_str,
    Callable[['Bot', 'Message'], Union[str_or_iter_str, Awaitable[str_or_iter_str]]]
]


class Bot(Client):
    """Represents a Steam bot.

    This class is a subclass of :class:`~steam.Client` and as a
    result anything that you can do with :class:`~steam.Client`
    you can do with Bot.

    Parameters
    ----------
    command_prefix
        What the message content must contain initially to have a command invoked.

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
        The Steam ID of the owner, this is converted to their 64 bit ID
        representation upon initialization.
    owner_ids: Set[:class:`int`]
        The Steam IDs of the owners, these are converted to their 64 bit ID
        representation upon initialization.
    """
    __cogs__: Dict[str, Cog] = dict()
    __commands__: Dict[str, Command] = dict()
    __listeners__: Dict[str, List[event_type]] = dict()
    __extensions__: Dict[str, 'ExtensionType'] = dict()

    def __init__(self, *, command_prefix: command_prefix_type, **options):
        self.command_prefix = command_prefix
        self.owner_id: int = utils.make_steam64(options.get('owner_id', 0))
        owner_ids: Set[int] = options.get('owner_ids', [])
        self.owner_ids = set()
        for owner_id in owner_ids:
            self.owner_ids.add(utils.make_steam64(owner_id))
        if self.owner_id and self.owner_ids:
            raise ValueError('you cannot have both owner_id and owner_ids')
        super().__init__(**options)

        for attr in [getattr(self, attr) for attr in dir(self)]:
            if not isinstance(attr, Command):
                continue

            self.add_command(attr)
            attr.cog = self
        self.add_command(Command(self._help_command, name='help'))

    @property
    def commands(self) -> List[Command]:
        """List[:class:`.Command`]: A list of loaded commands."""
        return list(self.__commands__.values())

    @property
    def extensions(self) -> Mapping[str, 'Command']:
        """Mapping[:class:`str`, :class:`.Command`]:
        A read only mapping of any loaded extensions."""
        return MappingProxyType(self.__extensions__)

    def dispatch(self, event: str, *args, **kwargs) -> None:
        super().dispatch(event, *args, **kwargs)
        method = f'on_{event}'
        for event in self.__listeners__.get(method, []):
            self._schedule_event(event, method, *args, **kwargs)

    async def close(self) -> None:
        """|coro|
        Unloads any extensions, cogs and commands, then
        closes the connection to Steam CMs and logs out.
        """
        for extension in self.__extensions__:
            try:
                self.unload_extension(extension)
            except Exception:
                pass

        for cog in self.__cogs__.values():
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

        module: 'ExtensionType' = importlib.import_module(extension)
        if hasattr(module, 'setup'):
            module.setup(self)
        else:
            del module
            del sys.modules[name]
            raise ImportError(f'extension {name} is missing a setup function')

        self.__extensions__[extension] = module

    def unload_extension(self, extension: str) -> None:
        """Unload an extension.

        Parameters
        ----------
        extension: :class:`str`
            The name of the extension to unload.
        """
        if extension not in self.__extensions__:
            raise ModuleNotFoundError(f'extension {extension} was not found')

        module: 'ExtensionType' = self.__extensions__[extension]
        for attr in [(getattr(self, attr) for attr in dir(module))]:
            if isinstance(attr, Cog):
                self.remove_cog(attr)

        if hasattr(module, 'teardown'):
            module.teardown(self)

        del sys.modules[extension]
        del self.__extensions__[extension]

    def reload_extension(self, extension: str) -> None:
        """Atomically reload an extension.
        If any error occurs during the reload the
        extension will be reverted to its original state.

        Parameters
        ----------
        extension: :class:`str`
            The name of the extension to reload.
        """
        previous = self.__extensions__[extension]

        try:
            self.unload_extension(extension)
            self.load_extension(extension)
        except Exception:
            previous.setup(self)
            self.__extensions__[extension] = previous
            sys.modules.update({extension: previous})
            raise

    def add_cog(self, cog: 'Cog') -> None:
        """Add a cog to the internal list.

        Parameters
        ----------
        cog: :class:`.Cog`
            The cog to add.
        """
        if not isinstance(cog, Cog):
            raise TypeError('cogs must derive from Cog')

        cog._inject(self)
        self.__cogs__[cog.qualified_name] = cog

    def remove_cog(self, cog: 'Cog') -> None:
        """Remove a cog from the internal list.

        Parameters
        ----------
        cog: :class:`.Cog`
            The cog to remove.
        """
        cog = cog._eject(self)
        del self.__cogs__[cog.qualified_name]

    def add_listener(self, func: event_type, name: str = None):
        """Add a function from the internal listeners list.

        Parameters
        ----------
        func: Callable[..., Awaitable[None]]
            The function to add.
        name: Optional[:class:`str`]
            The name of the event to listen for.
            Defaults to ``func.__name__``.
        """
        name = name or func.__name__

        if not asyncio.iscoroutinefunction(func):
            raise TypeError('listeners must be coroutines')

        if name in self.__listeners__:
            self.__listeners__[name].append(func)
        else:
            self.__listeners__[name] = [func]

    def remove_listener(self, func: 'event_type', name: str = None):
        """Remove a function from the internal listeners list.

        Parameters
        ----------
        func: Callable[..., Awaitable[None]]
            The function to remove.
        name: Optional[:class:`str`]
            The name of the event to remove.
            Defaults to ``func.__name__``.
        """
        name = name or func.__name__

        if name in self.__listeners__:
            try:
                self.__listeners__[name].remove(func)
            except ValueError:
                pass

    def listen(self, name: str = None) -> Callable[..., 'event_type']:
        """Register a function as a listener.
        Calls :meth:`add_listener`.
        Similar to :meth:`.Cog.listener`

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the event to listen for.
            Will default to ``func.__name__``.
        """
        def decorator(func: 'event_type'):
            self.add_listener(func, name)
            return func

        return decorator

    def add_command(self, command: 'Command') -> None:
        """Add a command to the internal commands list.

        Parameters
        ----------
        command: :class:`.Command`
            The command to register.
        """
        if not isinstance(command, Command):
            raise TypeError('the command passed must be a subclass of Command')

        if isinstance(self, Command):
            command.parent = self

        if command.name in self.__commands__:
            raise ClientException(f'command {command.name} is already registered.')

        self.__commands__[command.name] = command
        if not command.aliases:
            return

        for alias in command.aliases:
            if alias in self.__commands__:
                del self.__commands__[command.name]
                raise ClientException(f'{alias} is already an existing command or alias.')
            self.__commands__[alias] = command

    def remove_command(self, command: 'Command') -> None:
        """Removes a command from the internal commands list.

        Parameters
        ----------
        command: :class:`.Command`
            The command to remove.
        """
        for c in self.__commands__.values():
            if c.name == command.name:
                del self.__commands__[command.name]

    def command(self, *args, **kwargs) -> Callable[..., Command]:
        """A shortcut decorator that invokes :func:`.command`
        and adds it to the internal command list.
        """

        def decorator(func):
            try:
                kwargs['parent']
            except KeyError:
                kwargs['parent'] = self
            result = command(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    async def on_message(self, message: 'Message'):
        """|coro|
        Called when a message is created.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message that was received.
        """
        await self.process_commands(message)

    async def process_commands(self, message: 'Message'):
        """|coro|
        A method to process commands for a message.

        .. warning::
            This is vital for commands to function.
            If you have an :meth:`on_message` as a registered
            event using :meth:`event` commands will not be dispatched.
            Remember to add a call to this in your :meth:`on_message` event.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message to get the context for.
        """
        ctx = await self.get_context(message)
        await self.invoke(ctx)

    async def invoke(self, ctx: 'Context'):
        """|coro|
        Invoke a command. This will parse arguments,
        checks, cooldowns etc. correctly.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.
        """
        if not ctx.prefix:
            return
        self.dispatch('command', ctx)

        command = ctx.command
        await command._parse_arguments(ctx)
        # await ctx.command._check_cooldown(ctx)
        # if command.cog is not None:
        #     if not command.cog.cog_check(ctx):
        #         return
        try:
            await ctx.command.callback(*ctx.args, **ctx.kwargs)
        except Exception as exc:
            await self.on_command_error(ctx, exc)
            return
        self.dispatch('command_completion', ctx)

    async def get_context(self, message: 'Message', *, cls: Type[Context] = Context) -> Context:
        r"""|coro|
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

        content = message.content[len(prefix):].strip()
        shlex = Shlex(content)
        shlex.whitespace_split = True
        command_name = shlex.get_token().strip()  # skip command name
        command = self.__commands__.get(command_name)
        if command is None:
            raise CommandNotFound(f'the command {command_name} was not found')
        return cls(bot=self, message=message, shlex=shlex, command=command, prefix=prefix)

    async def get_prefix(self, message: 'Message') -> Optional[str]:
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
            prefixes = await utils.maybe_coroutine(self.command_prefix, message)
        if isinstance(prefixes, str):
            prefixes = (prefixes,)
        else:
            try:
                prefixes = tuple(prefixes)
            except TypeError as exc:
                raise TypeError(f'command_prefix must return an iterable not {type(prefixes)}') from exc

        for prefix in prefixes:
            if message.content.startswith(prefix):
                return prefix
        return None

    def get_command(self, name) -> Optional[Command]:
        """Get a command.

        Parameters
        ----------
        name: :class:`str`
            The name of the command.

        Returns
        -------
        Optional[:class:`.Command`]
            The found command or ``None``.
        """
        return self.__commands__.get(name)

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

    def get_extension(self, name: str) -> Optional['ExtensionType']:
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

    async def on_command_error(self, ctx: 'commands.Context', error: Exception):
        """|coro|
        The default command error handler provided by the bot.
        This only fires if you do not specify any listeners for command error.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context where the error happened.
        error: :exc:`Exception`
            The error that was raised.
        """
        default = self.__listeners__.get('on_command_error')
        if default is not None:
            for listener in default:
                await listener(ctx, error)
            return

        if hasattr(ctx.command, 'on_error'):
            return await ctx.command.on_error(ctx, error)

        if ctx.cog:
            return await ctx.cog.cog_command_error(ctx, error)

        print(f'Ignoring exception in command {ctx.command.name}:', file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    async def on_command(self, ctx: 'commands.Context'):
        """|coro|
        A method that is called every time a command is
        dispatched.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.
        """

    async def on_command_completion(self, ctx: 'commands.Context'):
        """|coro|
        A method that is called every time a command is
        dispatched and completed without error.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context.
        """

    async def _help_command(self, ctx: Context, *, command: str = None):
        """Shows help about the bot, a command, or a category."""
        # the default implementation for help.
        # TODO make a help class.
        if command is None:
            commands = []
            for c in self.commands:
                try:
                    doc = c.help.splitlines()[0]
                except (AttributeError, IndexError):
                    doc = 'None given'
                commands.append((command.name, doc))
            await ctx.send('\n'.join(f'{name}: {doc}' for name, doc in commands))
        else:
            command_ = self.__commands__.get(command)
            if command_ is not None:
                await ctx.send(f'Help with {command_.name}:\n{command_.help or "None given"}')
            else:
                await ctx.send(f'The command "{command}" was not found.')
