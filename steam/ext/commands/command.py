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
import inspect
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Type, Union

import steam

from ...errors import ClientException
from . import converters
from .cooldown import BucketType, Cooldown
from .errors import BadArgument, MissingRequiredArgument

if TYPE_CHECKING:
    from ...client import EventType
    from .cog import Cog
    from .context import Context

__all__ = (
    "Command",
    "command",
)

CommandFuncType = Callable[["Context"], Awaitable[None]]


def to_bool(argument: str):
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
        self.checks: List[Callable[..., Awaitable[bool]]] = []
        self._cooldowns: List[Cooldown] = []
        self.params = inspect.signature(func).parameters
        self.name = kwargs.get("name") or func.__name__
        if not isinstance(self.name, str):
            raise TypeError("Name of a command must be a string.")

        self.enabled = kwargs.get("enabled", True)

        help_doc = kwargs.get("help")
        if help_doc is not None:
            help_doc = inspect.cleandoc(help_doc)
        else:
            help_doc = inspect.getdoc(func)
            if isinstance(help_doc, bytes):
                help_doc = help_doc.decode("utf-8")

        self.help = help_doc

        self.brief = kwargs.get("brief")
        self.usage = kwargs.get("usage")
        self.aliases = kwargs.get("aliases", [])

        try:
            for alias in self.aliases:
                if not type(alias) is str:
                    raise TypeError
        except TypeError:
            raise TypeError("aliases of a command must be an iterable containing only strings.")

        self.description = inspect.cleandoc(kwargs.get("description", ""))
        self.hidden = kwargs.get("hidden", False)
        self.cog: "Cog" = kwargs.get("cog")

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
            raise TypeError("callback must be a coroutine.")
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
                    transformed = await self.transform(ctx, param, argument)
                args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                arg = " ".join(shlex)
                if not arg:
                    kwargs[name] = await self._get_default(ctx, param)
                else:
                    kwargs[name] = await self.transform(ctx, param, arg)
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
                    transformed = await self.transform(ctx, param, arg)
                    args.append(transformed)
                break
        ctx.args = tuple(args)
        ctx.kwargs = kwargs

    def transform(self, ctx, param: inspect.Parameter, argument: str) -> Awaitable[Any]:
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
        if isinstance(converter, converters.Converter):
            try:
                return await converter.convert(ctx, argument)
            except Exception as exc:
                raise BadArgument(f"{argument} failed to convert to type {converter.__name__ or str}") from exc
        if issubclass(converter, converters.Converter):
            try:
                return await converter.convert(converter, ctx, argument)
            except Exception as exc:
                raise BadArgument(f"{argument} failed to convert to type {converter.__name__ or str}") from exc
        else:
            if converter is bool:
                return to_bool(argument)
            try:
                return converter(argument)
            except TypeError as exc:
                raise BadArgument(f"{argument} failed to convert to type {converter.__name__ or str}") from exc

    async def _get_default(self, ctx, param: inspect.Parameter):
        if param.default is param.empty:
            raise MissingRequiredArgument(param)
        if inspect.isclass(param.default):
            if isinstance(param.default, converters.Default):
                return await param.default.default(ctx)
            if issubclass(param.default, converters.Default):
                return await param.default.default(param.default, ctx)
        return param.default

    def _parse_cooldown(self, ctx: "Context"):
        for cooldown in self._cooldowns:
            bucket = cooldown.bucket.get_bucket(ctx)
            cooldown(bucket)


def command(name: str = None, cls: Type[Command] = None, **attrs) -> Callable[..., Command]:
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


def cooldown(rate: int, per: float, bucket: BucketType) -> Callable[..., None]:
    """Mark a :class:`Command`'s cooldown.

    Parameters
    ----------
    rate: :class:`int`
        The amount of times a command can be executed
        before being put on cooldown.
    per: :class:`float`
        The amount of time to wait between cooldowns.
    bucket:
        The :class:`.BucketType` that the cooldown applies
        to.
    """

    def decorator(func: "Command") -> None:
        func._cooldowns.append(Cooldown(rate, per, bucket))

    return decorator
