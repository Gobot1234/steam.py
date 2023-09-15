"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import types
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable, Sequence
from inspect import get_annotations
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    ForwardRef,
    Protocol,
    TypeAlias,
    TypeVar,
    cast,
    final,
    get_args,
    get_origin,
    runtime_checkable,
)

from typing_extensions import Never, Self, get_original_bases

from ... import utils
from ...abc import PartialUser
from ...app import App, PartialApp
from ...channel import Channel
from ...chat import ChatMessage, Member, PartialMember
from ...clan import Clan
from ...enums import Type
from ...errors import HTTPException, InvalidID, WSException
from ...group import Group
from ...id import id64_from_url, parse_id64
from ...user import ClientUser, User
from .errors import BadArgument, MissingRequiredArgument

if TYPE_CHECKING:
    from steam.ext import commands

    from ...friend import Friend
    from .bot import Bot
    from .commands import MaybeCommandT
    from .context import Context

__all__ = (
    "converter",
    "Converter",
    "UserConverter",
    "ChannelConverter",
    "ClanConverter",
    "GroupConverter",
    "AppConverter",
    "Default",
    "DefaultAuthor",
    "DefaultChannel",
    "DefaultClan",
    "DefaultGroup",
    "DefaultApp",
    "Greedy",
)

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
BotT = TypeVar("BotT", bound="Bot", covariant=True)
Converters: TypeAlias = "ConverterBase[Any] | BasicConverter[Any] | Callable[[str], Any]"


class BasicConverter(Protocol[T]):
    converter_for: type[T]

    def __call__(self, arg: str, /) -> T:
        ...


CONVERTERS = defaultdict[type, list[Converters]](list)


def converter(func: Callable[[str], T], /) -> BasicConverter[T]:
    """The recommended way to mark a function converter as such.

    Note
    ----
    All of the converters marked with this decorator or derived from :class:`Converter` can be accessed via
    :attr:`~commands.Bot.converters`.

    Examples
    --------
    .. code:: python

        @commands.converter
        def command_converter(argument: str) -> commands.Command:  # this is the type hint used
            return bot.get_command(argument)


        # then later
        @bot.command
        async def source(ctx, command: commands.Command):  # this then calls command_converter on invocation.
            ...


    Attributes
    -----------
    converter_for: T
        The class that the converter can be type-hinted to to.
    """

    annotations = get_annotations(func)
    converter_for = annotations["return"]
    func = cast(BasicConverter[T], func)
    func.converter_for = converter_for
    CONVERTERS[converter_for].append(func)
    return func


@runtime_checkable
class ConverterBase(Protocol[T_co]):
    # this is the base class we use for isinstance checks, don't actually this
    @abstractmethod
    async def convert(self, ctx: commands.Context[Any], argument: str, /) -> T_co:
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
        - :class:`~steam.App`

    Examples
    --------

    Builtin:

    .. code:: python

        @bot.command
        async def command(ctx, user: steam.User):
            ...  # this will tell the parser to convert user from a str to a steam.User object.


        # invoked as
        # !command 76561198248053954
        # or !command Gobot1234

    A custom converter:

    .. code:: python

        class MediaConverter(commands.Converter[steam.Media]):  # the annotation to typehint to
            async def convert(self, ctx: commands.Context, argument: str) -> steam.Media:
                async with aiohttp.ClientSession() as session:
                    async with session.get(argument) as r:
                        media_bytes = BytesIO(await r.read())
                try:
                    return steam.Media(media_bytes)
                except (TypeError, ValueError):  # failed to convert to an media
                    raise commands.BadArgument("Cannot convert media") from None


        # then later
        @bot.command
        async def set_avatar(ctx: commands.Context, avatar: steam.Media) -> None:
            await bot.user.edit(avatar=avatar)
            await ctx.send("👌")


        # invoked as
        # !set_avatar https://my_image_url.com
    """

    converter_for: type[T_co]

    @classmethod
    def register(cls, command: MaybeCommandT) -> MaybeCommandT:
        """Register a converter to a specific command.

        Examples
        --------
        .. code:: python

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
        from .commands import Command

        try:
            (
                command.special_converters
                if isinstance(command, Command)
                else cast(list[Converters], command.__special_converters__)  # type: ignore
            ).append(cls)
        except AttributeError:
            command.__special_converters__ = [cls]  # type: ignore
        return command

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        try:
            converter_for = get_args(get_original_bases(cls)[-1])[0]  # T_co.__value__
        except IndexError:
            raise TypeError("Converters should subclass commands.Converter using __class_getitem__")
        else:
            if isinstance(converter_for, ForwardRef):
                raise NameError(f"name {converter_for.__forward_arg__!r} is not defined") from None
            cls.converter_for = converter_for
            """The class that the converter can be type-hinted to to."""
            CONVERTERS[converter_for].append(cls)


class PartialUserConverter(Converter[PartialUser]):
    async def convert(self, ctx: Context, argument: str) -> PartialUser:
        try:
            return ctx._state.get_partial_user(argument)
        except InvalidID:
            if (
                argument.startswith("@")
                and isinstance(ctx.message, ChatMessage)
                and (
                    (
                        mention := utils.find(
                            lambda tag: (
                                tag.name == "mention" and tag.inner == argument and tag.position[0] >= ctx.lex.position
                            ),
                            ctx.message.content.tags,
                        )
                    )
                    is not None
                )
            ):
                return ctx._state.get_partial_user(mention.attributes[""])
            if (user := utils.get(ctx.bot.users, name=argument)) is not None:
                return ctx._state.get_partial_user(user.id64)
            if (id64 := await id64_from_url(argument, session=ctx._state.http._session)) is not None:
                return ctx._state.get_partial_user(id64)

        raise BadArgument(f'Failed to convert "{argument}" to a Steam user')


class UserConverter(PartialUserConverter, Converter[User]):
    """The converter that is used when the type-hint passed is :class:`~steam.User`.

    Lookup is in the order of:
        - Steam ID
        - Mentions
        - Name
        - URLs
    """

    async def convert(self, ctx: Context, argument: str) -> User | ClientUser:
        partial_user = await super().convert(ctx, argument)
        try:
            user = await ctx._state._maybe_user(partial_user.id64)
            if not isinstance(user, (User, ClientUser)):
                raise BadArgument(f'Failed to convert "{argument}" to a Steam user') from None
            return user
        except WSException:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam user') from None


class PartialMemberConverter(PartialUserConverter, Converter[PartialMember]):
    async def convert(self, ctx: Context, argument: str) -> PartialMember:
        partial_user = await super().convert(ctx, argument)
        if not (ctx.clan or ctx.group):
            raise BadArgument("Cannot convert to a partial member without a clan or group")
        return ctx._chat_group._get_partial_member(partial_user.id)


class MemberConverter(PartialMemberConverter, Converter[Member]):
    async def convert(self, ctx: Context, argument: str) -> Member:
        partial_member = await super().convert(ctx, argument)
        try:
            user = ctx._chat_group._maybe_member(partial_member.id)
            if not isinstance(user, Member):
                raise TypeError
            return user
        except (WSException, TypeError):
            raise BadArgument(f'Failed to convert "{argument}" to a Steam user') from None


class ChannelConverter(Converter[Channel[Any, Any, Any]]):
    """The converter that is used when the type-hint passed is :class:`~steam.Channel`.

    Lookup is in the order of:
        - ID
        - Name
    """

    async def convert(self, ctx: Context, argument: str) -> Channel[Any]:
        channel = utils.find(
            (lambda c: c.id == int(argument)) if argument.isdigit() else lambda c: c.name == argument,
            ctx._chat_group.channels,
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
            clan = await ctx.bot.fetch_clan(parse_id64(argument, type=Type.Clan))
        except (InvalidID, HTTPException):
            clan = utils.find(lambda c: c.name == argument, ctx.bot.clans)
            if clan is None:
                id64 = await id64_from_url(argument, session=ctx._state.http._session)
                if id64 is None:
                    raise BadArgument(f'Failed to convert "{argument}" to a Steam clan')
                return await ctx.bot.fetch_clan(id64)
        except WSException:
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
            group = ctx.bot.get_group(parse_id64(argument, type=Type.Chat))
        except InvalidID:
            group = utils.find(lambda c: c.name == argument, ctx.bot.groups)
        if group is None:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam group')
        return group


class AppConverter(Converter[App]):
    """The converter that is used when the type-hint passed is :class:`~steam.App`.

    If the param is a digit it is assumed that the argument is the :attr:`App.id` else it is assumed it is the
    :attr:`App.name`.
    """

    async def convert(self, ctx: Context, argument: str) -> App[str]:
        entries = await ctx._state.http.get_app_suggestions(argument)
        try:
            return next(App(id=int(app["id"]), name=app["name"]) for app in entries)
        except StopIteration:
            raise BadArgument(f'Failed to convert "{argument}" to a Steam app') from None


class PartialAppConverter(AppConverter, Converter[PartialApp[str]]):
    """The converter that is used when the type-hint passed is :class:`~steam.App`.

    If the param is a digit it is assumed that the argument is the :attr:`App.id` else it is assumed it is the
    :attr:`App.name`.
    """

    async def convert(self, ctx: Context, argument: str) -> PartialApp[str]:
        app = await super().convert(ctx, argument)
        return PartialApp(ctx._state, id=app.id, name=app.name)


@runtime_checkable
class Default(Protocol, Any if TYPE_CHECKING else object):
    """A custom way to specify a default values for commands.

    Examples
    --------
    Builtin:

    .. code:: python

        @bot.command()
        async def info(ctx, user=DefaultAuthor):
            ...  # if no user is passed it will be ctx.author

    A custom default:

    .. code:: python

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
    async def default(self, ctx: commands.Context) -> object:
        raise NotImplementedError("Derived classes must to implement this")


class DefaultAuthor(Default):
    """Returns the :attr:`.Context.author`"""

    async def default(self, ctx: Context) -> User | ClientUser | Friend | Member | PartialMember | PartialUser:
        return ctx.author


class DefaultChannel(Default):
    """Returns the :attr:`.Context.channel`"""

    async def default(self, ctx: Context) -> Channel[Any]:
        return ctx.channel


class DefaultGroup(Default):
    """Returns the :attr:`.Context.group`"""

    async def default(self, ctx: Context) -> Group:
        if not ctx.group:
            assert ctx.current_param is not None
            raise MissingRequiredArgument(ctx.current_param)
        return ctx.group


class DefaultClan(Default):
    """Returns the :attr:`.Context.clan`"""

    async def default(self, ctx: Context) -> Clan:
        if not ctx.clan:
            assert ctx.current_param is not None
            raise MissingRequiredArgument(ctx.current_param)
        return ctx.clan


class DefaultApp(Default):
    """Returns the :attr:`.Context.author`'s :attr:`~steam.User.app`"""

    async def default(self, ctx: Context) -> PartialApp:
        if getattr(ctx.author, "app", None) is None:
            assert ctx.current_param is not None
            raise MissingRequiredArgument(ctx.current_param)
        return ctx.author.app  # type: ignore


class GreedyGenericAlias(types.GenericAlias):
    converter: Any

    def __getattribute__(self, name: str, /) -> Any:
        if name == "converter":
            return self.__args__[0]
        return super().__getattribute__(name)


@final
class Greedy(Sequence[T]):
    """
    A custom :class:`typing.Generic` that allows for special greedy command parsing behaviour. It signals to the command
    parser to consume as many arguments as it can until it silently errors reverts the last argument being read and
    then carries on normally.

    Greedy can be mixed in with any normally supported positional or keyword argument type any number of times.

    Example
    -------
    .. code:: python

        @bot.command()
        async def test(ctx, numbers: commands.Greedy[int], reason: str):
            await ctx.send(f"numbers: {numbers}, reason: {reason}")

    An invocation of ``"test 1 2 3 4 5 6 hello"`` would pass ``(1, 2, 3, 4, 5, 6)`` to ``numbers`` and ``"hello"`` to
    ``reason``.
    """

    converter: Final[type[T]] = Any  # unused
    """The converter the Greedy type holds."""

    def __new__(
        cls, *args: Any, **kwargs: Any
    ) -> Never:  # give a more helpful message than typing._BaseGenericAlias.__call__
        raise TypeError("Greedy cannot be instantiated directly, instead use Greedy[...]")

    def __class_getitem__(cls, converter: T | tuple[T]) -> Self:
        """The entry point for creating a Greedy type."""
        if isinstance(converter, tuple):
            try:
                (converter,) = converter
            except ValueError:
                raise TypeError("Cannot pass variadic arguments to Greedy")
        if isinstance(converter, ForwardRef):
            converter = eval(converter.__forward_code__)

        if not (callable(converter) or isinstance(converter, (Converter, str)) or get_origin(converter) is not None):
            raise TypeError(f"Greedy[...] expects a type or a Converter instance not {converter!r}")

        if isinstance(converter, type) and issubclass(converter, str) or converter is types.NoneType:
            raise TypeError(f"Greedy[{converter.__name__}] is invalid")  # type: ignore

        return cast(Self, GreedyGenericAlias(cls, (converter,)))
