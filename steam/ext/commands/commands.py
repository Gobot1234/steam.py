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
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Iterable, List, Optional, Type, Union

import steam

from ...errors import ClientException
from . import converters
from .cooldown import BucketType, Cooldown
from .errors import BadArgument, MissingRequiredArgument, NotOwner

if TYPE_CHECKING:
    from ...client import EventType
    from .cog import Cog
    from .context import Context

__all__ = (
    "Command",
    "command",
    "check",
    "is_owner",
    "cooldown",
)

CommandFuncType = Callable[["Context"], Awaitable[None]]
CheckType = Callable[["Context"], Awaitable[bool]]
MaybeCommand = Union[Callable[..., "Command"], CommandFuncType]
CommandDeco = Callable[[MaybeCommand], MaybeCommand]


def to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif lowered in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    else:
        raise BadArgument(f'"{lowered}" is not a recognised boolean option')


class Command:
    def __init__(self, func: CommandFuncType, **kwargs):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")

        self.callback = func

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

        self.params = inspect.signature(func).parameters
        self.name = kwargs.get("name") or func.__name__
        if not isinstance(self.name, str):
            raise TypeError("Name of a command must be a string.")

        help_doc = kwargs.get("help")
        if help_doc is not None:
            help_doc = inspect.cleandoc(help_doc)
        else:
            help_doc = inspect.getdoc(func)
            if isinstance(help_doc, bytes):
                help_doc = help_doc.decode("utf-8")

        self.help: Optional[str] = help_doc
        self.enabled = kwargs.get("enabled", True)
        self.brief: Optional[str] = kwargs.get("brief")
        self.usage: Optional[str] = kwargs.get("usage")
        self.cog: Optional["Cog"] = kwargs.get("cog")
        self.description: str = inspect.cleandoc(kwargs.get("description", ""))
        self.hidden = kwargs.get("hidden", False)
        self.aliases: Iterable[str] = kwargs.get("aliases", [])

        try:
            for alias in self.aliases:
                if not type(alias) is str:
                    raise TypeError
        except TypeError:
            raise TypeError("Aliases of a command must be an iterable containing only strings.")

    def __call__(self, *args, **kwargs):
        """|coro|
        Calls the internal callback that the command holds.

        .. note::
            This bypasses all mechanisms -- including checks, converters,
            invoke hooks, cooldowns, etc. You must take care to pass
            the proper arguments and types to this function.
        """
        if self.cog is not None:
            return self.callback(self.cog, *args, **kwargs)
        else:
            return self.callback(*args, **kwargs)

    def error(self, func: "EventType") -> "EventType":
        """Register an event to handle a commands
        ``on_error`` function.

        Example: ::

            @bot.command()
            async def raise_an_error(ctx):
                raise Exception('oh no an error')


            @raise_an_error.error
            async def on_error(ctx, error):
                print(f'{ctx.command.name} raised an exception {error}')
        """
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")
        self.on_error = func
        return func

    async def _parse_arguments(self, ctx: "Context") -> None:
        args = [ctx] if self.cog is None else [self.cog, ctx]
        kwargs = {}

        shlex = ctx.shlex
        iterator = iter(self.params.items())

        if self.cog is not None:
            # we have 'self' as the first parameter so just advance
            # the iterator and resume parsing
            try:
                next(iterator)
            except StopIteration:
                raise ClientException(f'Callback for {self.name} command is missing "self" parameter.')

        # next we have the 'ctx' as the next parameter
        try:
            next(iterator)
        except StopIteration:
            raise ClientException(f'Callback for {self.name} command is missing "ctx" parameter.')
        for name, param in iterator:
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                argument = shlex.get_token()
                if argument is None:
                    transformed = await self._get_default(ctx, param)
                else:
                    transformed = await self._transform(ctx, param, argument)
                args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                arg = " ".join(shlex)
                if not arg:
                    kwargs[name] = await self._get_default(ctx, param)
                else:
                    kwargs[name] = await self._transform(ctx, param, arg)
                break
            elif param.kind == param.VAR_KEYWORD:
                # we have received **kwargs
                arguments = list(shlex)
                if not arguments:
                    kwargs[name] = await self._get_default(ctx, param)

                annotation = param.annotation
                if annotation is inspect.Parameter.empty or annotation is dict:
                    annotation = Dict[str, str]  # default to {str: str}

                key_converter = self._get_converter(annotation.__args__[0])
                value_converter = self._get_converter(annotation.__args__[1])

                kv_pairs = [arg.split("=") for arg in arguments]
                kwargs[name] = {
                    await self._convert(ctx, key_converter, key): await self._convert(ctx, value_converter, value)
                    for (key, value) in kv_pairs
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

    def _transform(self, ctx, param: inspect.Parameter, argument: str) -> Awaitable[Any]:
        param_type = param.annotation if param.annotation is not param.empty else str
        converter = self._get_converter(param_type)
        return self._convert(ctx, converter, argument)

    def _get_converter(self, param_type: type) -> Union[converters.Converter, type]:
        if param_type.__name__ in dir(steam):  # find a converter
            converter = getattr(converters, f"{param_type.__name__}Converter", None)
            if converter is None:
                raise NotImplementedError(f"{param_type.__name__} does not have an associated converter")
            return converter
        return param_type

    async def _convert(
        self, ctx: "Context", converter: Union[Type[converters.Converter], type], argument: str,
    ):
        if hasattr(converter, "convert"):
            try:
                if hasattr(converter.convert, "__self__"):  # instance
                    return await converter.convert(ctx, argument)
                else:
                    return await converter.convert(converter, ctx, argument)
            except Exception as exc:
                raise BadArgument(f"{argument} failed to convert to type {converter.__name__}") from exc
        else:
            if converter is bool:
                return to_bool(argument)
            try:
                return converter(argument)
            except TypeError as exc:
                raise BadArgument(f"{argument} failed to convert to type {converter.__name__}") from exc

    async def _get_default(self, ctx, param: inspect.Parameter):
        if param.default is param.empty:
            raise MissingRequiredArgument(param)
        if inspect.isclass(param.default):
            default = param.default.default
            try:
                if hasattr("default", "__self__"):  # instance
                    return await default(ctx)
                else:
                    return await default(param.default, ctx)
            except Exception as exc:
                raise BadArgument(f"{param.default.__name__} failed to return a default argument") from exc
        return param.default

    async def can_run(self, ctx: "Context") -> bool:
        for check in self.checks:
            await check(ctx)
        return True


# TODO
# class GroupCommand(Command):
#     pass


def command(
    name: Optional[str] = None, cls: Optional[Type[Command]] = None, **attrs
) -> Callable[[CommandFuncType], Command]:
    r"""Register a coroutine as a :class:`~commands.Command`.

    Parameters
    ----------
    name: :class:`str`
        The name of the command.
        Will default to ``func.__name__``.
    cls: Type[:class:`Command`]
        The class to construct the command from. Defaults to
        :class:`Command`.
    \*\*attrs:
        The attributes to pass to the command's ``__init__``.
    """
    if cls is None:
        cls = Command

    def decorator(func: CommandFuncType) -> Command:
        if isinstance(func, Command):
            raise TypeError("Callback is already a command.")
        return cls(func, name=name, **attrs)

    return decorator


def check(predicate: CheckType) -> CommandDeco:
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


def is_owner() -> Callable[[CheckType], CommandDeco]:
    async def predicate(ctx: "Context") -> bool:
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
