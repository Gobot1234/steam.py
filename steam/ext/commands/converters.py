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

import types
import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any, Dict, ForwardRef, Generic, NoReturn, Sequence, TypeVar, Union, overload

from typing_extensions import Literal, Protocol, TypeAlias, get_args, get_origin, runtime_checkable

from ... import utils
from ...channel import Channel
from ...clan import Clan
from ...errors import HTTPException, InvalidSteamID
from ...game import Game, StatefulGame
from ...group import Group
from ...user import User
from .errors import BadArgument

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
T_co = TypeVar("T_co", covariant=True)
Converters: TypeAlias = "ConverterBase | BasicConverter[Any]"


class ConverterDict(Dict[type, "tuple[Converters, ...]"]):
    def __setitem__(self, key: Any, value: Converters) -> None:
        old_value = super().get(key, ())
        super().__setitem__(key, old_value + (value,))


class BasicConverter(Protocol[T]):
    converter_for: T

    def __call__(self, __arg: str) -> T:
        ...


CONVERTERS = ConverterDict()


def converter_for(converter_for: T) -> Callable[[BasicConverter[T]], BasicConverter[T]]:
    """The recommended way to mark a function converter as such.

    Note
    ----
    All of the converters marked with this decorator or derived from :class:`Converter` can be accessed via
    :attr:`~commands.Bot.converters`.

    Examples
    --------
    .. code-block:: python3

        @commands.converter_for(commands.Command)  # this is the type hint used
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

    def decorator(func: BasicConverter[T]) -> BasicConverter[T]:
        if not isinstance(func, types.FunctionType):
            raise TypeError(f"Excepted a function, received {func.__class__.__name__!r}")
        CONVERTERS[converter_for] = func
        func.converter_for = converter_for
        return func

    return decorator


@runtime_checkable
class ConverterBase(Protocol[T_co]):
    # this is the base class we use for isinstance checks, don't actually this
    @abstractmethod
    async def convert(self, ctx: "commands.Context", argument: str) -> "T":
        """An abstract method all converters must derive.

        Parameters
        ----------
        ctx
            The context for the invocation.
        argument
            The argument that is passed from the argument parser.

        Returns
        -------
        An object, should be of the same type of :attr:`converter_for`.
        """
        raise NotImplementedError("Derived classes must implement this")


class Converter(ConverterBase[T_co], ABC):
    """A custom :class:`typing.Protocol` from which converters can be derived.

    Note
    ----
    All of the converters derived from :class:`Converter` or marked with the :func:`converter_for` decorator can
    be accessed via :attr:`~commands.Bot.converters`.

    Some custom dataclasses from this library can be type-hinted without the need for a custom converter:

        - :class:`~steam.User`.
        - :class:`~steam.abc.Channel`
        - :class:`~steam.Clan`
        - :class:`~steam.Group`
        - :class:`~steam.Game`

    Examples
    --------

    Builtin:

    .. code-block:: python3

        @bot.command
        async def command(ctx, user: steam.User):
            ...  # this will tell the parser to convert user from a str to a steam.User object.


        # invoked as
        # !command 76561198248053954
        # or !command Gobot1234

    A custom converter:

    .. code-block:: python3

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

    @classmethod
    @overload
    def register(cls, command: None = ...) -> Callable[[MC], MC]:
        ...

    @classmethod
    @overload
    def register(cls, command: MC) -> MC:
        ...

    @classmethod
    def register(cls, command: Callable[[MC], MC] | MC | None = None) -> Callable[[MC], MC] | MC:
        """|maybecallabledeco|
        Register a converter to a specific command.

        Examples
        --------
        .. code-block:: python3

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
        try:
            converter_for = get_args(cls.__orig_bases__[0])[0]  # type: ignore
        except IndexError:
            # raise TypeError("Converters should subclass commands.Converter using __class_getitem__")
            warnings.warn(
                "Subclassing commands.Converter without arguments is depreciated and is scheduled for removal in V.1",
                DeprecationWarning,
            )
            CONVERTERS[cls] = cls
        else:
            if isinstance(converter_for, ForwardRef):
                raise NameError(f"name {converter_for.__forward_arg__!r} is not defined") from None
            setattr(cls, "converter_for", converter_for)
            CONVERTERS[converter_for] = cls

    if TYPE_CHECKING or utils.DOCS_BUILDING:

        @classmethod  # TODO: for 3.9 make this a cached_property and classmethod
        @property
        def converter_for(cls) -> T_co:
            """The class that the converter can be type-hinted to to."""
            ...


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
                    account_id = ctx.message.mentions.ids[0]
                except (IndexError, AttributeError):
                    pass
                else:
                    user = await ctx.bot.fetch_user(account_id)
                    if user is not None and user.id == account_id:
                        del ctx.message.mentions.ids[0]
                        return user
            user = utils.find(lambda u: u.name == argument, ctx.bot.users)

            if user is None:
                id64 = await utils.id64_from_url(argument, session=ctx._state.http._session)
                if id64 is not None:
                    user = await ctx.bot.fetch_user(id64)
        if user is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam user')
        return user


class ChannelConverter(Converter[Channel[Any]]):
    """The converter that is used when the type-hint passed is :class:`~steam.Channel`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> Channel[Any]:
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
        return Game(id=int(argument)) if argument.isdigit() else Game(name=argument)


@runtime_checkable
class Default(Protocol):
    """A custom way to specify a default values for commands.

    Examples
    --------
    Builtin:

    .. code-block:: python3

        @bot.command()
        async def info(ctx, user=DefaultAuthor):
            ...  # if no user is passed it will be ctx.author

    A custom default:

    .. code-block:: python3

        class CurrentCommand(commands.Default):
            async def default(self, ctx: commands.Context) -> commands.Command:
                return ctx.command  # return the current command


        # then later
        @bot.command
        async def source(ctx: commands.Context, command: commands.Command = CurrentCommand):
            ...  # command would now be source


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

    async def default(self, ctx: Context) -> Channel[Any]:
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

    async def default(self, ctx: Context) -> StatefulGame:
        return ctx.author.game


def flatten_greedy(item: T | Greedy[Any]) -> Generator[T, None, None]:
    if get_origin(item) in (Greedy, Union):
        for arg in get_args(item):
            if arg in INVALID_GREEDY_TYPES:
                raise TypeError(f"Greedy[{arg.__name__}] is invalid")
            if get_origin(arg) in (Greedy, Union):
                yield from flatten_greedy(arg)
            else:
                yield arg
    else:
        yield item


class Greedy(Generic[T]):
    """
    A custom :class:`typing.Generic` that allows for special greedy command parsing behaviour. It signals to the command
    parser to consume as many arguments as it can until it silently errors reverts the last argument being read and
    then carries on normally.

    Greedy can be mixed in with any normally supported positional or keyword argument type any number of times.

    Example
    -------
    .. code-block:: python3

        @bot.command()
        async def test(ctx, numbers: commands.Greedy[int], reason: str):
            await ctx.send(f"numbers: {numbers}, reason: {reason}")

    An invocation of ``"test 1 2 3 4 5 6 hello"`` would pass ``(1, 2, 3, 4, 5, 6)`` to ``numbers`` and ``"hello"`` to
    ``reason``.
    """

    converter: T  #: The converter the Greedy type holds.

    def __new__(
        cls, *args: Any, **kwargs: Any
    ) -> NoReturn:  # give a more helpful message than typing._BaseGenericAlias.__call__
        raise TypeError("Greedy cannot be instantiated directly, instead use Greedy[...]")

    def __class_getitem__(cls, converter: GreedyTypes[T]) -> Greedy[T]:
        """The entry point for creating a Greedy type.

        Note
        ----
        Passing more than one argument to ``converter`` is shorthand for ``Union[converter_tuple]``.
        """
        if isinstance(converter, tuple):
            converter = converter[0] if len(converter) == 1 else Union[converter]
        if not (callable(converter) or isinstance(converter, (Converter, str)) or get_origin(converter) is not None):
            raise TypeError(f"Greedy[...] expects a type or a Converter instance not {converter!r}")

        if converter in INVALID_GREEDY_TYPES:
            raise TypeError(f"Greedy[{converter.__name__}] is invalid")

        seen = tuple(dict.fromkeys(flatten_greedy(converter)))

        annotation = super().__class_getitem__(seen[0] if len(seen) == 1 else Union[tuple(seen)])
        annotation.converter = get_args(annotation)[0]
        return annotation


if TYPE_CHECKING:
    # would be nice if this could just subclass Sequence but due to version differences for its
    # super().__class_getitem__'s return type it isn't necessarily assignable to.
    # when I drop support for <3.8 I'll make __class_getitem__ return a types.GenericAlias subclass
    class Greedy(Greedy[T], Sequence[T]):
        ...


ConverterTypes: TypeAlias = "T | str | tuple[T] | tuple[str]"
GreedyTypes: TypeAlias = "T | str | tuple[T, ...] | tuple[str, ...] | Converters"
# in order of appearence:
# a class/type
# should be a string with a ForwardRef to a class to be evaluated later
# for Greedy[int,] / Greedy[(int,)] to be valid or Greedy[User, int] to be expanded to Union
# same as above two points
# a simple callable converter or Converter


INVALID_GREEDY_TYPES = (
    str,  # leads to parsing weirdness
    type(None),  # how would this work
)
