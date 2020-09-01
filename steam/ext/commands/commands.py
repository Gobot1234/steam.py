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
https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/core.py
"""

import asyncio
import functools
import inspect
import sys
import typing
from types import MethodType
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    OrderedDict,
    Set,
    Type,
    Union,
)

from typing_extensions import Literal, get_args, get_origin

import steam

from ...errors import ClientException
from . import converters
from .cooldown import BucketType, Cooldown
from .errors import BadArgument, CheckFailure, MissingRequiredArgument, NotOwner
from .utils import CaseInsensitiveDict, reload_module_with_TYPE_CHECKING, update_annotations

if TYPE_CHECKING:
    from .bot import CommandFunctionType
    from .cog import Cog
    from .context import Context

__all__ = (
    "Command",
    "command",
    "GroupCommand",
    "group",
    "check",
    "is_owner",
    "cooldown",
)

CheckType = Callable[["Context"], Union[bool, Awaitable[bool]]]
MaybeCommand = Union[Callable[..., "Command"], "CommandFunctionType"]
CommandDeco = Callable[[MaybeCommand], MaybeCommand]
CommandErrorFunctionType = Callable[["Context", Exception], Awaitable[None]]


def to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif lowered in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    raise BadArgument(f'"{lowered}" is not a recognised boolean option')


class Command:
    def __init__(self, func: "CommandFunctionType", **kwargs):
        self.name: str = kwargs.get("name") or func.__name__
        if not isinstance(self.name, str):
            raise TypeError("Name of a command must be a string.")

        self.callback = func

        help_doc = kwargs.get("help")
        if help_doc is not None:
            help_doc = inspect.cleandoc(help_doc)
        else:
            help_doc = inspect.getdoc(func)
            if isinstance(help_doc, bytes):
                help_doc = help_doc.decode("utf-8")
        self.help: Optional[str] = help_doc

        try:
            checks = func.__commands_checks__
            checks.reverse()
        except AttributeError:
            checks = kwargs.get("checks", [])
        finally:
            self.checks: List[CheckType] = checks

        try:
            cooldown = func.__commands_cooldown__
        except AttributeError:
            cooldown = kwargs.get("cooldown", [])
        finally:
            self.cooldown: List[Cooldown] = cooldown

        self.enabled = kwargs.get("enabled", True)
        self.brief: Optional[str] = kwargs.get("brief")
        self.usage: Optional[str] = kwargs.get("usage")
        self.cog: Optional["Cog"] = kwargs.get("cog")
        self.parent: Optional["Command"] = kwargs.get("parent")
        self.description: str = inspect.cleandoc(kwargs.get("description", ""))
        self.hidden: bool = kwargs.get("hidden", False)
        self.aliases: Iterable[str] = kwargs.get("aliases", [])

        for alias in self.aliases:
            if not isinstance(alias, str):
                raise TypeError("A commands aliases should be an iterable only containing strings")

    def __str__(self):
        return self.qualified_name

    @property
    def callback(self) -> "CommandFunctionType":
        """The internal callback the command holds."""
        return self._callback

    @callback.setter
    def callback(self, function: "CommandFunctionType") -> None:
        if not asyncio.iscoroutinefunction(function):
            raise TypeError(f"Callback for command {function.__name__} must be a coroutine.")

        func = function.__func__ if isinstance(function, MethodType) else function
        module = sys.modules[function.__module__]

        try:
            annotations = update_annotations(func.__annotations__, module.__dict__)
        except NameError as exc:
            reload_module_with_TYPE_CHECKING(module)
            try:
                annotations = update_annotations(func.__annotations__, module.__dict__)
            except NameError:
                raise exc from None

        func.__annotations__ = annotations  # replace the function's old annotations for later
        self.params: OrderedDict[str, inspect.Parameter] = inspect.signature(function).parameters.copy()
        self.module = module
        self._callback = function

    @property
    def clean_params(self) -> OrderedDict[str, inspect.Parameter]:
        """:class:`OrderedDict[:class:`str`, :class:`inspect.Parameter`]`:
        The command's parameters without "self" and "ctx"."""
        params = self.params.copy()
        if self.cog is not None:
            try:
                params.popitem(last=False)  # cog's "self" param
            except ValueError:
                raise ClientException(f'Callback for {self.name} command is missing a "self" parameter.') from None
        try:
            params.popitem(last=False)  # context param
        except ValueError:
            raise ClientException(f'Callback for {self.name} command is missing a "ctx" parameter.') from None
        return params

    @property
    def qualified_name(self) -> str:
        """:class:`str`: The full name of the command, this takes into account subcommands etc."""
        return " ".join(c.name for c in reversed(list(self.parents)))

    @property
    def parents(self) -> typing.Generator["Command", None, None]:
        """Iterator[:class:`Command`]: A generator returning the command's parents."""

        def recursive_iter(command: Command) -> typing.Generator["Command", None, None]:
            yield command
            if isinstance(command.parent, GroupCommand):
                yield from recursive_iter(command.parent)

        return recursive_iter(self)

    def __call__(self, *args, **kwargs) -> Awaitable[None]:
        """|coro|
        Calls the internal callback that the command holds.

        .. note::
            This bypasses all mechanisms -- including checks, converters, invoke hooks, cooldowns, etc. You must take
            care to pass the proper arguments and types to this function.
        """
        if self.cog is not None:
            return self.callback(self.cog, *args, **kwargs)
        else:
            return self.callback(*args, **kwargs)

    def error(self, func: "CommandErrorFunctionType") -> "CommandErrorFunctionType":
        """Register an event to handle a commands ``on_error`` functionality similarly to
        :meth:`steam.ext.commands.Bot.on_command_error`.

        Example: ::

            @bot.command()
            async def raise_an_error(ctx):
                raise Exception('oh no an error')


            @raise_an_error.error
            async def on_error(ctx, error):
                print(f'{ctx.command.name} raised an exception {error}')
        """
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"Error handler for {self.name} must be a coroutine")
        self.on_error = func
        return func

    async def _parse_arguments(self, ctx: "Context") -> None:
        args = [ctx] if self.cog is None else [self.cog, ctx]
        kwargs = {}

        shlex = ctx.shlex

        for name, param in self.clean_params.items():
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                is_greedy = get_origin(param.annotation) is converters.Greedy
                greedy_args = []
                while 1:
                    argument = shlex.read()
                    if argument is None:
                        transformed = await self._get_default(ctx, param)
                    else:
                        try:
                            transformed = await self._transform(ctx, param, argument)
                        except BadArgument:
                            if not is_greedy:
                                raise
                            shlex.undo()  # undo last read string for the next argument
                            args.append(tuple(greedy_args))
                            break
                    if not is_greedy:
                        args.append(transformed)
                        break
                    greedy_args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                arg = " ".join(shlex)
                if not arg:
                    kwargs[name] = await self._get_default(ctx, param)
                else:
                    kwargs[name] = await self._transform(ctx, param, arg)
                break
            elif param.kind == param.VAR_KEYWORD:
                # same as **kwargs
                arguments = list(shlex)
                # TODO make injection way better, ie so you dont have to [] it to get dict values
                if not arguments:
                    kwargs[name] = await self._get_default(ctx, param)
                    break

                annotation = param.annotation
                if annotation is param.empty or annotation is dict:
                    annotation = Dict[str, str]  # default to {str: str}

                key_type, value_type = get_args(annotation)
                key_converter = self._get_converter(key_type)
                value_converter = self._get_converter(value_type)

                kv_pairs = [arg.split("=") for arg in arguments]
                kwargs[name] = {
                    await self._convert(ctx, key_converter, param, key_type.strip()): await self._convert(
                        ctx, value_converter, param, value_type.strip()
                    )
                    for key_type, value_type in kv_pairs
                }
                break

            elif param.kind == param.VAR_POSITIONAL:
                # same as *args
                for arg in shlex:
                    transformed = await self._transform(ctx, param, arg)
                    args.append(transformed)
                break
        ctx.args = tuple(args)
        ctx.kwargs = kwargs

    def _transform(self, ctx: "Context", param: inspect.Parameter, argument: str) -> Awaitable[Any]:
        param_type = param.annotation if param.annotation is not param.empty else str
        converter = self._get_converter(param_type)
        return self._convert(ctx, converter, param, argument)

    def _get_converter(self, param_type: type) -> Union[converters.Converter, type]:
        try:
            module = param_type.__module__
        except AttributeError:
            pass
        else:
            if module is not None and (module.startswith("steam.") and not module.endswith("converter")):
                converter = getattr(converters, f"{param_type.__name__}Converter", None)
                if converter is None:
                    raise NotImplementedError(f"{param_type.__name__} does not have an associated converter")
                return converter
        return param_type

    async def _convert(
        self,
        ctx: "Context",
        converter: Union[converters.Converter, type, Callable[[str], Any]],
        param: inspect.Parameter,
        argument: str,
    ) -> Any:
        if isinstance(converter, converters.Converter):
            try:
                converter = converter() if callable(converter) else converter
                return await converter.convert(ctx, argument)
            except Exception as exc:
                try:
                    name = converter.__name__
                except AttributeError:
                    name = converter.__class__.__name__
                raise BadArgument(f"{argument} failed to convert to {name}") from exc
        else:
            if converter is bool:
                return to_bool(argument)
            origin = get_origin(converter)
            if origin is not None:
                for arg in get_args(converter):
                    converter = self._get_converter(arg)
                    try:
                        return await self._convert(ctx, converter, param, argument)
                    except BadArgument:
                        if origin is Union:
                            continue
                        raise
                else:
                    if origin is Union and type(None) in get_args(converter):  # typing.Optional
                        try:
                            return self._get_default(ctx, param)  # get the default if possible
                        except MissingRequiredArgument:
                            return None  # fall back to None
                    raise BadArgument(f"Failed to parse {argument} to any type")

            try:
                return converter(argument)
            except Exception as exc:
                try:
                    name = converter.__name__
                except AttributeError:
                    name = converter.__class__.__name__
                raise BadArgument(f"{argument!r} failed to convert to {name}") from exc

    async def _get_default(self, ctx: "Context", param: inspect.Parameter) -> Any:
        if param.default is param.empty:
            raise MissingRequiredArgument(param)
        if isinstance(param.default, converters.Default):
            try:
                default = param.default() if callable(param.default) else param.default
                return await default.default(ctx)
            except Exception as exc:
                try:
                    name = param.default.__name__
                except AttributeError:
                    name = param.default.__class__.__name__
                raise BadArgument(f"{name} failed to return a default argument") from exc
        return param.default

    async def can_run(self, ctx: "Context") -> Literal[True]:
        for check in self.checks:
            if not await steam.utils.maybe_coroutine(check, ctx):
                raise CheckFailure("You failed to pass one of the checks for this command")
        return True


class GroupMixin:
    def __init__(self, *args, **kwargs):
        self.case_insensitive = kwargs.get("case_insensitive", False)
        self.__commands__: Dict[str, Command] = CaseInsensitiveDict() if self.case_insensitive else dict()
        super().__init__(*args, **kwargs)

    @property
    def commands(self) -> Set[Command]:
        """Set[:class:`Command`]: A list of the loaded commands."""
        return set(self.__commands__.values())

    def add_command(self, command: "Command") -> None:
        """Add a command to the internal commands list.

        Parameters
        ----------
        command: :class:`Command`
            The command to register.
        """
        if not isinstance(command, Command):
            raise TypeError("Commands should derive from commands.Command")

        if command.name in self.__commands__:
            raise ClientException(f"The command {command.name} is already registered.")

        if isinstance(self, Command):
            command.parent = self

        if isinstance(command.parent, GroupCommand):
            if command.parent is not self:
                return command.parent.add_command(command)

        self.__commands__[command.name] = command
        for alias in command.aliases:
            if alias in self.__commands__:
                self.remove_command(command.name)
                raise ClientException(f"{alias} is already an existing command or alias.")
            self.__commands__[alias] = command

    def remove_command(self, name: str) -> Optional[Command]:
        """Removes a command from the internal commands list.

        Parameters
        ----------
        name: :class:`str`
            The name of the command to remove.

        Returns
        --------
        Optional[:class:`Command`]
            The removed command.
        """
        try:
            command = self.__commands__.pop(name)
        except ValueError:
            return None

        for alias in command.aliases:
            del self.__commands__[alias]
        return command

    def get_command(self, name: str) -> Optional[Command]:
        """Get a command.

        Parameters
        ----------
        name: :class:`str`
            The name of the command.

        Returns
        -------
        Optional[:class:`Command`]
            The found command or ``None``.
        """
        if " " not in name:
            return self.__commands__.get(name)

        names = name.split()
        if not names:
            return None
        command = self.__commands__.get(names[0])
        if not isinstance(command, GroupMixin):
            return command

        return command.get_command(" ".join(names[1:]))

    def command(self, *args, **kwargs) -> Callable[["CommandFunctionType"], "Command"]:
        """A shortcut decorator that invokes :func:`command` and adds it to the internal command list."""

        def decorator(func: "CommandFunctionType"):
            try:
                kwargs["parent"]
            except KeyError:
                kwargs["parent"] = self
            result = command(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator

    def group(self, *args, **kwargs) -> Callable[["CommandFunctionType"], "GroupCommand"]:
        """A shortcut decorator that invokes :func:`group` and adds it to the internal command list."""

        def decorator(func: "CommandFunctionType"):
            try:
                kwargs["parent"]
            except KeyError:
                kwargs["parent"] = self
            result = group(*args, **kwargs)(func)
            self.add_command(result)
            return result

        return decorator


class GroupCommand(GroupMixin, Command):
    def __init__(self, func: "CommandFunctionType", **kwargs):
        super().__init__(func, **kwargs)

    @property
    def children(self) -> typing.Generator["Command", None, None]:
        for command in self.commands:
            yield command
            if isinstance(command, GroupCommand):
                yield from command.children

    def recursively_remove_all_commands(self):
        for command in self.commands:
            if isinstance(command, GroupCommand):
                command.recursively_remove_all_commands()
            self.remove_command(command.name)

    async def _parse_arguments(self, ctx: "Context") -> None:
        ctx.command.invoked_without_command = bool(list(self.children))
        await super()._parse_arguments(ctx)


def command(
    name: Optional[str] = None, cls: Type[Command] = Command, **attrs
) -> Callable[["CommandFunctionType"], Command]:
    """Register a coroutine as a :class:`Command`.

    Parameters
    ----------
    name: :class:`str`
        The name of the command. Will default to ``func.__name__``.
    cls: Type[:class:`Command`]
        The class to construct the command from. Defaults to :class:`Command`.
    **attrs:
        The attributes to pass to the command's ``__init__``.
    """

    def decorator(func: "CommandFunctionType") -> Command:
        if isinstance(func, Command):
            raise TypeError("Callback is already a command.")
        return cls(func, name=name, **attrs)

    return decorator


def group(
    name: Optional[str] = None, cls: Type[GroupCommand] = GroupCommand, **attrs
) -> Callable[["CommandFunctionType"], GroupCommand]:
    """Register a coroutine as a :class:`GroupCommand`.

    Parameters
    ----------
    name: :class:`str`
        The name of the command. Will default to ``func.__name__``.
    cls: Type[:class:`GroupCommand`]
        The class to construct the command from. Defaults to :class:`GroupCommand`.
    **attrs:
        The attributes to pass to the command's ``__init__``.
    """

    def decorator(func: "CommandFunctionType") -> GroupCommand:
        if isinstance(func, Command):
            raise TypeError("Callback is already a command.")
        return cls(func, name=name, **attrs)

    return decorator


def check(predicate: CheckType) -> CommandDeco:  # TODO better docs
    """
    A decorator that registers a function that *could be a* |coroutine_link|_. to a command.

    They should take a singular argument representing the :class:`~steam.ext.commands.Context` for the message.

    Examples
    ---------

    def is_mod(ctx):
        return ctx.author in ctx.clan.mods

    @commands.check(is_mod)
    @bot.command()
    async def kick(ctx, user: steam.User):
        # implementation here
    """

    def decorator(func: MaybeCommand) -> MaybeCommand:
        if isinstance(func, Command):
            func.checks.append(predicate)
        else:
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = []

            func.__commands_checks__.append(predicate)

        return func

    if inspect.iscoroutinefunction(predicate):
        decorator.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx):
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def is_owner() -> CommandDeco:
    """
    A decorator that will only allow the bot's owner to invoke the command, relies on
    :attr:`~steam.ext.commands.Bot.owner_id` or :attr:`~steam.ext.commands.Bot.owner_ids`.
    """

    def predicate(ctx: "Context") -> bool:
        if ctx.bot.owner_id:
            return ctx.author.id64 == ctx.bot.owner_id
        elif ctx.bot.owner_ids:
            return ctx.author.id64 in ctx.bot.owner_ids
        raise NotOwner()

    return check(predicate)


def cooldown(rate: int, per: float, type: BucketType = BucketType.Default) -> CommandDeco:
    """Mark a :class:`Command`'s cooldown.

    Parameters
    ----------
    rate: :class:`int`
        The amount of times a command can be executed
        before being put on cooldown.
    per: :class:`float`
        The amount of time to wait between cooldowns.
    type: :class:`.BucketType`
        The :class:`.BucketType` that the cooldown applies to.
    """

    def decorator(func: MaybeCommand) -> MaybeCommand:
        if isinstance(func, Command):
            func.cooldown.append(Cooldown(rate, per, type))
        else:
            if not hasattr(func, "__commands_cooldown__"):
                func.__commands_cooldown__ = []
            func.__commands_cooldown__.append(Cooldown(rate, per, type))
        return func

    return decorator
