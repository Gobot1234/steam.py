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
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Generic, NoReturn, Tuple, Type, TypeVar, Union

from typing_extensions import Protocol, get_args, get_origin, runtime_checkable

from ...channel import Channel
from ...clan import Clan
from ...errors import InvalidSteamID
from ...game import Game
from ...group import Group
from ...models import FunctionType
from ...user import User
from .errors import BadArgument

if TYPE_CHECKING:
    from steam.ext import commands

    from .context import Context

__all__ = (
    "converter",
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

T = TypeVar("T", bound=type)


class BasicConverter(FunctionType):
    converter_for: T

    def __call__(self, arg: str) -> T:
        ...


Converters = Union[Type["Converter"], BasicConverter]
CONVERTERS: dict[Any, Converters] = {}


def converter(converter: Any) -> Callable[[BasicConverter], BasicConverter]:
    """
    The recommended way to mark a callable converter as such.

    .. note::
        All of the converters marked with this decorator or derived from :class:`.Converter` can be accessed either via
        :attr:`~steam.ext.commands.Bot.converters` or :attr:`~steam.ext.commands.converters.CONVERTERS`.

    Examples
    --------
    .. code-block:: python

        @commands.converter(commands.Command)  # this is the type hint used
        def command_convert(self, argument: str) -> commands.Command:
            ...

        # then later

        @bot.command()
        async def source(ctx, avatar: commands.Command):  # this then calls command_convert on invocation.
            ...


    Parameters
    ----------
    converter: T
        The type annotation the decorated converter should convert for.

    Attributes
    -----------
    converter_for: T
        The class that the converter can be type-hinted to to.
    """

    def decorator(func: BasicConverter) -> BasicConverter:
        if not callable(func):
            raise TypeError(f"Excepted a callable, received {func.__class__.__name__!r}")
        CONVERTERS[converter] = func
        func.converter_for = converter
        return func

    return decorator


@runtime_checkable
class Converter(Protocol[T]):
    """A custom :class:`typing.Protocol` from which converters can be derived.

    Some custom dataclasses from this library can be type-hinted without the need for a custom converter:

        - :class:`~steam.User`.
        - :class:`~steam.Channel`
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

        @bot.command()
        async def command(ctx, user: steam.User):
            # this will end up making the user variable a :class:`~steam.User` object.

        # invoked as
        # !command 76561198248053954
        # or !command Gobot1234

    A custom converter: ::

        class ImageConverter(commands.Converter[steam.Image]):  # the annotation to typehint to
            async def convert(self, ctx, argument):
                search = re.search(r'\[url=(.*)\], argument)
                if search is None:
                    raise commands.BadArgument(f'{argument} is not a recognised image')
                async with aiohttp.ClientSession() as session:
                    async with session.get(search.group(1)) as r:
                        image_bytes = await r.read()
                try:
                    return steam.Image(image_bytes)
                except (TypeError, ValueError) as exc:  # failed to convert to an image
                    raise commands.BadArgument from exc

        # then later

        @bot.command()
        async def set_avatar(ctx, avatar: steam.Image):
            await bot.edit(avatar=avatar)
            await ctx.send('👌')

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
            The created argument, should be of the same type of :attr:`converter_for`
        """
        raise NotImplementedError("Derived classes must implement this")

    def __init_subclass__(cls):
        super().__init_subclass__()
        # if not hasattr(cls, "_converter_for"):
        #     raise TypeError("Converters should subclass commands.Converter[converter_for] using __class_getitem__")
        for converter, converter_for in reversed(tuple(CONVERTERS.items())):
            if cls._converter_for is converter_for:
                del CONVERTERS[converter]
                CONVERTERS[cls] = converter_for
                cls.converter_for = converter_for
                return
        else:
            import warnings

            warnings.warn(
                "Subclassing commands.Converter without arguments is depreciated and is scheduled for removal in V.1",
                DeprecationWarning,
            )
            CONVERTERS[cls] = cls

    def __class_getitem__(cls, converter_for: Any) -> Converter[T]:
        """The main entry point for Converters.

        This method is called when :class:`.Converter` is subclassed to handle the argument that was passed as the
        converter_for.
        """
        if isinstance(converter_for, tuple):
            if len(converter_for) != 1:
                raise TypeError("commands.Converter only accepts one argument")
            converter_for = converter_for[0]
        annotation = super().__class_getitem__(converter_for)
        cls._converter_for = get_args(annotation)[0]
        CONVERTERS[annotation] = cls._converter_for
        return annotation


class UserConverter(Converter[User]):
    """The converter that is used when the type-hint passed is :class:`~steam.User`.

    Lookup is in the order of:
        - Steam ID
        - Mentions
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> User:
        try:
            user = ctx.bot.get_user(argument) or await ctx.bot.fetch_user(argument)
        except InvalidSteamID:
            search = re.search(r"\[mention=(\d+)]@\w+\[/mention]", argument)
            if search is not None:
                return await self.convert(ctx, search.group(1))
            user = [u for u in ctx.bot.users if u.name == argument]
        if not user:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam user')
        return user[0] if isinstance(user, list) else user


class ChannelConverter(Converter[Channel]):
    """The converter that is used when the type-hint passed is :class:`~steam.Channel`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> Channel:
        channel = None
        if argument.isdigit():
            groups = ctx.bot._connection._combined.values()
            for group in groups:
                channel = [c for c in group.channels if c.id == int(argument)]
        else:
            attr = ctx.clan or ctx.group
            channel = [c for c in attr.channels if c.name == argument]
        if not channel:
            raise BadArgument(f'Failed to convert "{argument}" to a channel')
        return channel[0] if isinstance(channel, list) else channel


class ClanConverter(Converter[Clan]):
    """The converter that is used when the type-hint passed is :class:`~steam.Clan`.

    Lookup is in the order of:
        - Steam ID
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> Clan:
        try:
            clan = ctx.bot.get_clan(argument)
        except InvalidSteamID:
            clan = [c for c in ctx.bot.clans if c.name == argument]
        if clan is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam clan')
        return clan[0] if isinstance(clan, list) else clan


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
            group = [c for c in ctx.bot.groups if c.name == argument]
        if not group:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam group')
        return group[0] if isinstance(group, list) else group


class GameConverter(Converter[Game]):
    """The converter that is used when the type-hint passed is :class:`~steam.Game`.

    If the param is a digit it is assumed that the argument is the game's app id else it is assumed it is the game's
    title.
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

    A custom default: ::

        class CurrentCommand(commands.Default):
            async def default(self, ctx):
                return ctx.command  # return the current command

        # then later

        @bot.command()
        async def source(ctx, command=CurrentCommand):
            # command would now be source

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
    ``reason``
    """

    converter: T  #: The converter the Greedy type holds.

    def __new__(
        cls, *args: Any, **kwargs: Any
    ) -> NoReturn:  # give a more helpful message than typing._BaseGenericAlias.__call__
        raise TypeError("commands.Greedy cannot be instantiated directly, instead use Greedy[converter]")

    def __class_getitem__(cls, converter: GreedyTypes) -> Greedy[T]:
        """The main entry point for Greedy types."""
        if isinstance(converter, tuple):
            if len(converter) != 1:
                raise TypeError("commands.Greedy only accepts one argument")
            converter = converter[0]
        if (
            converter in INVALID_GREEDY_TYPES
            or get_origin(converter) is not None
            or not isinstance(converter, (Converter, str))
            and not callable(converter)
        ):
            raise TypeError(f"Cannot type-hint commands.Greedy with {converter!r}")
        annotation = super().__class_getitem__(converter)
        annotation.converter = get_args(annotation)[0]
        return annotation


# fmt: off
GreedyTypes = Union[
    T,                     # a class/type
    str,                   # should be a string with a ForwardRef to a class to be evaluated later
    Tuple[T],              # for Greedy[int,] / Greedy[(int,)] to be valid
    Tuple[str],            # same as above two points
    Callable[[str], Any],  # a callable simple converter
    Converter,             # a Converter subclass
]
INVALID_GREEDY_TYPES = (
    str,                   # leads to parsing weirdness
    None,                  # how would this work
    type(None),            # same as above
    Greedy,                # Greedy[Greedy[int]] makes no sense
)
