# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

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
"""

from __future__ import annotations

import re
import sys
import types
from abc import abstractmethod
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    ForwardRef,
    Generic,
    Iterator,
    NoReturn,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from typing_extensions import Literal, Protocol, get_args, get_origin, runtime_checkable

from ... import utils
from ...channel import Channel
from ...clan import Clan
from ...errors import HTTPException, InvalidSteamID
from ...game import Game
from ...group import Group
from ...models import FunctionType
from ...user import User
from .errors import BadArgument
from .utils import reload_module_with_TYPE_CHECKING

if TYPE_CHECKING:
    from steam.ext import commands

    from .commands import MC
    from .context import Context

__all__ = (
    "converter_for",
    "Converter",
    "UserConverter",
    "ChannelConverter",
    "ClanConverter",
    "GroupConverter",
    "GameConverter",
    "Default",
    "DefaultAuthor",
    "DefaultChannel",
    "DefaultClan",
    "DefaultGroup",
    "DefaultGame",
    "Greedy",
)

T = TypeVar("T")
Converters = Union[Type["Converter"], "BasicConverter"]
RD = Union[Callable[["MC"], "MC"], "MC"]


class ConverterDict(Dict[type, Tuple[Converters, ...]]):
    def __setitem__(self, key: Any, value: Converters) -> None:
        try:
            old_value = self[key]
        except KeyError:
            super().__setitem__(key, (value,))
        else:
            super().__setitem__(key, old_value + (value,))


class BasicConverter(FunctionType):
    converter_for: T

    def __call__(self, arg: str) -> T:
        ...


CONVERTERS = ConverterDict()


def converter_for(converter_for: T) -> Callable[[MC], MC]:
    """The recommended way to mark a function converter as such.

    Note
    ----
    All of the converters marked with this decorator or derived from :class:`.Converter` can be accessed via
    :attr:`~steam.ext.commands.Bot.converters`.

    Examples
    --------
    .. code-block:: python

        @commands.converter(commands.Command)  # this is the type hint used
        def command_converter(argument: str) -> commands.Command:
            return bot.get_command(argument)

        # then later

        @bot.command
        async def source(ctx, command: commands.Command):  # this then calls command_converter on invocation.
            ...


    Parameters
    ----------
    converter_for: T
        The type annotation the decorated converter should convert for.

    Attributes
    -----------
    converter_for: T
        The class that the converter can be type-hinted to to.
    """

    def decorator(func: MC) -> MC:
        if not isinstance(func, types.FunctionType):
            raise TypeError(f"Excepted a function, received {func.__class__.__name__!r}")
        CONVERTERS[converter_for] = func
        func.converter_for = converter_for
        return func

    return decorator


@runtime_checkable
class Converter(Protocol[T]):
    r"""A custom :class:`typing.Protocol` from which converters can be derived.

    Note
    ----
    All of the converters derived from :class:`Converter` or marked with the :func:`converter_for` decorator can
    be accessed via :attr:`~steam.ext.commands.Bot.converters`.

    Some custom dataclasses from this library can be type-hinted without the need for a custom converter:

        - :class:`~steam.User`.
        - :class:`~steam.abc.Channel`
        - :class:`~steam.Clan`
        - :class:`~steam.Group`
        - :class:`~steam.Game`

    Attributes
    -----------
    converter_for: T
        The class that the converter can be type-hinted to to.

    Examples
    --------

    Builtin: ::

        @bot.command
        async def command(ctx, user: steam.User):
            # this will end up making the user variable a `steam.User` object.

        # invoked as
        # !command 76561198248053954
        # or !command Gobot1234

    A custom converter: ::

        class ImageConverter(commands.Converter[steam.Image]):  # the annotation to typehint to

            async def convert(self, ctx: commands.Context, argument: str) -> steam.Image:
                async with aiohttp.ClientSession() as session:
                    async with session.get(argument) as r:
                        image_bytes = BytesIO(await r.read())
                try:
                    return steam.Image(image_bytes)
                except (TypeError, ValueError):  # failed to convert to an image
                    raise commands.BadArgument("Cannot convert image") from None


        # then later
        @bot.command
        async def set_avatar(ctx: commands.Context, avatar: steam.Image) -> None:
            await bot.user.edit(avatar=avatar)
            await ctx.send("👌")

        # invoked as
        # !set_avatar https://my_image_url.com
    """

    converter_for: T

    @abstractmethod
    async def convert(self, ctx: "commands.Context", argument: str):
        """|coro|
        An abstract method all converters must derive.

        Parameters
        ----------
        ctx: :class:`~steam.ext.commands.Context`
            The context for the invocation.
        argument: :class:`str`
            The argument that is passed from the argument parser.

        Returns
        -------
        T
            The created argument, should be of the same type of :attr:`converter_for`.
        """
        raise NotImplementedError("Derived classes must implement this")

    @classmethod
    @overload
    def register(cls, command: Literal[None] = ...) -> Callable[["MC"], "MC"]:
        ...

    @classmethod
    @overload
    def register(cls, command: MC) -> MC:
        ...

    @classmethod
    def register(cls, command: Optional[RD] = None) -> RD:
        """|maybecallabledeco|
        Register a converter to a specific command.

        Examples
        --------
        .. code-block:: python

            class CustomUserConverter(commands.Converter[steam.User]):
                async def convert(self, ctx: commands.Context, argument: str) -> steam.User:
                    ...

            @bot.command
            @CustomUserConverter.register
            async def is_cool(ctx, user: steam.User):
                ...

        In this example ``is_cool``'s user parameter would be registered to the ``CustomUserConverter`` rather than
        the global :class:`UserConverter`.
        """

        def decorator(command: MC) -> MC:
            is_command = not isinstance(command, types.FunctionType)
            try:
                (command.special_converters if is_command else command.__special_converters__).append(cls)
            except AttributeError:
                if is_command:
                    command.special_converters = [cls]
                else:
                    command.__special_converters__ = [cls]
            return command

        return decorator(command) if command is not None else decorator

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        converter_for = globals().pop("__current_converter", None)
        # the flow for this is __class_getitem__ -> type.__new__ (but that won't do anything) -> __init_subclass__ so
        # this is alright
        if converter_for is None:
            # raise TypeError("Converters should subclass commands.Converter using __class_getitem__")
            utils.warn(
                "Subclassing commands.Converter without arguments is depreciated and is scheduled for removal in V.1"
            )
            CONVERTERS[cls] = cls
        else:
            if isinstance(converter_for, ForwardRef):
                module = sys.modules[cls.__module__]
                reload_module_with_TYPE_CHECKING(module)
                str_value = converter_for.__forward_arg__
                try:
                    converter_for = module.__dict__[str_value]
                except KeyError:
                    raise NameError(f"{str_value!r} was not able to be evaluated to a type") from None
            cls.converter_for = converter_for
            CONVERTERS[converter_for] = cls

    def __class_getitem__(cls, converter_for: ConverterTypes) -> Converter[T]:
        """The entry point for Converters.

        This method is called when :class:`.Converter` is subclassed to handle the argument that was passed as the
        ``converter_for``.
        """
        if isinstance(converter_for, tuple) and len(converter_for) != 1:
            raise TypeError("commands.Converter only accepts one argument")
        annotation = super().__class_getitem__(converter_for)
        globals()["__current_converter"] = get_args(annotation)[0]
        return annotation


class UserConverter(Converter[User]):
    """The converter that is used when the type-hint passed is :class:`~steam.User`.

    Lookup is in the order of:
        - Steam ID
        - Mentions
        - Name
        - URLs
    """

    async def convert(self, ctx: Context, argument: str) -> User:
        try:
            user = await ctx.bot.fetch_user(argument)
        except (InvalidSteamID, HTTPException):
            if argument.startswith("@"):  # probably a mention
                try:
                    account_id = ctx.message.mentions.mention_accountids[0]
                except IndexError:
                    pass
                else:
                    user = await ctx.bot.fetch_user(account_id)
                    if user is not None and user.id == account_id:
                        ctx.message.mentions.mention_accountids.remove(account_id)
                        return user
            user = utils.find(lambda u: u.name == argument, ctx.bot.users)

            if user is None:
                id64 = await utils.id64_from_url(argument, session=ctx._state.http._session)
                return await self.convert(ctx, id64)
        if user is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam user')
        return user


class ChannelConverter(Converter[Channel]):
    """The converter that is used when the type-hint passed is :class:`~steam.Channel`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> Channel:
        channel = utils.find(
            lambda c: c.id == int(argument) if argument.isdigit() else lambda c: c.name == argument,
            (ctx.clan or ctx.group).channels,
        )
        if channel is None:
            raise BadArgument(f'Failed to convert "{argument}" to a channel')
        return channel


class ClanConverter(Converter[Clan]):
    """The converter that is used when the type-hint passed is :class:`~steam.Clan`.

    Lookup is in the order of:
        - Steam ID
        - Name
        - URLs
    """

    async def convert(self, ctx: Context, argument: str) -> Clan:
        try:
            clan = await ctx.bot.fetch_clan(argument)
        except (InvalidSteamID, HTTPException):
            clan = utils.find(lambda c: c.name == argument, ctx.bot.clans)
            if clan is None:
                id64 = await utils.id64_from_url(argument, session=ctx._state.http._session)
                return await self.convert(ctx, id64)
        if clan is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam clan')
        return clan


class GroupConverter(Converter[Group]):
    """The converter that is used when the type-hint passed is :class:`~steam.Group`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> Group:
        try:
            group = ctx.bot.get_group(argument)
        except InvalidSteamID:
            group = utils.find(lambda c: c.name == argument, ctx.bot.groups)
        if group is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam group')
        return group


class GameConverter(Converter[Game]):
    """The converter that is used when the type-hint passed is :class:`~steam.Game`.

    If the param is a digit it is assumed that the argument is the :attr:`Game.id` else it is assumed it is the
    :attr:`Game.title`.
    """

    async def convert(self, ctx: Context, argument: str) -> Game:
        return Game(id=int(argument)) if argument.isdigit() else Game(title=argument)


@runtime_checkable
class Default(Protocol):
    """A custom way to specify a default values for commands.

    Examples
    --------
    Builtin: ::

        @bot.command()
        async def info(ctx, user=DefaultAuthor):
            # if no user is passed it will be ctx.author
            ...

    A custom default: ::

        class CurrentCommand(commands.Default):
            async def default(self, ctx: commands.Context) -> commands.Command:
                return ctx.command  # return the current command

        # then later

        @bot.command
        async def source(ctx: commands.Context, command: commands.Command = CurrentCommand):
            # command would now be source
            ...

        # this could also be mixed in with a converter to convert a string to a command.
    """

    @abstractmethod
    async def default(self, ctx: "commands.Context"):
        raise NotImplementedError("Derived classes must to implement this")


class DefaultAuthor(Default):
    """Returns the :attr:`.Context.author`"""

    async def default(self, ctx: Context) -> User:
        return ctx.author


class DefaultChannel(Default):
    """Returns the :attr:`.Context.channel`"""

    async def default(self, ctx: Context) -> Channel:
        return ctx.channel


class DefaultGroup(Default):
    """Returns the :attr:`.Context.group`"""

    async def default(self, ctx: Context) -> Group:
        return ctx.group


class DefaultClan(Default):
    """Returns the :attr:`.Context.clan`"""

    async def default(self, ctx: Context) -> Clan:
        return ctx.clan


class DefaultGame(Default):
    """Returns the :attr:`.Context.author`'s :attr:`~steam.User.game`"""

    async def default(self, ctx: Context) -> Game:
        return ctx.author.game


class Greedy(Generic[T]):
    """
    A custom :class:`typing.Generic` that allows for special greedy command parsing behaviour. It signals to the command
    parser to consume as many arguments as it can until it silently errors reverts the last argument being read and
    then carries on normally.

    Greedy can be mixed in with any normally supported positional or keyword argument type any number of times.

    Example
    -------
    .. code-block:: python

        @bot.command()
        async def test(ctx, numbers: commands.Greedy[int], reason: str):
            await ctx.send(f"numbers: {numbers}, reason: {reason}")

    An invocation of ``"test 1 2 3 4 5 6 hello"`` would pass ``(1, 2, 3, 4, 5, 6)`` to ``numbers`` and ``"hello"`` to
    ``reason``.

    Attributes
    ----------
    converter: T
        The converter the Greedy type holds.

    Note
    ----
    Passing a tuple of length greater than one is shorthand for ``Greedy[Union[converter_tuple]]``.
    """

    converter: T

    def __new__(
        cls, *args: Any, **kwargs: Any
    ) -> NoReturn:  # give a more helpful message than typing._BaseGenericAlias.__call__
        raise TypeError("commands.Greedy cannot be instantiated directly, instead use Greedy[...]")

    def __class_getitem__(cls, converter: GreedyTypes) -> Greedy[T]:
        """The entry point for Greedy types."""
        if isinstance(converter, tuple):
            converter = converter[0] if len(converter) == 1 else Union[converter]
        if not (callable(converter) or isinstance(converter, (Converter, str)) or get_origin(converter) is not None):
            raise TypeError(f"Greedy[...] expects a type or a Converter instance not {converter!r}")

        if converter in INVALID_GREEDY_TYPES:
            raise TypeError(f"Greedy[{converter.__name__}] is invalid")

        origin = get_origin(converter)
        args = get_args(converter)
        if origin is Union:
            for arg in args:
                if arg in INVALID_GREEDY_TYPES:
                    raise TypeError(f"Greedy[{converter!r}] is invalid.")
                if get_origin(arg) is Greedy:  # flatten Greedies similarly to Unions
                    new_args = list(args)
                    idx = new_args.index(arg)
                    new_args.remove(arg)
                    new_args.insert(idx, arg.converter)
                    duplicate_free = []
                    for t in new_args:
                        if t not in duplicate_free:
                            duplicate_free.append(t)
                    return cls.__class_getitem__(tuple(duplicate_free))
                if arg is Greedy:
                    raise TypeError(f"Cannot use un-parametrized Greedy")
        elif origin is Greedy:
            converter = converter.converter

        annotation = super().__class_getitem__(converter)
        annotation.converter = get_args(annotation)[0]
        return annotation

    if TYPE_CHECKING:

        def __iter__(self) -> Iterator[T]:  # make Unions and stuff sort of work
            ...


# fmt: off
ConverterTypes = Union[
    T,
    str,
    Tuple[T, ...],
    Tuple[str, ...],
]
GreedyTypes = Union[
    T,                # a class/type
    str,              # should be a string with a ForwardRef to a class to be evaluated later
    Tuple[T, ...],    # for Greedy[int,] / Greedy[(int,)] to be valid or Greedy[User, int] to be expanded to Union
    Tuple[str, ...],  # same as above two points
    BasicConverter,   # a callable simple converter
    Converter,        # a Converter subclass
]
INVALID_GREEDY_TYPES = (
    str,              # leads to parsing weirdness
    type(None),       # how would this work
)
