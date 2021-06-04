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
https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/core.py
"""

from __future__ import annotations

import asyncio
import functools
import inspect
from collections.abc import Callable, Coroutine, Iterable
from time import time
from typing import TYPE_CHECKING, Any, ForwardRef, Optional, TypeVar, Union, get_type_hints, overload

from typing_extensions import Literal, ParamSpec, TypeAlias, get_args, get_origin

from ...channel import DMChannel
from ...errors import ClientException
from ...models import FunctionType
from ...utils import cached_property, maybe_coroutine
from . import converters
from .cooldown import BucketType, Cooldown
from .errors import (
    BadArgument,
    CheckFailure,
    CommandDisabled,
    DMChannelOnly,
    DuplicateKeywordArgument,
    MissingRequiredArgument,
    NotOwner,
    UnmatchedKeyValuePair,
)
from .utils import CaseInsensitiveDict

if TYPE_CHECKING:
    from .bot import Bot
    from .cog import Cog
    from .context import Context

__all__ = (
    "Command",
    "command",
    "Group",
    "group",
    "check",
    "is_owner",
    "cooldown",
)

CheckType: TypeAlias = "Callable[[Context], Union[bool, Coroutine[Any, Any, bool]]]"
MaybeCommand: TypeAlias = "Union[Callable[..., Command], CommandFunctionType]"
C = TypeVar("C", bound="Command")
G = TypeVar("G", bound="Group")
E = TypeVar("E", bound="Callable[[Context, Exception], Coroutine[Any, Any, None]]")
H = TypeVar("H", bound="Callable[[Context], Coroutine[Any, Any, None]]")
MC = TypeVar("MC", bound=MaybeCommand)
MCD = TypeVar("MCD", bound=Union["CommandDeco", MaybeCommand])
CFT = TypeVar("CFT", bound="CommandFunctionType")
CHR = TypeVar("CHR", bound="CheckReturnType")
CH = TypeVar("CH", bound="Callable[[CheckType], CheckReturnType]")


class CommandDeco(FunctionType):  # bad Callable[[MC], MC]
    def __call__(self, command: MC) -> MC:
        ...


class CheckReturnType(CommandDeco):
    predicate: CheckType


class CommandFunctionType(FunctionType):
    __commands_checks__: list[CheckType]
    __commands_cooldown__: list[Cooldown]
    __special_converters__: list[type[converters.Converter]]

    @overload
    async def __call__(self, ctx: Context, *args: Any, **kwargs: Any) -> None:
        ...

    @overload
    async def __call__(self, cog: Cog, ctx: Context, *args: Any, **kwargs: Any) -> None:
        ...


@converters.converter_for(bool)
def to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in ("yes", "y", "true", "t", "1", "enable", "on"):
        return True
    elif lowered in ("no", "n", "false", "f", "0", "disable", "off"):
        return False
    raise BadArgument(f"{argument!r} is not a recognised boolean option")


class Command:
    """A class to represent a command.

    Attributes
    ----------
    name: :class:`str`
        The command's name.
    help: Optional[:class:`str`]
        The command's help docstring.
    checks: list[Callable[[:class:`steam.ext.commands.Context`], Union[:class:`bool`, Awaitable[:class:`bool`]]
        A list of the command's checks.
    cooldown: list[:class:`.Cooldown`]
        The command's cooldowns.
    special_converters: list[type[converters.Converter]]
        A list of the command's special converters as registered by :meth:`steam.ext.commands.Converter.register`.
    enabled: :class:`bool`
        Whether or not the command is enabled.
    cog: Optional[:class:`~steam.ext.commands.Cog`]
        The command's cog.
    parent: Optional[:class:`Command`]
        The command's parent.
    description: :class:`str`
        The command's description.
    hidden: :class:`bool`
        Whether or not the command is hidden.
    aliases: Iterable[:class:`str`]
        The command's aliases.
    params: dict[:class:`str`, :class:`inspect.Parameter`]
        The command's parameters.
    """

    DECORATORS: set[str] = {  # used in Cog._inject to update any unbound methods
        "on_error",
        "_before_hook",
        "_after_hook",
    }

    def __new__(cls: type[C], *args: Any, **kwargs: Any) -> C:
        self = super().__new__(cls)
        self.__original_kwargs__: dict[str, Any] = kwargs.copy()
        return self

    def __init__(self, func: CFT, **kwargs: Any):
        self.name: str = kwargs.get("name") or func.__name__
        if not isinstance(self.name, str):
            raise TypeError("name must be a string.")

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
            self.checks: list[CheckReturnType] = checks

        try:
            cooldown = func.__commands_cooldown__
        except AttributeError:
            cooldown = kwargs.get("cooldown", [])
        finally:
            self.cooldown: list[Cooldown] = cooldown

        try:
            special_converters = func.__special_converters__
        except AttributeError:
            special_converters = kwargs.get("special_converters", [])
        finally:
            self.special_converters: list[type[converters.Converter]] = special_converters

        self.enabled: bool = kwargs.get("enabled", True)
        self.brief: Optional[str] = kwargs.get("brief")
        self.usage: Optional[str] = kwargs.get("usage")
        self.cog: Optional[Union[Cog, Bot]] = kwargs.get("cog")
        self.parent: Optional[GroupMixin] = kwargs.get("parent")
        self.description: str = inspect.cleandoc(kwargs.get("description", ""))
        self.hidden: bool = kwargs.get("hidden", False)
        self.aliases: Iterable[str] = kwargs.get("aliases", ())

        for alias in self.aliases:
            if not isinstance(alias, str):
                raise TypeError("A commands aliases should be an iterable only containing strings")

        self._before_hook = None
        self._after_hook = None

    def __str__(self) -> str:
        return self.qualified_name

    @property
    def callback(self) -> CFT:
        """The internal callback the command holds."""
        return self._callback

    @callback.setter
    def callback(self, function: CFT) -> None:
        if not inspect.iscoroutinefunction(function):
            raise TypeError(f"The callback for the command {function.__name__!r} must be a coroutine function.")

        function = function.__func__ if inspect.ismethod(function) else function  # HelpCommand.command_callback

        annotations = get_type_hints(function)
        for name, annotation in annotations.items():
            if get_origin(annotation) is converters.Greedy and isinstance(annotation.converter, ForwardRef):
                annotations[name] = converters.Greedy[eval(annotation.converter.__forward_code__, function.__globals__)]

        function.__annotations__ = annotations

        self.params: dict[str, inspect.Parameter] = dict(inspect.signature(function).parameters)
        if not self.params:
            raise ClientException(f'Callback for {self.name} command is missing a "ctx" parameter.') from None

        self.module = function.__module__
        self._callback = function

    @cached_property
    def clean_params(self) -> dict[str, inspect.Parameter]:
        """dict[:class:`str`, :class:`inspect.Parameter`]: The command's parameters without ``"self"`` and ``"ctx"``."""
        params = self.params.copy()
        keys = list(params)
        if self.cog is not None:
            try:
                del params[keys.pop(0)]  # cog's "self" param
            except IndexError:
                raise ClientException(f'Callback for {self.name} command is missing a "self" parameter.') from None
        try:
            del params[keys.pop(0)]  # context param
        except IndexError:
            raise ClientException(f'Callback for {self.name} command is missing a "ctx" parameter.') from None
        return params

    @property
    def qualified_name(self) -> str:
        """:class:`str`: The full name of the command, this takes into account subcommands etc."""
        return " ".join(c.name for c in reversed(list(self.parents)))

    @property
    def parents(self: C) -> list[C]:
        """list[:class:`Command`]: The command's parents."""
        commands = []
        command = self
        while command is not None:
            if not isinstance(command, Command):
                break
            commands.append(command)
            command = command.parent

        return commands

    async def __call__(self, ctx: Context, *args: Any, **kwargs: Any) -> None:
        """|coro|
        Calls the internal callback that the command holds.

        Note
        ----
        This bypasses all mechanisms -- including checks, converters, invoke hooks, cooldowns, etc. You must take
        care to pass the proper arguments (excluding the parameter "self" in a cog context) and types to this
        function.
        """
        if self.cog is not None:
            return await self.callback(self.cog, ctx, *args, **kwargs)
        else:
            return await self.callback(ctx, *args, **kwargs)

    @overload
    def error(self, coro: Literal[None] = ...) -> Callable[[E], E]:
        ...

    @overload
    def error(self, coro: E) -> E:
        ...

    def error(self, coro: Optional[E] = None) -> Union[Callable[[E], E], E]:
        """|maybecallabledeco|
        Register a :term:`coroutine function` to handle a commands ``on_error`` functionality similarly to
        :meth:`steam.ext.commands.Bot.on_command_error`.

        Example: ::

            @bot.command
            async def raise_an_error(ctx: commands.Context) -> None:
                raise Exception("oh no an error")


            @raise_an_error.error
            async def on_error(ctx: commands.Context, error: Exception) -> None:
                await ctx.send(f"{ctx.command.name} raised an exception {error!r}")
        """

        def decorator(coro: E) -> E:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Error handler for {self.name} must be a coroutine function")
            self.on_error = coro
            return coro

        return decorator(coro) if coro is not None else decorator

    @overload
    def before_invoke(self, coro: Literal[None] = ...) -> Callable[[H], H]:
        ...

    @overload
    def before_invoke(self, coro: H) -> H:
        ...

    def before_invoke(self, coro: Optional[H] = None) -> Union[Callable[[H], H], H]:
        """|maybecallabledeco|
        Register a :term:`coroutine function` to be ran before any arguments are parsed.
        """

        def decorator(coro: H) -> H:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Hook for {self.name} must be a coroutine function")
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
        Register a :term:`coroutine function` to be ran after the command has been invoked.
        """

        def decorator(coro: H) -> H:
            if not inspect.iscoroutinefunction(coro):
                raise TypeError(f"Hook for {self.name} must be a coroutine function")
            self._after_hook = coro
            return coro

        return decorator(coro) if coro is not None else decorator

    async def invoke(self, ctx: Context) -> None:
        """|coro|
        Invoke the callback the command holds.

        Parameters
        ----------
        ctx: :class:`~steam.ext.commands.Context`
            The invocation context.
        """
        try:
            try:  # we mess with mentions in UserConverter.convert so we need to copy them for later
                mentions = ctx.message.mentions.ids.copy()
            except AttributeError:
                pass
            if not self.enabled:
                raise CommandDisabled(self)
            for check in ctx.bot.checks:
                if not await maybe_coroutine(check, ctx):
                    raise CheckFailure("You failed to pass one of the checks for this command")
            for check in self.checks:
                if not await maybe_coroutine(check, ctx):
                    raise CheckFailure("You failed to pass one of the checks for this command")
            for cooldown in self.cooldown:
                cooldown(ctx)
            await self._parse_arguments(ctx)
            await self._call_before_invoke(ctx)
            await self(ctx, *ctx.args, **ctx.kwargs)
        except asyncio.CancelledError:
            return
        except Exception:
            ctx.command_failed = True
            raise
        finally:
            try:
                ctx.message.mentions.ids = mentions
            except (UnboundLocalError, AttributeError):
                pass
            await self._call_after_invoke(ctx)

    async def can_run(self, ctx: Context) -> bool:
        """|coro|
        Whether or not the command can be ran.

        Parameters
        ----------
        ctx: :class:`~steam.ext.commands.Context`
            The invocation context.

        Returns
        -------
        :class:`bool`
        """
        if not self.enabled:
            return False
        for check in self.checks:
            if not await maybe_coroutine(check, ctx):
                return False
        for cooldown in self.cooldown:
            bucket = cooldown.bucket.get_bucket(ctx)
            retry_after = cooldown.get_retry_after(bucket, time())
            if retry_after:
                return False

        return True

    async def _call_before_invoke(self, ctx: Context) -> None:
        if self._before_hook is not None:
            await self._before_hook(ctx)
        if ctx.bot._before_hook is not None:
            await ctx.bot._before_hook(ctx)

    async def _call_after_invoke(self, ctx: Context) -> None:
        if self._after_hook is not None:
            await self._after_hook(ctx)
        if ctx.bot._after_hook is not None:
            await ctx.bot._after_hook(ctx)

    async def _parse_positional_or_keyword_argument(self, ctx: Context, param: inspect.Parameter, args: list) -> None:
        is_greedy = get_origin(param.annotation) is converters.Greedy
        greedy_args: list[Any] = []
        if ctx.lex.position == ctx.lex.end:
            args.append(await self._get_default(ctx, param))
        for argument in ctx.lex:
            try:
                transformed = await self._transform(ctx, param, argument)
            except BadArgument:
                if not is_greedy:
                    raise
                ctx.lex.undo()  # undo last read string for the next argument
                args.append(tuple(greedy_args))
                break
            if not is_greedy:
                args.append(transformed)
                break
            greedy_args.append(transformed)

    async def _parse_keyword_argument(self, ctx: Context, param: inspect.Parameter, kwargs: dict[str, Any]) -> None:
        kwargs[param.name] = await (  # kwarg only param denotes "consume rest" semantics
            self._transform(ctx, param, ctx.lex.rest) if ctx.lex.rest else self._get_default(ctx, param)
        )

    async def _parse_var_keyword_argument(self, ctx: Context, param: inspect.Parameter, kwargs: dict[str, Any]) -> None:
        kv_pairs = [arg.split("=") for arg in ctx.lex]
        if not kv_pairs:
            raise MissingRequiredArgument(param)  # defaults don't work here

        key_type, value_type = (
            (str, str) if param.annotation in (param.empty, dict) else get_args(param.annotation)
        )  # default to dict[str, str]

        key_converter = self._get_converter(key_type)
        value_converter = self._get_converter(value_type)
        try:
            for key_arg, value_arg in kv_pairs:
                if key_arg in kwargs:
                    raise DuplicateKeywordArgument(key_arg)
                kwargs.update(
                    {
                        await self._convert(ctx, key_converter, param, key_arg.strip()): await self._convert(
                            ctx, value_converter, param, value_arg.strip()
                        )
                    }
                )
        except ValueError:
            raise UnmatchedKeyValuePair("Unmatched key-value pair passed") from None

    async def _parse_var_position_argument(self, ctx: Context, param: inspect.Parameter, args: list) -> None:
        for arg in ctx.lex:
            transformed = await self._transform(ctx, param, arg)
            args.append(transformed)

    async def _parse_arguments(self, ctx: Context) -> None:
        args: list[Any] = []
        kwargs: dict[str, Any] = {}  # these are mutated by functions above

        for param in self.clean_params.values():
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                await self._parse_positional_or_keyword_argument(ctx, param, args)
            elif param.kind == param.KEYWORD_ONLY:
                await self._parse_keyword_argument(ctx, param, kwargs)
                break
            elif param.kind == param.VAR_KEYWORD:  # same as **kwargs
                await self._parse_var_keyword_argument(ctx, param, kwargs)
                break
            elif param.kind == param.VAR_POSITIONAL:  # same as *args
                await self._parse_var_position_argument(ctx, param, args)
                break

        ctx.args = tuple(args)
        ctx.kwargs = kwargs

    def _transform(self, ctx: Context, param: inspect.Parameter, argument: str) -> Coroutine[None, None, Any]:
        parm_type = self._prepare_param(param)
        converter = self._get_converter(parm_type)
        return self._convert(ctx, converter, param, argument)

    def _prepare_param(self, param: inspect.Parameter) -> type:
        converter = param.annotation
        if converter is param.empty:
            if param.default is not param.empty:
                converter = str if param.default is None else type(param.default)
            else:
                converter = str
        return converter

    def _get_converter(self, param_type: type) -> converters.Converters:
        converters_ = converters.CONVERTERS.get(param_type, param_type)
        if isinstance(converters_, tuple):
            if len(converters_) == 1 or not self.special_converters:
                return converters_[0]
            for converter in converters_:
                try:
                    idx = self.special_converters.index(converter)
                except ValueError:
                    pass
                else:
                    return self.special_converters[idx]
            return converters_[0]
        return converters_

    async def _convert(
        self,
        ctx: Context,
        converter: converters.Converters,
        param: inspect.Parameter,
        argument: str,
    ) -> Any:
        if isinstance(converter, converters.ConverterBase):
            if isinstance(converter, type):  # needs to be instantiated
                converter = converter()
            try:
                return await converter.convert(ctx, argument)
            except Exception as exc:
                try:
                    name = converter.__name__
                except AttributeError:
                    name = converter.__class__.__name__
                raise BadArgument(f"{argument!r} failed to convert to {name}") from exc
        origin = get_origin(converter)
        if origin is not None:
            args = get_args(converter)
            for arg in args:
                converter = self._get_converter(arg)
                try:
                    ret = await self._convert(ctx, converter, param, argument)
                except BadArgument:
                    if origin is Union:
                        continue
                    raise
                else:
                    if origin is not Literal:
                        return ret
                    if arg == ret:
                        return ret

            if origin is Union and args[-1] is type(None):  # typing.Optional
                try:
                    return self._get_default(ctx, param)  # get the default if possible
                except MissingRequiredArgument:
                    return None  # fall back to None
            if origin is Literal:
                raise BadArgument(f"Expected one of {', '.join(args)} not {argument!r}")

            raise BadArgument(f"Failed to parse {argument!r} to any type")

        try:
            return converter(argument)
        except Exception as exc:
            try:
                name = converter.__name__
            except AttributeError:
                name = converter.__class__.__name__
            raise BadArgument(f"{argument!r} failed to convert to {name}") from exc

    async def _get_default(self, ctx: Context, param: inspect.Parameter) -> Any:
        if param.default is param.empty:
            raise MissingRequiredArgument(param)
        if isinstance(param.default, converters.Default):
            try:
                default = param.default() if isinstance(param.default, type) else param.default
                return await default.default(ctx)
            except Exception as exc:
                try:
                    name = param.default.__name__
                except AttributeError:
                    name = param.default.__class__.__name__
                raise BadArgument(f"{name} failed to return a default argument") from exc
        return param.default


class GroupMixin:
    """Mixin for something that can have commands registered under it.

    Attributes
    ----------
    case_insensitive: :class:`bool`
        Whether or not commands should be invoke-able case insensitively.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        self.case_insensitive: bool = kwargs.get("case_insensitive", False)
        self.__commands__: dict[str, Command] = CaseInsensitiveDict() if self.case_insensitive else {}
        super().__init__(*args, **kwargs)

    @property
    def all_commands(self) -> list[Command]:
        """list[:class:`Command`]: A list of the loaded commands."""
        return list(self.__commands__.values())

    @property
    def commands(self) -> set[Command]:
        """set[:class:`Command`]: A set of the loaded commands without duplicates."""
        return set(self.__commands__.values())

    def add_command(self, command: Command) -> None:
        """Add a command to the internal commands list.

        Parameters
        ----------
        command: :class:`Command`
            The command to register.
        """
        if not isinstance(command, Command):
            raise TypeError("command should derive from commands.Command")

        if command.name in self.__commands__:
            raise ClientException(f"The command {command.name} is already registered.")

        for param in command.clean_params.values():
            if isinstance(param.annotation, str):
                raise ClientException(
                    f"Please rename the parameter {param.name} or make its annotation defined at runtime"
                )

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

        # fast path, no space in name
        if " " not in name:
            return self.__commands__.get(name)

        names = name.split()
        if not names:
            return None
        command = self.__commands__.get(names[0])
        if not isinstance(command, Group):
            return command

        for name in names[1:]:
            try:
                command = command.__commands__[name]
            except (AttributeError, KeyError):
                return None

        return command

    @overload
    def command(
        self,
        callback: CFT,
    ) -> C:
        ...

    @overload
    def command(
        self,
        *,
        name: Optional[str] = ...,
        cls: Optional[type[C]] = ...,
        help: Optional[str] = ...,
        brief: Optional[str] = ...,
        usage: Optional[str] = ...,
        description: Optional[str] = ...,
        aliases: Optional[Iterable[str]] = ...,
        checks: list[CheckReturnType] = ...,
        cooldown: list[Cooldown] = ...,
        special_converters: list[type[converters.Converters]] = ...,
        cog: Optional[Cog] = ...,
        parent: Optional[GroupMixin] = ...,
        enabled: bool = ...,
        hidden: bool = ...,
        case_insensitive: bool = ...,
    ) -> Callable[[CFT], C]:
        ...

    def command(
        self,
        callback: Optional[CFT] = None,
        *,
        name: Optional[str] = None,
        cls: Optional[type[C]] = None,
        **attrs: Any,
    ) -> Union[Callable[[CFT], C], C]:
        """|maybecallabledeco|
        A decorator that invokes :func:`command` and adds the created :class:`Command` to the internal command list.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the command. Will default to ``callback.__name__``.
        cls: type[:class:`Command`]
            The class to construct the command from. Defaults to :class:`Command`.
        **attrs:
            The attributes to pass to the command's ``__init__``.
        """

        def decorator(callback: CFT) -> C:
            attrs.setdefault("parent", self)
            result = command(callback, name=name, cls=cls or Command, **attrs)
            self.add_command(result)
            return result

        return decorator(callback) if callback is not None else decorator

    @overload
    def group(
        self,
        callback: CFT,
    ) -> G:
        ...

    @overload
    def group(
        self,
        *,
        name: Optional[str] = ...,
        cls: Optional[type[G]] = ...,
        help: Optional[str] = ...,
        brief: Optional[str] = ...,
        usage: Optional[str] = ...,
        description: Optional[str] = ...,
        aliases: Optional[Iterable[str]] = ...,
        checks: list[CheckReturnType] = ...,
        cooldown: list[Cooldown] = ...,
        special_converters: list[type[converters.Converters]] = ...,
        cog: Optional[Cog] = ...,
        parent: Optional[GroupMixin] = ...,
        enabled: bool = ...,
        hidden: bool = ...,
        case_insensitive: bool = ...,
    ) -> Callable[[CFT], G]:
        ...

    def group(
        self,
        callback: Optional[CFT] = None,
        *,
        name: Optional[str] = None,
        cls: Optional[type[G]] = None,
        **attrs: Any,
    ) -> Union[Callable[[CFT], G], G]:
        """|maybecallabledeco|
        A decorator that invokes :func:`group` and adds the created :class:`Group` to the internal command list.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the command. Will default to ``callback.__name__``.
        cls: type[:class:`Group`]
            The class to construct the command from. Defaults to :class:`Group`.
        **attrs:
            The attributes to pass to the command's ``__init__``.
        """

        def decorator(callback: CFT) -> G:
            attrs.setdefault("parent", self)
            result = group(callback, name=name, cls=cls or Group, **attrs)
            self.add_command(result)
            return result

        return decorator(callback) if callback is not None else decorator

    @property
    def children(self: C) -> list[C]:
        """list[:class:`Command`]: The commands children."""
        commands = []
        for command in self.commands:
            commands.append(command)
            if isinstance(command, Group):
                commands.extend(command.children)

        return commands

    def recursively_remove_all_commands(self) -> None:
        for command in self.commands:
            if isinstance(command, GroupMixin):
                command.recursively_remove_all_commands()
            self.remove_command(command.name)


class Group(GroupMixin, Command):
    def __init__(self, func: CommandFunctionType, **kwargs: Any):
        super().__init__(func, **kwargs)

    async def invoke(self, ctx: Context) -> None:
        command = self
        for command_name in ctx.lex:
            try:
                command = command.__commands__[command_name]
            except (AttributeError, KeyError):
                ctx.lex.undo()
                break

        await (super().invoke(ctx) if command is self else command.invoke(ctx))


@overload
def command(
    callback: CFT,
) -> C:
    ...


@overload
def command(
    *,
    name: Optional[str] = ...,
    cls: Optional[type[C]] = ...,
    help: Optional[str] = ...,
    brief: Optional[str] = ...,
    usage: Optional[str] = ...,
    description: Optional[str] = ...,
    aliases: Optional[Iterable[str]] = ...,
    checks: list[CheckReturnType] = ...,
    cooldown: list[Cooldown] = ...,
    special_converters: list[type[converters.Converters]] = ...,
    cog: Optional[Cog] = ...,
    parent: Optional[Command] = ...,
    enabled: bool = ...,
    hidden: bool = ...,
    case_insensitive: bool = ...,
) -> Callable[[CFT], C]:
    ...


def command(
    callback: Optional[CFT] = None,
    *,
    name: Optional[str] = None,
    cls: Optional[type[C]] = None,
    **attrs: Any,
) -> Union[Callable[[CFT], C], C]:
    """|maybecallabledeco|
    A decorator that registers a :term:`coroutine function` as a :class:`Command`.

    Parameters
    ----------
    name: Optional[:class:`str`]
        The name of the command. Will default to ``callback.__name__``.
    cls: type[:class:`Command`]
        The class to construct the command from. Defaults to :class:`Command`.
    **attrs:
        The attributes to pass to the command's ``__init__``.
    """
    cls = cls or Command

    def decorator(callback: CFT) -> C:
        if isinstance(callback, Command):
            raise TypeError("callback is already a command.")
        return cls(callback, name=name, **attrs)

    return decorator(callback) if callback is not None else decorator


@overload
def group(
    callback: CFT,
) -> G:
    ...


@overload
def group(
    *,
    name: Optional[str] = ...,
    cls: Optional[type[G]] = ...,
    help: Optional[str] = ...,
    brief: Optional[str] = ...,
    usage: Optional[str] = ...,
    description: Optional[str] = ...,
    aliases: Optional[Iterable[str]] = ...,
    checks: list[CheckReturnType] = ...,
    cooldown: list[Cooldown] = ...,
    special_converters: list[type[converters.Converters]] = ...,
    cog: Optional[Cog] = ...,
    parent: Optional[Command] = ...,
    enabled: bool = ...,
    hidden: bool = ...,
    case_insensitive: bool = ...,
) -> Callable[[CFT], G]:
    ...


def group(
    callback: Optional[CFT] = None,
    *,
    name: Optional[str] = None,
    cls: Optional[type[G]] = None,
    **attrs: Any,
) -> Union[Callable[[CFT], G], G]:
    """|maybecallabledeco|
    A decorator that registers a :term:`coroutine function` as a :class:`Group`.

    Parameters
    ----------
    name: Optional[:class:`str`]
        The name of the command. Will default to ``callback.__name__``.
    cls: type[:class:`Group`]
        The class to construct the command from. Defaults to :class:`Group`.
    **attrs:
        The attributes to pass to the command's ``__init__``.
    """

    return command(callback, name=name, cls=cls or Group, **attrs)


def check(predicate: CheckType) -> CheckReturnType:
    """
    A decorator that registers a function that *could be a* |coroutine_link|_ as a check to a command.

    They should take a singular argument representing the :class:`~steam.ext.commands.Context` for the message.

    Examples
    --------
    .. code-block::

        def is_mod(ctx: commands.Context) -> bool:
            return ctx.clan and ctx.author in ctx.clan.mods

        @commands.check(is_mod)
        @bot.command
        async def kick(ctx: commands.Context, user: steam.User) -> None:
            ...

    This will raise an :exc:`steam.ext.commands.CheckFailure` if the user is not an a mod in the clan.

    Attributes
    ----------
    predicate: Callable[[:class:`Context`], Awaitable[:class:`bool`]]
        The registered check, this will always be a wrapped in a :term:`coroutine function`
    """

    def decorator(func: MC) -> MC:
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
        async def wrapper(ctx: Context) -> bool:
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


@overload
def is_owner(command: Literal[None] = ...) -> MCD:
    ...


@overload
def is_owner(command: MCD) -> MCD:
    ...


def is_owner(command: Optional[MCD] = None) -> MCD:
    """|maybecallabledeco|
    A decorator that will only allow the bot's owner(s) to invoke the command.

    Warning
    -------
    This relies on :attr:`~steam.ext.commands.Bot.owner_id` or :attr:`~steam.ext.commands.Bot.owner_ids` to be set to
    function if they are not no one will be able to use these commands.
    """

    def predicate(ctx: Context) -> bool:
        if ctx.bot.owner_id and ctx.author.id64 == ctx.bot.owner_id:
            return True
        if ctx.bot.owner_ids and ctx.author.id64 in ctx.bot.owner_ids:
            return True
        raise NotOwner()

    decorator = check(predicate)
    return decorator(command) if command is not None else decorator


@overload
def dm_only(command: Literal[None] = ...) -> MCD:
    ...


@overload
def dm_only(command: MCD) -> MCD:
    ...


def dm_only(command: Optional[MCD] = None) -> MCD:
    """|maybecallabledeco|
    A decorator that will make a command only invokable in a :class:`steam.DMChannel`.
    """

    def predicate(ctx: Context) -> bool:
        if isinstance(ctx.channel, DMChannel):
            return True

        raise DMChannelOnly()

    decorator = check(predicate)
    return decorator(command) if command is not None else decorator


def cooldown(rate: int, per: float, type: BucketType = BucketType.Default) -> CommandDeco:
    """Give a :class:`Command`'s a cooldown.

    Parameters
    ----------
    rate: :class:`int`
        The amount of times a command can be executed
        before being put on cooldown.
    per: :class:`float`
        The amount of time to wait between cooldowns.
    type: :class:`.BucketType`
        The :class:`.BucketType` that the cooldown applies to.

    Examples
    --------
    Usage::

        @bot.command
        @commands.cooldown(rate=1, per=10, commands.BucketType.User)
        async def once_every_ten_seconds(ctx: commands.Context) -> None:
            ...

    This can only be invoked a user every ten seconds.
    """

    def decorator(command: MC) -> MC:
        if isinstance(command, Command):
            command.cooldown.append(Cooldown(rate, per, type))
        else:
            if not hasattr(command, "__commands_cooldown__"):
                command.__commands_cooldown__ = []
            command.__commands_cooldown__.append(Cooldown(rate, per, type))
        return command

    return decorator
