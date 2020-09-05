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

import re
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Generic, NoReturn, Tuple, TypeVar, Union

from typing_extensions import Protocol, get_origin, runtime_checkable

from ...errors import InvalidSteamID
from ...game import Game
from .errors import BadArgument

if TYPE_CHECKING:
    from steam.ext import commands

    from ...channel import BaseChannel
    from ...clan import Clan
    from ...group import Group
    from ...user import User
    from .context import Context

__all__ = (
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


@runtime_checkable
class Converter(Protocol):
    """A custom class from which converters can be derived. They should be type-hinted to a command's argument.

    Some custom types from this library can be type-hinted just using their normal type (see below).

    Examples
    --------

    Builtin: ::

        @bot.command()
        async def command(ctx, user: steam.User):
            # this will end up making the user variable a `User` object.

        # invoked as
        # !command 76561198248053954
        # or !command "Gobot1234"

    A custom converter: ::

        class ImageConverter:
            async def convert(self, ctx: 'commands.Context', argument: str):
                async with aiohttp.ClientSession as session:
                    async with session.get(argument) as r:
                        image_bytes = await r.read()
                try:
                    return steam.Image(image_bytes)
                except (TypeError, ValueError) as exc:  # failed to convert to an image
                    raise commands.BadArgument from exc

        # then later

        @bot.command()
        async def set_avatar(ctx, avatar: ImageConverter):
            await bot.edit(avatar=avatar)
        await ctx.send('👌')

        # invoked as
        # !set_avatar "my image url"
    """

    @abstractmethod
    async def convert(self, ctx: "commands.Context", argument: str):
        raise NotImplementedError("Derived classes must implement this")


class UserConverter(Converter):
    """The converter that is used when the type-hint passed is :class:`~steam.User`.

    Lookup is in the order of:
        - Steam ID
        - Mentions
        - Name
    """

    async def convert(self, ctx: "commands.Context", argument: str) -> "User":
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


class ChannelConverter(Converter):
    """The converter that is used when the type-hint passed is :class:`~steam.Channel`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: "commands.Context", argument: str) -> "BaseChannel":
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


class ClanConverter(Converter):
    """The converter that is used when the type-hint passed is :class:`~steam.Clan`.

    Lookup is in the order of:
        - Steam ID
        - Name
    """

    async def convert(self, ctx: "commands.Context", argument: str) -> "Clan":
        try:
            clan = ctx.bot.get_clan(argument)
        except InvalidSteamID:
            clan = [c for c in ctx.bot.clans if c.name == argument]
        if clan is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam clan')
        return clan[0] if isinstance(clan, list) else clan


class GroupConverter(Converter):
    """The converter that is used when the type-hint passed is :class:`~steam.Group`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: "commands.Context", argument: str) -> "Group":
        try:
            group = ctx.bot.get_group(argument)
        except InvalidSteamID:
            group = [c for c in ctx.bot.groups if c.name == argument]
        if not group:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam group')
        return group[0] if isinstance(group, list) else group


class GameConverter(Converter):
    """The converter that is used when the type-hint passed is :class:`~steam.Game`.

    If the param is a digit it is assumed that the argument is the game's app id else it is assumed it is the game's
    title.
    """

    async def convert(self, ctx: "commands.Context", argument: str):
        return Game(id=int(argument)) if argument.isdigit() else Game(title=argument)


@runtime_checkable
class Default(Protocol):
    """A custom way to specify a default values for commands.

    Examples
    --------
    Builtin: ::

        @bot.command()
        async def info(ctx, user: steam.User = DefaultAuthor):
            # if no user is passed it will be ctx.author

    A custom default: ::

        class CurrentCommand(commands.Default):
            async def default(self, ctx: 'commands.Context'):
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

    async def default(self, ctx: "commands.Context"):
        return ctx.author


class DefaultChannel(Default):
    """Returns the :attr:`.Context.channel`"""

    async def default(self, ctx: "commands.Context"):
        return ctx.channel


class DefaultGroup(Default):
    """Returns the :attr:`.Context.group`"""

    async def default(self, ctx: "commands.Context"):
        return ctx.group


class DefaultClan(Default):
    """Returns the :attr:`.Context.clan`"""

    async def default(self, ctx: "commands.Context"):
        return ctx.clan


class DefaultGame(Default):
    """Returns the :attr:`~steam.ext.commands.Context.author`'s :attr:`~steam.User.game`"""

    async def default(self, ctx: "commands.Context"):
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
            await ctx.send("numbers: {}, reason: {}".format(numbers, reason))

    An invocation of "test 1 2 3 4 5 6 hello" would pass numbers (1, 2, 3, 4, 5, 6) and reason with hello.
    """

    converter: T

    def __new__(cls, *args, **kwargs) -> NoReturn:  # give a more helpful message than typing._BaseGenericAlias.__call__
        raise TypeError("commands.Greedy cannot be instantiated directly, instead use Greedy[converter]")

    def __class_getitem__(cls, converter: "GreedyTypes") -> "Greedy[T]":
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
            raise TypeError(f"Cannot type-hint Greedy with {converter!r}")
        annotation = super().__class_getitem__(converter)
        annotation.converter = converter
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
    Any,                   # same as above
    Greedy,                # Greedy[Greedy[int]] makes no sense
)
