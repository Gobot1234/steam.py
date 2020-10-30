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

from __future__ import annotations

import asyncio
import functools
import inspect
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Optional,
    OrderedDict,
    Union,
    get_type_hints,
    overload,
)

from chardet import detect
from typing_extensions import Literal, get_args, get_origin

from ...errors import ClientException
from ...models import FunctionType
from ...utils import cached_property, maybe_coroutine
from . import converters
from .cooldown import BucketType, Cooldown
from .errors import (
    BadArgument,
    CheckFailure,
    CommandDisabled,
    CommandOnCooldown,
    DuplicateKeywordArgument,
    MissingRequiredArgument,
    NotOwner,
    UnmatchedKeyValuePair,
)
from .utils import CaseInsensitiveDict, reload_module_with_TYPE_CHECKING

if TYPE_CHECKING:
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

CheckType = Callable[["Context"], Union[bool, Coroutine[Any, Any, bool]]]
MaybeCommand = Union[Callable[..., "Command"], "CommandFunctionType"]
MaybeCommandDeco = Union["CommandDeco", MaybeCommand]
CommandErrorFunctionType = Callable[["Context", Exception], Coroutine[Any, Any, None]]
HookFunction = Callable[["Context"], Coroutine[Any, Any, None]]
HookDecoType = Union[Callable[["HookFunction"], "HookFunction"], "HookFunction"]


class CommandDeco(FunctionType):
    def __call__(self, func: MaybeCommand) -> MaybeCommand:
        ...


class CheckReturnType(CommandDeco):
    predicate: CheckType


class CommandFunctionType(FunctionType):
    __commands_checks__: list[CheckType]
    __commands_cooldown__: list[Cooldown]
    __special_converters__: list[converters.Converter]

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
    params: OrderedDict[:class:`str`, :class:`inspect.Parameter`]
        The command's parameters.
    """

    def __new__(cls, *args, **kwargs: Any) -> Command:
        self = super().__new__(cls)
        self.__original_kwargs__ = kwargs.copy()
        return self

    def __init__(self, func: CommandFunctionType, **kwargs: Any):
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
                encoding = detect(help_doc)["encoding"]
                help_doc = help_doc.decode(encoding)
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
        self.cog: Optional[Cog] = kwargs.get("cog")
        self.parent: Optional[Command] = kwargs.get("parent")
        self.description: str = inspect.cleandoc(kwargs.get("description", ""))
        self.hidden: bool = kwargs.get("hidden", False)
        self.aliases: Iterable[str] = kwargs.get("aliases", [])

        for alias in self.aliases:
            if not isinstance(alias, str):
                raise TypeError("A commands aliases should be an iterable only containing strings")

        self._before_hook = None
        self._after_hook = None

    def __str__(self) -> str:
        return self.qualified_name

    @property
    def callback(self) -> CommandFunctionType:
        """The internal callback the command holds.

        Note
        ----
        When this is set if it fails to find a matching object in the module's dict, it will reload the module with
        :attr:`typing.TYPE_CHECKING` set to ``True``, the purpose of this is to help aid with circular import
        issues, if you do not want this to happen you have a few options:

            - Put the imports in an ``if False:`` block or a constant named ``MYPY`` set to ``False`` (assuming you
              are using MyPy see https://mypy.readthedocs.io/en/stable/common_issues.html#import-cycles).
            - Use an else after the ``if typing.TYPE_CHECKING`` to set the imported values to something at runtime.
            - Don't have circular imports :P
        """
        return self._callback

    @callback.setter
    def callback(self, function: CommandFunctionType) -> None:
        if not asyncio.iscoroutinefunction(function):
            raise TypeError(f"The callback for the command {function.__name__!r} must be a coroutine function.")

        module = sys.modules[function.__module__]

        try:
            annotations = get_type_hints(function, module.__dict__)
        except NameError as exc:
            reload_module_with_TYPE_CHECKING(module)
            try:
                annotations = get_type_hints(function, module.__dict__)
            except NameError:
                raise exc from None

        while inspect.ismethod(function):  # HelpCommand.command_callback
            function = function.__func__
        function.__annotations__ = annotations  # replace the function's old annotations for later
        self.params: OrderedDict[str, inspect.Parameter] = inspect.signature(function).parameters.copy()
        try:
            self.params.copy().popitem(last=False)
        except KeyError:
            raise ClientException(f'Callback for {self.name} command is missing a "ctx" parameter.') from None
        self.module = module
        self._callback = function

    @cached_property
    def clean_params(self) -> OrderedDict[str, inspect.Parameter]:
        """OrderedDict[:class:`str`, :class:`inspect.Parameter`]:
        The command's parameters without ``"self"`` and ``"ctx"``."""
        params = self.params.copy()
        if self.cog is not None:
            try:
                params.popitem(last=False)  # cog's "self" param
            except KeyError:
                raise ClientException(f'Callback for {self.name} command is missing a "self" parameter.') from None
        try:
            params.popitem(last=False)  # context param
        except KeyError:
            raise ClientException(f'Callback for {self.name} command is missing a "ctx" parameter.') from None
        return params

    @property
    def qualified_name(self) -> str:
        """:class:`str`: The full name of the command, this takes into account subcommands etc."""
        return " ".join(c.name for c in reversed(list(self.parents)))

    @property
    def parents(self) -> Generator[Command, None, None]:
        """Iterator[:class:`Command`]: The command's parents."""
        command = self
        while command is not None:
            if not isinstance(command, Command):
                break
            yield command
            command = command.parent

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

    def error(self, coro: Optional[CommandErrorFunctionType] = None) -> CommandErrorFunctionType:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to handle a commands ``on_error`` functionality similarly to
        :meth:`steam.ext.commands.Bot.on_command_error`.

        Example: ::

            @bot.command()
            async def raise_an_error(ctx):
                raise Exception('oh no an error')


            @raise_an_error.error
            async def on_error(ctx, error):
                print(f'{ctx.command.name} raised an exception {error}')
        """

        def decorator(coro: CommandErrorFunctionType) -> CommandErrorFunctionType:
            if not asyncio.iscoroutinefunction(coro):
                raise TypeError(f"Error handler for {self.name} must be a coroutine")
            self.on_error = coro
            return coro

        return decorator(coro) if coro is not None else lambda coro: decorator(coro)

    def before_invoke(self, coro: Optional[HookFunction] = None) -> HookDecoType:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to be ran before any arguments are parsed.
        """

        def decorator(coro: HookFunction) -> HookFunction:
            if asyncio.iscoroutinefunction(coro):
                raise TypeError("Hooks must be coroutines")
            self._before_hook = coro
            return coro

        return decorator(coro) if coro is not None else lambda coro: decorator(coro)

    def after_invoke(self, coro: Optional[HookFunction] = None) -> HookDecoType:
        """|maybecallabledeco|
        Register a :ref:`coroutine <coroutine>` to be ran after the command has been invoked.
        """

        def decorator(coro: HookFunction) -> HookFunction:
            if asyncio.iscoroutinefunction(coro):
                raise TypeError("Hooks must be coroutines")
            self._after_hook = coro
            return coro

        return decorator(coro) if coro is not None else lambda coro: decorator(coro)

    async def invoke(self, ctx: Context) -> None:
        """|coro|
        Invoke the callback the command holds.

        Parameters
        ----------
        ctx: :class:`~steam.ext.commands.Context`
            The invocation context.
        """
        try:
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
            try:
                cooldown(ctx)
            except CommandOnCooldown:
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

    async def _parse_arguments(self, ctx: Context) -> None:
        args = []
        kwargs = {}

        for name, param in self.clean_params.items():
            if param.kind == param.POSITIONAL_OR_KEYWORD:
                is_greedy = get_origin(param.annotation) is converters.Greedy
                greedy_args = []
                if ctx.shlex.position == ctx.shlex.end:
                    args.append(await self._get_default(ctx, param))
                for argument in ctx.shlex:
                    try:
                        transformed = await self._transform(ctx, param, argument)
                    except BadArgument:
                        if not is_greedy:
                            raise
                        ctx.shlex.undo()  # undo last read string for the next argument
                        args.append(tuple(greedy_args))
                        break
                    if not is_greedy:
                        args.append(transformed)
                        break
                    greedy_args.append(transformed)
            elif param.kind == param.KEYWORD_ONLY:
                # kwarg only param denotes "consume rest" semantics
                arg = ctx.shlex.in_stream[ctx.shlex.position :]
                kwargs[name] = await (self._transform(ctx, param, arg) if arg else self._get_default(ctx, param))
                break
            elif param.kind == param.VAR_KEYWORD:
                # same as **kwargs
                kv_pairs = [arg.split("=") for arg in ctx.shlex]
                if not kv_pairs:
                    if "default" in kwargs:
                        raise DuplicateKeywordArgument("default")
                    kwargs["default"] = await self._get_default(ctx, param)
                    break

                annotation = param.annotation
                key_type, value_type = (
                    (str, str) if annotation in (param.empty, dict) else get_args(annotation)
                )  # default to {str: str}

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
                    break
                except ValueError:
                    raise UnmatchedKeyValuePair("Unmatched key-value pair passed") from None
            elif param.kind == param.VAR_POSITIONAL:
                # same as *args
                for arg in ctx.shlex:
                    transformed = await self._transform(ctx, param, arg)
                    args.append(transformed)
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
            if len(converters_) == 1:
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
        if isinstance(converter, converters.Converter):
            try:
                converter = converter() if callable(converter) else converter
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
                default = param.default() if callable(param.default) else param.default
                return await default.default(ctx)
            except Exception as exc:
                try:
                    name = param.default.__name__
                except AttributeError:
                    name = param.default.__class__.__name__
                raise BadArgument(f"{name} failed to return a default argument") from exc
        return param.default


class GroupMixin:
    def __init__(self, *args: Any, **kwargs: Any):
        self.case_insensitive = kwargs.get("case_insensitive", False)
        self.__commands__: dict[str, Command] = CaseInsensitiveDict() if self.case_insensitive else dict()
        super().__init__(*args, **kwargs)

    @property
    def commands(self) -> set[Command]:
        """set[:class:`Command`]: A set of the loaded commands."""
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

        if isinstance(self, Command):
            command.parent = self

        if isinstance(command.parent, GroupMixin) and command.parent is not self:
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

        # fast path, no space in name
        if " " not in name:
            return self.__commands__.get(name)

        names = name.split()
        if not names:
            return None
        command = self.__commands__.get(names[0])
        if not isinstance(command, GroupMixin):
            return command

        for name in names[1:]:
            try:
                command = command.__commands__[name]
            except (AttributeError, KeyError):
                return None

        return command

    def command(
        self,
        callback: Optional[CommandFunctionType] = None,
        *,
        name: Optional[str] = None,
        cls: Optional[type[Command]] = None,
        **attrs: Any,
    ) -> Union[Callable[[CommandFunctionType], Command], Command]:
        """|maybecallabledeco|
        A decorator that invokes :func:`command` and adds the created :class:`Command` to the internal command list.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the command. Will default to ``callback.__name__``.
        cls: type[:class:`GroupCommand`]
            The class to construct the command from. Defaults to :class:`GroupCommand`.
        **attrs:
            The attributes to pass to the command's ``__init__``.
        """
        cls = cls or Command

        def decorator(callback: CommandFunctionType) -> Command:
            attrs.setdefault("parent", self)
            result = command(callback, name=name, cls=cls, **attrs)
            self.add_command(result)
            return result

        return decorator(callback) if callback is not None else lambda callback: decorator(callback)

    def group(
        self,
        callback: Optional[CommandFunctionType] = None,
        *,
        name: Union[Optional[str], CommandFunctionType] = None,
        cls: Optional[type[GroupCommand]] = None,
        **attrs: Any,
    ) -> Union[Callable[[CommandFunctionType], GroupCommand], GroupCommand]:
        """|maybecallabledeco|
        A decorator that invokes :func:`group` and adds the created :class:`GroupCommand` to the internal command list.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the command. Will default to ``callback.__name__``.
        cls: type[:class:`GroupCommand`]
            The class to construct the command from. Defaults to :class:`GroupCommand`.
        **attrs:
            The attributes to pass to the command's ``__init__``.
        """
        cls = cls or GroupCommand

        def decorator(callback: CommandFunctionType) -> GroupCommand:
            attrs.setdefault("parent", self)
            result = group(callback, name=name, cls=cls, **attrs)
            self.add_command(result)
            return result

        return decorator(callback) if callback is not None else lambda callback: decorator(callback)

    @property
    def children(self) -> Generator[Command, None, None]:
        """Iterator[:class:`Command`]: The commands children."""
        for command in self.commands:
            yield command
            if isinstance(command, GroupCommand):
                yield from command.children

    def recursively_remove_all_commands(self) -> None:
        for command in self.commands:
            if isinstance(command, GroupMixin):
                command.recursively_remove_all_commands()
            self.remove_command(command.name)


class GroupCommand(GroupMixin, Command):
    def __init__(self, func: CommandFunctionType, **kwargs: Any):
        super().__init__(func, **kwargs)


def command(
    callback: Optional[CommandFunctionType] = None,
    *,
    name: Optional[str] = None,
    cls: Optional[type[Command]] = None,
    **attrs: Any,
) -> Union[Callable[[CommandFunctionType], Command], Command]:
    """|maybecallabledeco|
    A decorator that registers a :ref:`coroutine <coroutine>` as a :class:`Command`.

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

    def decorator(callback: CommandFunctionType) -> Command:
        if isinstance(callback, Command):
            raise TypeError("Callback is already a command.")
        return cls(callback, name=name, **attrs)

    return decorator(callback) if callback is not None else lambda callback: decorator(callback)


def group(
    callback: Optional[CommandFunctionType] = None,
    *,
    name: Optional[str] = None,
    cls: Optional[type[GroupCommand]] = None,
    **attrs: Any,
) -> Union[Callable[[CommandFunctionType], GroupCommand], GroupCommand]:
    """|maybecallabledeco|
    A decorator that registers a :ref:`coroutine <coroutine>` as a :class:`GroupCommand`.

    Parameters
    ----------
    name: Optional[:class:`str`]
        The name of the command. Will default to ``callback.__name__``.
    cls: type[:class:`GroupCommand`]
        The class to construct the command from. Defaults to :class:`GroupCommand`.
    **attrs:
        The attributes to pass to the command's ``__init__``.
    """

    return command(callback, name=name, cls=cls or GroupCommand, attrs=attrs)


def check(predicate: CheckType) -> CheckReturnType:
    """
    A decorator that registers a function that *could be a* |coroutine_link|_ as a check to a command.

    They should take a singular argument representing the :class:`~steam.ext.commands.Context` for the message.

    Usage::

        def is_mod(ctx):
            return ctx.author in ctx.clan.mods

        @commands.check(is_mod)
        @bot.command()
        async def kick(ctx, user: steam.User):
            # implementation here

    This will raise an :exc:`steam.ext.commands.CheckFailure` if the user is not an a mod in the clan.

    Attributes
    ----------
    predicate: Callable[[:class:`Context`], Awaitable[:class:`bool`]]
        The registered check, this will always be a wrapped in a :ref:`coroutine <coroutine>`
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
        async def wrapper(ctx: Context) -> bool:
            return predicate(ctx)

        decorator.predicate = wrapper

    return decorator


def is_owner(command: Optional[MaybeCommandDeco] = None) -> MaybeCommandDeco:
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
    return decorator(command) if command is not None else lambda command: decorator(command)


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
        async def once_every_ten_seconds(ctx):
            ...

    This can only be invoked a user every ten seconds.
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
