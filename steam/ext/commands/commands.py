"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of
https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/core.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import itertools
from collections.abc import Callable, Coroutine, Iterable, Sequence
from time import time
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    ForwardRef,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)

import typing_extensions
from typing_extensions import ParamSpec, Self, TypedDict, TypeVar, Unpack

from ...channel import UserChannel
from ...chat import Chat
from ...utils import cached_property, maybe_coroutine
from . import converters
from .context import Context
from .cooldown import BucketType, Cooldown
from .errors import *
from .utils import CaseInsensitiveDict, Coro

if TYPE_CHECKING:
    from .bot import Bot
    from .cog import Cog

__all__ = (
    "Command",
    "command",
    "Group",
    "group",
    "check",
    "is_owner",
    "cooldown",
)

P = ParamSpec("P", default=...)
R = TypeVar("R", default=Any, covariant=True)


MaybeCoroFunc: TypeAlias = Callable[P, R | Coro[R]]
CoroFunc: TypeAlias = Callable[P, Coro[R]]
CheckType: TypeAlias = MaybeCoroFunc[["Context"], bool]
ErrT = TypeVar("ErrT", bound=CoroFunc[["Context", Exception], None] | CoroFunc[["Cog", "Context", Exception], None])
InvokeT = TypeVar("InvokeT", bound=CoroFunc[["Context"], None] | CoroFunc[["Cog", "Context"], None])
MaybeCommandT = TypeVar("MaybeCommandT", bound="Callable[..., Command] | Command")
CoroFuncT = TypeVar("CoroFuncT", bound=CoroFunc)


class CommandDeco(Protocol):
    def __call__(self, command: MaybeCommandT, /) -> MaybeCommandT:
        ...


MaybeBool = TypeVar("MaybeBool", bound=bool | Coro[bool], default=bool | Coro[bool], covariant=True)


class Check(Protocol[MaybeBool]):
    predicate: Callable[[Context[Any]], Coro[bool]]

    @overload
    def __call__(self, context: Context[Any], /) -> MaybeBool:
        ...

    @overload
    def __call__(self, command: MaybeCommandT, /) -> MaybeCommandT:
        ...


@converters.converter
def to_bool(argument: str) -> bool:
    lowered = argument.lower()
    if lowered in {"yes", "y", "true", "t", "1", "enable", "on"}:
        return True
    elif lowered in {"no", "n", "false", "f", "0", "disable", "off"}:
        return False
    raise BadArgument(f"{argument!r} is not a recognised boolean option")


class CommandKwargsNoCls(TypedDict, total=False):
    name: str | None
    help: str
    brief: str
    usage: str
    description: str
    aliases: Iterable[str]
    checks: list[Check]
    cooldown: list[Cooldown]
    special_converters: list[converters.Converters]
    cog: Cog
    parent: GroupMixin | Group[Any]
    enabled: bool
    hidden: bool
    case_insensitive: bool


C = TypeVar("C", bound="Command", default="Command")


class CommandKwargs(CommandKwargsNoCls, Generic[C], total=False):
    cls: type[C] | None


CogT = TypeVar("CogT", bound="Cog | Bot | None", default="Cog | Bot | None", covariant=True)


class Command(Generic[CogT, P, R]):
    """A class to represent a command.

    Attributes
    ----------
    name
        The command's name.
    help
        The command's help docstring.
    checks
        A list of the command's checks.
    cooldown
        The command's cooldowns.
    special_converters
        A list of the command's special converters as registered by :meth:`steam.ext.commands.Converter.register`.
    enabled
        Whether the command is enabled.
    cog
        The command's cog.
    parent
        The command's parent.
    description
        The command's description.
    hidden
        Whether the command is hidden.
    aliases
        The command's aliases.
    params
        The command's parameters.
    """

    __original_kwargs__: dict[str, Any]

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        self = super().__new__(cls)
        self.__original_kwargs__ = kwargs.copy()
        return self

    def __init__(
        self,
        func: CoroFunc[Concatenate[CogT, Context[Any], P], R] | CoroFunc[Concatenate[Context[Any], P], R],
        /,
        **kwargs: Unpack[CommandKwargs],
    ):
        self.name = kwargs.get("name") or func.__name__
        self.callback = func

        help_doc = kwargs.get("help")
        self.help: str | None = inspect.cleandoc(help_doc) if help_doc is not None else inspect.getdoc(func)

        try:
            checks = func.__commands_checks__  # type: ignore
            checks.reverse()
        except AttributeError:
            checks = kwargs.get("checks", [])
        self.checks: list[Check] = checks

        try:
            cooldown = func.__commands_cooldown__  # type: ignore
        except AttributeError:
            cooldown = kwargs.get("cooldown", [])
        self.cooldown: list[Cooldown] = cooldown

        try:
            special_converters: list[converters.Converters] = func.__special_converters__  # type: ignore
        except AttributeError:
            special_converters = kwargs.get("special_converters", [])
        self.special_converters = special_converters

        self.enabled = kwargs.get("enabled", True)
        self.brief = kwargs.get("brief")
        self.usage = kwargs.get("usage")
        self.cog: Cog | Bot | None = None
        self.parent: GroupMixin | Group[CogT] | None = kwargs.get("parent")
        self.description: str = inspect.cleandoc(kwargs.get("description", ""))
        self.hidden: bool = kwargs.get("hidden", False)
        self.aliases: Sequence[str] = list(kwargs.get("aliases", ()))

        self._before_hook = None
        self._after_hook = None

    def __str__(self) -> str:
        return self.qualified_name

    # @property
    # @overload
    # def callback(
    #     self: Command[None, Concatenate[Context[Any], P], R]
    # ) -> Callable[Concatenate[Context[Any], P], Coro[R]]:
    #     ...

    # @property
    # @overload
    # def callback(
    #     self: Command[CogT, Concatenate[CogT, Context[Any], P], R]
    # ) -> Callable[Concatenate[CogT, Context[Any], P], Coro[R]]:
    #     ...

    @property
    def callback(
        self,
    ) -> Callable[Concatenate[CogT, Context[Any], P], Coro[R]] | Callable[Concatenate[Context[Any], P], Coro[R]]:
        """The internal callback the command holds."""
        return self._callback

    @callback.setter
    def callback(
        self,
        function: (
            Callable[Concatenate[CogT, Context[Any], P], Coro[R]] | Callable[Concatenate[Context[Any], P], Coro[R]]
        ),
    ) -> None:
        if not inspect.iscoroutinefunction(function):
            raise TypeError(f"The callback for the command {function.__name__!r} must be a coroutine function.")

        annotations = typing_extensions.get_type_hints(function)
        for name, annotation in annotations.items():
            if get_origin(annotation) is converters.Greedy and isinstance(annotation.converter, ForwardRef):
                annotations[name] = converters.Greedy[eval(annotation.converter.__forward_code__, function.__globals__)]

        if inspect.ismethod(function):
            function.__func__.__annotations__ = annotations
        else:
            function.__annotations__ = annotations
        self.params = dict(inspect.signature(function, eval_str=True).parameters)
        if not self.params:
            raise TypeError(f'Callback for {self.name} command is missing a "ctx" parameter.') from None

        self.module = function.__module__
        self._callback = function

    @cached_property
    def clean_params(self) -> dict[str, inspect.Parameter]:
        """The command's parameters without ``"self"`` and ``"ctx"``."""
        params = iter(self.params.items())
        if self.cog is not None:
            try:
                next(params)  # cog's "self" param
            except StopIteration:
                raise TypeError(f'Callback for {self.name} command is missing a "self" parameter.') from None
        try:
            next(params)  # context param
        except StopIteration:
            raise TypeError(f'Callback for {self.name} command is missing a "ctx" parameter.') from None
        return dict(params)

    @property
    def qualified_name(self) -> str:
        """The full name of the command, this takes into account subcommands."""
        return " ".join(c.name for c in reversed(self.parents))

    @property
    def parents(self) -> list[Self]:
        """The command's parents."""
        commands: list[Self] = []
        command = self
        while isinstance(command, Command):
            commands.append(command)
            command = command.parent

        return commands

    async def __call__(self, ctx: Context, *args: P.args, **kwargs: P.kwargs) -> R:
        """Calls the internal callback that the command holds.

        Note
        ----
        This bypasses all mechanisms -- including checks, converters, invoke hooks, cooldowns, etc. You must take
        care to pass the proper arguments (excluding the parameter "self" in a cog context) and types to this
        function.
        """
        if self.cog is not None:
            return await self.callback(self.cog, ctx, *args, **kwargs)  # type: ignore
        else:
            return await self.callback(ctx, *args, **kwargs)  # type: ignore

    def error(self, coro: ErrT) -> ErrT:
        """A decorator to register a :term:`coroutine function` to handle a commands ``on_error`` functionality
        similarly to :meth:`steam.ext.commands.Bot.on_command_error`.

        Example:

        .. code:: python

            @bot.command
            async def raise_an_error(ctx: commands.Context) -> None:
                raise Exception("oh no an error")


            @raise_an_error.error
            async def on_error(ctx: commands.Context, error: Exception) -> None:
                await ctx.send(f"{ctx.command.name} raised an exception {error!r}")
        """

        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Error handler for {self.name} must be a coroutine function")
        self.on_error = coro
        return coro

    def before_invoke(self, coro: InvokeT) -> InvokeT:
        """Register a :term:`coroutine function` to be run before any arguments are parsed."""

        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Hook for {self.name} must be a coroutine function")
        self._before_hook = coro
        return coro

    def after_invoke(self, coro: InvokeT) -> InvokeT:
        """Register a :term:`coroutine function` to be run after the command has been invoked."""

        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Hook for {self.name} must be a coroutine function")
        self._after_hook = coro
        return coro

    async def invoke(self, ctx: Context) -> None:
        """Invoke the callback the command holds.

        Parameters
        ----------
        ctx
            The invocation context.
        """
        try:
            if not self.enabled:
                raise CommandDisabled(self)
            for check in itertools.chain(ctx.bot.checks, self.checks):
                if not await check.predicate(ctx):
                    raise CheckFailure("You failed to pass one of the checks for this command")
            for cooldown in self.cooldown:
                cooldown(ctx)
            await self._parse_arguments(ctx)
            await self._call_before_invoke(ctx)
            assert ctx.args is not None
            assert ctx.kwargs is not None
            await self(ctx, *ctx.args, **ctx.kwargs)
        except asyncio.CancelledError:
            return
        except Exception:
            ctx.command_failed = True
            raise
        finally:
            await self._call_after_invoke(ctx)

    async def can_run(self, ctx: Context) -> bool:
        """Whether the command can be run.

        Parameters
        ----------
        ctx
            The invocation context.
        """
        if not self.enabled:
            return False
        for check in self.checks:
            if not await maybe_coroutine(check, ctx):
                return False
        for cooldown in self.cooldown:
            bucket = cooldown.bucket.get_bucket(ctx)
            if cooldown.get_retry_after(bucket, time()):
                return False

        return True

    async def _call_before_invoke(self, ctx: Context) -> None:
        if self._before_hook is not None:
            if self.cog is not None:
                await self._before_hook(self.cog, ctx)  # type: ignore
            else:
                await self._before_hook(ctx)  # type: ignore
        if ctx.bot._before_hook is not None:
            await ctx.bot._before_hook(ctx)

    async def _call_after_invoke(self, ctx: Context) -> None:
        if self._after_hook is not None:
            if self.cog is not None:
                await self._after_hook(self.cog, ctx)  # type: ignore
            else:
                await self._after_hook(ctx)  # type: ignore
        if ctx.bot._after_hook is not None:
            await ctx.bot._after_hook(ctx)

    async def _parse_positional_or_keyword_argument(
        self, ctx: Context, param: inspect.Parameter, args: list[Any]
    ) -> None:
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
                kwargs[await self._convert(ctx, key_converter, param, key_arg.strip())] = await self._convert(
                    ctx, value_converter, param, value_arg.strip()
                )

        except ValueError:
            raise UnmatchedKeyValuePair("Unmatched key-value pair passed") from None

    async def _parse_var_position_argument(self, ctx: Context, param: inspect.Parameter, args: list[Any]) -> None:
        for arg in ctx.lex:
            transformed = await self._transform(ctx, param, arg)
            args.append(transformed)

    async def _parse_arguments(self, ctx: Context) -> None:
        args: list[Any] = []
        kwargs: dict[str, Any] = {}  # these are mutated by functions above

        for param in self.clean_params.values():
            ctx.current_param = param
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
        if isinstance(converters_, list):
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
        if isinstance(converter, type) and issubclass(converter, converters.ConverterBase):
            converter = converter()
        if isinstance(converter, converters.ConverterBase):
            try:
                return await converter.convert(ctx, argument)
            except Exception as exc:
                raise BadArgument(f"{argument!r} failed to convert to {converter.__class__.__name__}") from exc
        origin = get_origin(converter)
        if origin is not None:
            args = get_args(converter)
            for arg in args:
                converter = self._get_converter(arg)
                try:
                    ret = await self._convert(ctx, converter, param, argument)
                except BadArgument:
                    if origin not in (Union, UnionType):
                        raise
                else:
                    if origin is not Literal:
                        return ret
                    if arg == ret:
                        return ret

            if origin in (Union, UnionType) and args[-1] is type(None):  # typing.Optional
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
                name = converter.__name__  # type: ignore
            except AttributeError:
                name = converter.__class__.__name__
            raise BadArgument(f"{argument!r} failed to convert to {name}") from exc

    async def _get_default(self, ctx: Context, param: inspect.Parameter) -> Any:
        default = param.default
        if default is param.empty:
            raise MissingRequiredArgument(param)
        if isinstance(default, type) and issubclass(default, converters.ConverterBase):
            default = default()
        if isinstance(default, converters.Default):
            try:
                return await default.default(ctx)
            except Exception as exc:
                raise BadArgument(f"{param.default.__class__.__name__} failed to return a default argument") from exc
        return default


CallbackT: TypeAlias = CoroFunc[Concatenate[CogT, Context[Any], P], R] | CoroFunc[Concatenate[Context[Any], P], R]


class GroupMixin(Generic[CogT]):
    """Mixin for something that can have commands registered under it.

    Attributes
    ----------
    case_insensitive
        Whether commands should be invoke-able case insensitively.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        self.case_insensitive: bool = kwargs.get("case_insensitive", False)
        self.__commands__: dict[str, Command[CogT]] = CaseInsensitiveDict() if self.case_insensitive else {}
        super().__init__(*args, **kwargs)

    @property
    def all_commands(self) -> list[Command[CogT]]:
        """A list of the loaded commands."""
        return list(self.__commands__.values())

    @property
    def commands(self) -> set[Command[CogT]]:
        """A set of the loaded commands without duplicates."""
        return set(self.__commands__.values())

    @property
    def children(self) -> Sequence[Command[CogT]]:
        """The commands children."""
        commands = list[Command[CogT]]()
        for command in self.commands:
            commands.append(command)
            if isinstance(command, Group):
                commands += command.children

        return commands

    def add_command(self, command: Command[CogT]) -> None:
        """Add a command to the internal commands list.

        Parameters
        ----------
        command
            The command to register.
        """
        if not isinstance(command, Command):
            raise TypeError("command should derive from commands.Command")

        if command.name in self.__commands__:
            raise ValueError(f"The command {command.name} is already registered.")

        for param in command.clean_params.values():
            if isinstance(param.annotation, str):
                raise TypeError(f"Please rename the parameter {param.name} or make its annotation defined at runtime")

        self.__commands__[command.name] = command
        for alias in command.aliases:
            if alias in self.__commands__:
                self.remove_command(command.name)
                raise ValueError(f"{alias} is already an existing command or alias.")
            self.__commands__[alias] = command

    def remove_command(self, name: str) -> Command[CogT] | None:
        """Remove a command from the internal commands list.

        Parameters
        ----------
        name
            The name of the command to remove.

        Returns
        --------
        The removed command or ``None`` if the command was not found.
        """
        try:
            command = self.__commands__.pop(name)
        except ValueError:
            return None

        for alias in command.aliases:
            del self.__commands__[alias]
        return command

    def get_command(self, name: str) -> Command[CogT] | None:
        """Get a command.

        Parameters
        ----------
        name
            The name of the command.

        Returns
        -------
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
                command = command.__commands__[name]  # type: ignore
            except (AttributeError, KeyError):
                return None

        return command

    @overload
    def command(self, callback: CallbackT[CogT, P, R], /) -> Command[CogT, P, R]:
        ...

    @overload  # this needs higher kinded types as cls should be type[C[P]] | None
    def command(
        self, **kwargs: Unpack[CommandKwargsNoCls]
    ) -> Callable[[CallbackT[CogT, P, R]], Command[CogT, P, R],]:
        ...

    @overload  # this also needs higher kinded types as cls should be type[C[P]] | None
    def command(self, **kwargs: Unpack[CommandKwargs[C]]) -> Callable[[CallbackT[CogT, P, R]], C]:
        ...

    def command(  # type: ignore
        self,
        callback: CoroFuncT | None = None,
        /,
        *,
        name: str | None = None,
        cls: type[C] = Command,
        **attrs: Any,
    ) -> Callable[[CoroFuncT], C] | C:
        """|maybecallabledeco|
        A decorator that invokes :func:`command` and adds the created :class:`Command` to the internal command list.

        Parameters
        ----------
        name
            The name of the command. Will default to ``callback.__name__``.
        cls: type[:class:`Command`]
            The class to construct the command from. Defaults to :class:`Command`.
        attrs
            The parameters to pass to the command's ``__init__``.

        Returns
        -------
        The created command.
        """

        def decorator(callback: CoroFuncT) -> C:
            attrs.setdefault("parent", self)
            result = command(name=name, cls=cls, **attrs)(callback)
            self.add_command(result)  # type: ignore
            return result

        return decorator(callback) if callback is not None else decorator

    @overload
    def group(self, callback: CallbackT[CogT, P, R], /) -> Group[CogT, P, R]:
        ...

    @overload
    def group(self, **kwargs: Unpack[CommandKwargsNoCls]) -> Callable[[CallbackT[CogT, P, R]], Group[CogT, P, R]]:
        ...

    @overload
    def group(self, **kwargs: Unpack[CommandKwargs[G]]) -> Callable[[CallbackT[CogT, P, R]], G]:
        ...

    def group(  # type: ignore
        self,
        callback: CoroFuncT | None = None,
        /,
        *,
        name: str | None = None,
        cls: type[G] | None = None,
        **attrs: Any,
    ) -> Callable[[CoroFuncT], G] | G:
        """A decorator that invokes :func:`group` and adds the created :class:`Group` to the internal command list.

        Parameters
        ----------
        name
            The name of the command. Will default to ``callback.__name__``.
        cls: type[:class:`Group`]
            The class to construct the command from. Defaults to :class:`Group`.
        attrs
            The parameters to pass to the command's ``__init__``.

        Returns
        -------
        The created group command.
        """

        def decorator(callback: CoroFuncT) -> G:
            attrs.setdefault("parent", self)
            result = group(name=name, cls=cls or Group, **attrs)(callback)
            self.add_command(result)
            return cast(G, result)  # casting shouldn't really be necessary

        return decorator(callback) if callback is not None else decorator

    def remove_all_commands(self) -> None:
        for command in self.commands:
            if isinstance(command, GroupMixin):
                command.remove_all_commands()
            self.remove_command(command.name)


class Group(GroupMixin[CogT], Command[CogT, P, R]):
    pass


@overload
def command(callback: CallbackT[CogT, P, R], /) -> Command[CogT, P, R]:
    ...


@overload
def command(**kwargs: Unpack[CommandKwargsNoCls]) -> Callable[[CallbackT[CogT, P, R]], Command[CogT, P, R]]:
    ...


@overload
def command(**kwargs: Unpack[CommandKwargs[C]]) -> Callable[[CallbackT[CogT, P, R]], C]:
    ...


def command(  # type: ignore
    callback: CoroFuncT | None = None,
    /,
    *,
    name: str | None = None,
    cls: type[C] = Command,
    **attrs: Any,
) -> Callable[[CoroFuncT], C] | C:
    """|maybecallabledeco|
    A decorator that turns a :term:`coroutine function` into a :class:`Command`.

    Parameters
    ----------
    name
        The name of the command. Will default to ``callback.__name__``.
    cls: type[:class:`Command`]
        The class to construct the command from. Defaults to :class:`Command`.
    attrs
        The attributes to pass to the command's ``__init__``.

    Returns
    -------
    The created command.
    """
    cls = cls or Command

    def decorator(callback: CoroFuncT) -> C:
        if isinstance(callback, Command):
            raise TypeError("callback is already a command.")
        return cls(callback, name=name, **attrs)

    return decorator(callback) if callback is not None else decorator


G = TypeVar("G", bound="Group[Any]", default="Group[Any]")


@overload
def group(callback: CallbackT[CogT, P, R], /) -> Group[CogT, P, R]:
    ...


@overload
def group(**kwargs: Unpack[CommandKwargsNoCls]) -> Callable[[CallbackT[CogT, P, R]], Group[CogT, P, R]]:
    ...


@overload
def group(**kwargs: Unpack[CommandKwargs[G]]) -> Callable[[CallbackT[CogT, P, R]], G]:
    ...


def group(
    callback: CoroFuncT | None = None,
    /,
    *,
    name: str | None = None,
    cls: type[G] | None = None,
    **attrs: Any,
) -> Callable[[CoroFuncT], G] | G:
    """|maybecallabledeco|
    A decorator that turns a :term:`coroutine function` into a :class:`Group`.

    Parameters
    ----------
    name
        The name of the command. Will default to ``callback.__name__``.
    cls: type[:class:`Group`]
        The class to construct the command from. Defaults to :class:`Group`.
    attrs
        The attributes to pass to the command's ``__init__``.

    Returns
    -------
    The created group command.
    """
    return command(callback, name=name, cls=cls or Group, **attrs)  # type: ignore


def check(predicate: Callable[[Context], MaybeBool]) -> Check[MaybeBool]:
    """
    A decorator that registers a function that *could be a* |coroutine_link|_ as a check to a command.

    They should take a singular argument representing the :class:`~steam.ext.commands.Context` for the message.

    Examples
    --------
    .. code:: python

        @commands.check
        def is_mod(ctx: commands.Context) -> bool:
            return ctx.clan and ctx.author in ctx.clan.mods


        @is_mod
        @bot.command
        async def kick(ctx: commands.Context, user: steam.User) -> None:
            ...

    This will raise an :exc:`steam.ext.commands.CheckFailure` if the user is not an a mod in the clan.

    Attributes
    ----------
    predicate
        The registered check, this will always be a :term:`coroutine function` even if the original check wasn't.
    """

    @overload
    def inner(func: Context, /) -> MaybeBool:
        ...

    @overload
    def inner(func: MaybeCommandT, /) -> MaybeCommandT:
        ...

    @functools.partial(cast, Check[MaybeBool])
    def inner(func: Context | MaybeCommandT, /) -> MaybeBool | MaybeCommandT:
        if isinstance(func, Context):
            return predicate(func)
        elif isinstance(func, Command):
            func.checks.append(inner)
        else:
            if not hasattr(func, "__commands_checks__"):
                func.__commands_checks__ = [inner]  # type: ignore
            else:
                func.__commands_checks__.append(inner)  # type: ignore

        return func

    if inspect.iscoroutinefunction(predicate):
        inner.predicate = predicate
    else:

        @functools.wraps(predicate)
        async def wrapper(ctx: Context) -> bool:
            return predicate(ctx)  # type: ignore

        inner.predicate = wrapper

    return inner


@check
def is_owner(ctx: Context) -> bool:
    """
    A decorator that will only allow the bot's owner(s) to invoke the command.

    Warning
    -------
    This relies on :attr:`~steam.ext.commands.Bot.owner_id` or :attr:`~steam.ext.commands.Bot.owner_ids` to be set to
    function if they are not no one will be able to use these commands.
    """

    if ctx.author.id64 == ctx.bot.owner_id or ctx.author.id64 in ctx.bot.owner_ids:
        return True
    raise NotOwner()


@check
def chat_only(ctx: Context) -> bool:
    """A decorator that will make a command only invokable in a :class:`steam.Chat`."""

    if isinstance(ctx.channel, Chat):
        return True

    raise ChatOnly()


@check
def dm_only(ctx: Context) -> bool:
    """A decorator that will make a command only invokable in a :class:`steam.UserChannel`."""

    if isinstance(ctx.channel, UserChannel):
        return True

    raise UserChannelOnly()


def cooldown(rate: int, per: float, type: BucketType = BucketType.Default) -> CommandDeco:
    """Give a :class:`Command`'s a cooldown.

    Parameters
    ----------
    rate
        The amount of times a command can be executed
        before being put on cooldown.
    per
        The amount of time to wait between cooldowns.
    type
        The bucket that the cooldown applies to.

    Examples
    --------
    Usage

    .. code:: python

        @bot.command
        @commands.cooldown(rate=1, per=10, type=commands.BucketType.User)
        async def once_every_ten_seconds(ctx: commands.Context) -> None:
            ...  # this can only be invoked a user every ten seconds.
    """

    def decorator(command: MaybeCommandT) -> MaybeCommandT:
        if isinstance(command, Command):
            command.cooldown.append(Cooldown(rate, per, type))
        else:
            if not hasattr(command, "__commands_cooldown__"):
                command.__commands_cooldown__ = []  # type: ignore
            command.__commands_cooldown__.append(Cooldown(rate, per, type))  # type: ignore
        return command

    return decorator
