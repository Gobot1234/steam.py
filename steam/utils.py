# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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
"""

import asyncio
import contextvars
import functools
import html
import json
import re
from inspect import isawaitable
from operator import attrgetter
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generator,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)

import aiohttp
from typing_extensions import Literal

from .enums import EInstanceFlag, EType, ETypeChar, EUniverse
from .errors import InvalidSteamID

_T = TypeVar("_T")
_PROTOBUF_MASK = 0x80000000

# from ValvePython/steam


def is_proto(emsg: int) -> bool:
    return (int(emsg) & _PROTOBUF_MASK) > 0


def set_proto_bit(emsg: int) -> int:
    return int(emsg) | _PROTOBUF_MASK


def clear_proto_bit(emsg: int) -> int:
    return int(emsg) & ~_PROTOBUF_MASK


# fmt: off
IntOrStr = Union[int, str]
ETypeType = Union[
    EType,
    Literal[
        "Invalid", "Individual",
        "Multiseat", "GameServer",
        "AnonGameServer", "Pending",
        "ContentServer", "Clan",
        "Chat", "ConsoleUser",
        "AnonUser", "Max",
        0, 1, 2, 3, 4, 5, 6,
        7, 8, 9, 10, 11,
    ],
]
EUniverseType = Union[EUniverse, Literal["Invalid ", "Public", "Beta", "Internal", "Dev", "Max", 0, 1, 2, 3, 4, 5, 6,]]
InstanceType = Literal[0, 1]
# fmt: on


@overload
def make_id64() -> Literal[0]:
    ...


@overload
def make_id64(
    id: IntOrStr = 0,
    type: Optional[ETypeType] = None,
    universe: Optional[EUniverseType] = None,
    instance: Optional[InstanceType] = None,
) -> int:
    ...


def make_id64(
    id: IntOrStr = 0,
    type: Optional[ETypeType] = None,
    universe: Optional[EUniverseType] = None,
    instance: Optional[InstanceType] = None,
) -> int:
    """Convert various representations of Steam IDs to its Steam 64 bit ID.

    Examples
    --------
    .. code:: python

        make_id64()  # invalid steam_id
        make_id64(12345)  # account_id
        make_id64(12345, type='Clan')  # makes the account_id into a clan id
        make_id64('12345')
        make_id64(id=12345, type='Invalid', universe='Invalid', instance=0)
        make_id64(103582791429521412)  # steam64
        make_id64('103582791429521412')
        make_id64('STEAM_1:0:2')  # steam2
        make_id64('[g:1:4]')  # steam3

    Raises
    ------
    :exc:`TypeError`
        Too many arguments have been given.
    :exc:`.InvalidSteamID`
        The created SteamID would be invalid.

    Returns
    -------
    :class:`int`
        The 64 bit Steam ID.
    """
    if not any((type, universe, instance)) and id == 0:
        return 0
    try:
        id = int(id)
    except ValueError:
        id_is_int = False
    else:
        id_is_int = True

    # numeric input
    if id_is_int:
        # 32 bit account id
        if 0 <= id < 2 ** 32:
            type = type or EType.Individual
            universe = universe or EUniverse.Public
        # 64 bit
        elif 2 ** 32 < id < 2 ** 64:
            value = id
            id = id & 0xFFFFFFFF
            instance = (value >> 32) & 0xFFFFF
            type = (value >> 52) & 0xF
            universe = (value >> 56) & 0xFF
        else:
            raise InvalidSteamID(id, "it is too large" if id > 2 ** 64 else "it is too small")
    # textual input e.g. [g:1:4]
    else:
        result = id2_to_tuple(id) or id3_to_tuple(id)
        if result is None:
            raise InvalidSteamID(id, "it cannot be parsed")

        id, type, universe, instance = result

    try:
        type = EType(type) if isinstance(type, int) else EType[type]
    except (KeyError, ValueError):
        raise InvalidSteamID(id, f"{type!r} is not a valid EType") from None
    try:
        universe = EUniverse(universe) if isinstance(universe, int) else EUniverse[universe]
    except (KeyError, ValueError):
        raise InvalidSteamID(id, f"{type!r} is not a valid EUniverse") from None

    if instance is None:
        instance = 1 if type in (EType.Individual, EType.GameServer) else 0

    return int(universe) << 56 | int(type) << 52 | int(instance) << 32 | id


ID2_REGEX = re.compile(r"STEAM_(?P<universe>\d+):(?P<reminder>[0-1]):(?P<id>\d+)")


def id2_to_tuple(value: str) -> Optional[Tuple[int, EType, EUniverse, int]]:
    """
    Parameters
    ----------
    value: :class:`str`
        steam2 e.g. ``STEAM_1:0:1234``.

    Returns
    -------
    Optional[Tuple[:class:`int`, :class:`.EType`, :class:`.EUniverse`, :class:`int`]]
        A tuple of 32 bit ID, type, universe and instance or ``None``
        e.g. (100000, EType.Individual, EUniverse.Public, 1) or ``None``.

    .. note::
        The universe will be always set to ``1``. See :attr:`SteamID.id2_zero`.
    """
    search = ID2_REGEX.search(value)

    if search is None:
        return None

    id = (int(search.group("id")) << 1) | int(search.group("reminder"))
    universe = int(search.group("universe"))

    # games before orange box used to incorrectly display universe as 0, we support that
    if universe == 0:
        universe = 1

    return id, EType(1), EUniverse(universe), 1


ID3_REGEX = re.compile(
    rf"\[(?P<type>[i{''.join(ETypeChar._member_map_)}]):"
    r"(?P<universe>[0-4]):"
    r"(?P<id>\d{1,10})"
    r"(:(?P<instance>\d+))?]",
)


def id3_to_tuple(value: str) -> Optional[Tuple[int, EType, EUniverse, int]]:
    """Convert a Steam ID3 into its component parts.

    Parameters
    ----------
    value: :class:`str`
        The ID3 e.g. ``[U:1:1234]``.

    Returns
    -------
    Optional[Tuple[:class:`int`, :class:`.EType`, :class:`.EUniverse`, :class:`int`]]
        A tuple of 32 bit ID, type, universe and instance or ``None``
        e.g. (100000, EType.Individual, EUniverse.Public, 1)
    """
    search = ID3_REGEX.search(value)
    if search is None:
        return None

    id = int(search.group("id"))
    universe = EUniverse(int(search.group("universe")))
    type_char = search.group("type").replace("i", "I")
    type = EType(ETypeChar[type_char].value.value)
    instance = search.group("instance")

    if type_char in "gT":
        instance = 0
    elif instance is not None:
        instance = int(instance)
    elif type_char == "L":
        instance = EInstanceFlag.Lobby
    elif type_char == "c":
        instance = EInstanceFlag.Clan
    elif type_char in (EType.Individual, EType.GameServer):
        instance = 1
    else:
        instance = 0

    instance = int(instance)

    return id, type, universe, instance


_INVITE_HEX = "0123456789abcdef"
_INVITE_CUSTOM = "bcdfghjkmnpqrtvw"
_INVITE_VALID = f"{_INVITE_HEX}{_INVITE_CUSTOM}"
_INVITE_MAPPING = dict(zip(_INVITE_HEX, _INVITE_CUSTOM))
_INVITE_INVERSE_MAPPING = dict(zip(_INVITE_CUSTOM, _INVITE_HEX))
INVITE_REGEX = re.compile(rf"(https?://s\.team/p/(?P<code1>[\-{_INVITE_VALID}]+))|(?P<code2>[\-{_INVITE_VALID}]+)")


def invite_code_to_tuple(code: str) -> Optional[Tuple[int, EType, EUniverse, int]]:
    """
    Parameters
    ----------
    code: :class:`str`
        The invite code e.g. ``cv-dgb``

    Returns
    -------
    Optional[Tuple[:class:`int`, :class:`.EType`, :class:`.EUniverse`, :class:`int`]]
        A tuple of 32 bit ID, type, universe and instance or ``None``
        e.g. (100000, EType.Individual, EUniverse.Public, 1) or ``None``.
    """
    search = INVITE_REGEX.search(code)

    if not search:
        return None

    code = (search.group("code1") or search.group("code2")).replace("-", "")

    def repl_mapper(x: re.Match) -> str:
        return _INVITE_INVERSE_MAPPING[x.group()]

    id = int(re.sub(f"[{_INVITE_CUSTOM}]", repl_mapper, code), 16)

    if 0 < id < 2 ** 32:
        return id, EType(1), EUniverse.Public, 1


URL_REGEX = re.compile(
    r"(?P<clean_url>(?:http[s]?://|)(?:www\.|)steamcommunity\.com/(?P<type>profiles|id|gid|groups)/(?P<value>.+))"
)


async def id64_from_url(
    url: Optional[str], session: Optional[aiohttp.ClientSession] = None, timeout: float = 30
) -> Optional[int]:
    """Takes a Steam Community url and returns steam64 or ``None``.

    .. note::
        Each call makes a http request to https://steamcommunity.com.

    .. note::
        Example URLs
            https://steamcommunity.com/gid/[g:1:4]

            https://steamcommunity.com/gid/103582791429521412

            https://steamcommunity.com/groups/Valve

            https://steamcommunity.com/profiles/[U:1:12]

            https://steamcommunity.com/profiles/76561197960265740

            https://steamcommunity.com/id/johnc

    Parameters
    ----------
    url: :class:`str`
        The Steam community url.
    session: Optional[:class:`aiohttp.ClientSession`]
        The session to make the request with. If ``None`` is passed a new one is generated.
    timeout: Optional[:class:`float`]
        How long to wait on http request before turning ``None``.

    Returns
    -------
    Optional[:class:`int`]
        The found 64 bit ID or ``None`` if ``https://steamcommunity.com`` is down or no matching account is found.
    """

    search = URL_REGEX.search(str(url).rstrip("/"))

    if search is None:
        return None

    gave_session = bool(session)
    session = session or aiohttp.ClientSession()

    try:
        if search.group("type") in ("id", "profiles"):
            # user profile
            r = await session.get(search.group("clean_url"), timeout=timeout)
            text = await r.text()
            data_match = re.search(r"g_rgProfileData\s*=\s*(?P<json>{.*?});\s*", text)
            data = json.loads(data_match.group("json"))
        else:
            # group profile
            r = await session.get(search.group("clean_url"), timeout=timeout)
            text = await r.text()
            data = re.search(r"OpenGroupChat\(\s*'(?P<steamid>\d+)'\s*\)", text)
        return int(data["steamid"])
    except (TypeError, AttributeError):
        return None
    finally:
        if not gave_session:
            await session.close()


def parse_trade_url(url: str) -> Optional["re.Match[str]"]:
    """Parses a trade URL for useful information.

    Parameters
    -----------
    url: :class:`str`
        The trade URL to search.

    Returns
    -------
    Optional[re.Match[:class:`str`]]
        The :class:`re.Match` object with ``token`` and ``user_id`` :meth:`re.Match.group` objects or ``None``
    """
    return re.search(
        r"(?:http[s]?://|)(?:www.|)steamcommunity.com/tradeoffer/new/\?partner=(?P<user_id>\d{,10})"
        r"&token=(?P<token>[\w-]{7,})",
        html.unescape(str(url)),
    )


# some backports


# TODO make a custom cancellable Executor
def to_thread(callable: Callable[..., _T], *args, **kwargs) -> Coroutine[None, None, _T]:  # asyncio.to_thread
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    partial = functools.partial(ctx.run, callable, *args, **kwargs)
    return loop.run_in_executor(None, partial)


_NOT_FOUND = object()


class cached_property:  # functools.cached_property
    __slots__ = ("func", "attr_name", "__doc__")

    def __init__(self, func: Callable[[Any], _T]):
        self.func = func
        self.attr_name: Optional[str] = None
        self.__doc__ = func.__doc__

    def __set_name__(self, _, name: str) -> None:
        if self.attr_name is None:
            self.attr_name = name

    def __get__(self, instance: Optional[Any], _) -> Union[_T, "cached_property"]:
        if instance is None:
            return self
        cache = instance.__dict__  # errors here for classes with slots
        value = cache.get(self.attr_name, _NOT_FOUND)
        if value is _NOT_FOUND:
            value = self.func(instance)
            cache[self.attr_name] = value
        return value


class async_property(property):
    """
    A way to create async properties nicely.

    class CoolClass:
        def __init__(self, var):
            self._read_only_var = var

        @async_property:
        async def var(self):
            await self.process_var()
            return self._read_only_var
    """

    def getter(self, fget: Callable[[Any], Awaitable[Any]]) -> "async_property":
        return super().getter(fget)

    def setter(self, fset: Callable[[Any, Any], Awaitable[None]]) -> "async_property":
        return super().setter(fset)

    def deleter(self, fdel: Callable[[Any], Awaitable[None]]) -> "async_property":
        return super().deleter(fdel)

    def __set__(self, obj: Any, value: Any) -> None:
        if self.fset is None:
            raise AttributeError("can't set attribute")
        asyncio.create_task(self.fset(obj, value))

    def __delete__(self, obj: Any) -> None:
        if self.fdel is None:
            raise AttributeError("can't delete attribute")
        asyncio.create_task(self.fdel(obj))


def ainput(prompt: str = "") -> Awaitable[str]:
    return to_thread(input, prompt)


def contains_bbcode(string: str) -> bool:
    bbcodes = [
        "me",
        "code",
        "pre",
        "giphy",
        "spoiler",
        "quote",
        "random",
        "flip",
        "store",
    ]
    for bbcode in bbcodes:
        if string.startswith(f"/{bbcode}"):
            return True

    return False


def chunk(iterable: Sequence[_T], size: int) -> List[Sequence[_T]]:
    def chunker() -> Generator[Sequence[_T], None, None]:
        for i in range(0, len(iterable), size):
            yield iterable[i : i + size]

    return list(chunker())


# everything below here is directly from discord.py's utils
# https://github.com/Rapptz/discord.py/blob/master/discord/utils.py


def find(predicate: Callable[[_T], bool], iterable: Iterable[_T]) -> Optional[_T]:
    """A helper to return the first element found in the sequence.

    Parameters
    -----------
    predicate: Callable[[T], bool]
        A function that returns a boolean and takes an element from the ``iterable`` as its first argument.
    iterable: Iterable[T]
        The iterable to search through.

    Returns
    -------
    Optional[T]
        The first element from the ``iterable`` for which the ``predicate`` returns ``True`` or if no matching element
        was found returns ``None``.
    """

    for element in iterable:
        if predicate(element):
            return element
    return None


def get(iterable: Iterable[_T], **attrs) -> Optional[_T]:
    r"""A helper that returns the first element in the iterable that meets all the traits passed in ``attrs``. This
    is an alternative for :func:`utils.find`.

    Parameters
    -----------
    iterable: Iterable[T]
        An iterable to search through.
    \*\*attrs
        Keyword arguments that denote attributes to match.

    Returns
    -------
    Optional[T]
        The first element from the ``iterable`` which matches all the traits passed in ``attrs`` or ``None`` if no
        matching element was found.
    """

    # global -> local
    _all = all
    attrget = attrgetter

    # Special case the single element call
    if len(attrs) == 1:
        k, v = attrs.popitem()
        pred = attrget(k.replace("__", "."))
        for elem in iterable:
            if pred(elem) == v:
                return elem
        return None

    converted = [(attrget(attr.replace("__", ".")), value) for attr, value in attrs.items()]

    for elem in iterable:
        if _all(pred(elem) == value for pred, value in converted):
            return elem
    return None


async def maybe_coroutine(func: Callable[..., Union[_T, Awaitable[_T]]], *args, **kwargs) -> _T:
    value = func(*args, **kwargs)
    if isawaitable(value):
        return await value
    return value
