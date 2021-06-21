"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import html
import json
import re
import struct
import sys
from collections.abc import Awaitable, Callable, Coroutine, Generator, Iterable, Sized
from inspect import isawaitable
from io import BytesIO
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, Optional, SupportsInt, TypeVar, Union, overload

import aiohttp
from typing_extensions import Final, Literal, ParamSpec, Protocol, TypeAlias

from .enums import InstanceFlag, Type, TypeChar, Universe
from .errors import InvalidSteamID

if TYPE_CHECKING:
    from typing import SupportsIndex  # doesn't exist in 3.7

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)
_P = ParamSpec("_P")
_PROTOBUF_MASK = 0x80000000

# from ValvePython/steam


def is_proto(emsg: int) -> bool:
    return (int(emsg) & _PROTOBUF_MASK) > 0


def set_proto_bit(emsg: int) -> int:
    return int(emsg) | _PROTOBUF_MASK


def clear_proto_bit(emsg: int) -> int:
    return int(emsg) & ~_PROTOBUF_MASK


Intable: TypeAlias = "Union[SupportsInt, SupportsIndex, str, bytes]"  # anything int(x) wouldn't normally fail on


# fmt: off
TypeType = Union[
    Type,
    Literal[
        "Invalid", "Individual", "Multiseat", "GameServer", "AnonGameServer", "Pending", "ContentServer", "Clan",
        "Chat", "ConsoleUser", "AnonUser", "Max",
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
    ],
]
UniverseType = Union[Universe, Literal["Invalid ", "Public", "Beta", "Internal", "Dev", "Max", 0, 1, 2, 3, 4, 5, 6]]
InstanceType = Literal[0, 1]
# fmt: on


@overload
def make_id64() -> Literal[0]:
    ...


@overload
def make_id64(
    id: Intable = 0,
    type: Optional[TypeType] = None,
    universe: Optional[UniverseType] = None,
    instance: Optional[InstanceType] = None,
) -> int:
    ...


def make_id64(
    id: Intable = 0,
    type: Optional[TypeType] = None,
    universe: Optional[UniverseType] = None,
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
    :exc:`.InvalidSteamID`
        The created SteamID would be invalid.

    Returns
    -------
    :class:`int`
        The 64 bit Steam ID.
    """
    if not any((id, type, universe, instance)):
        return 0

    try:
        id = int(id)
    except (ValueError, TypeError):
        # textual input e.g. [g:1:4]
        try:
            id, type, universe, instance = id2_to_tuple(id) or id3_to_tuple(id)
        except TypeError:
            raise InvalidSteamID(id, "it cannot be parsed") from None
    else:
        # numeric input
        # 32 bit account id
        if 0 <= id < 2 ** 32:
            type = type or Type.Individual
            universe = universe or Universe.Public
        # 64 bit
        elif 2 ** 32 < id < 2 ** 64:
            value = id
            id = id & 0xFFFFFFFF
            instance = (value >> 32) & 0xFFFFF
            type = (value >> 52) & 0xF
            universe = (value >> 56) & 0xFF
        else:
            raise InvalidSteamID(id, "it is too large" if id > 2 ** 64 else "it is too small")

        try:
            type = Type(type) if isinstance(type, int) else Type[type]
        except (KeyError, ValueError):
            raise InvalidSteamID(id, f"{type!r} is not a valid Type") from None
        try:
            universe = Universe(universe) if isinstance(universe, int) else Universe[universe]
        except (KeyError, ValueError):
            raise InvalidSteamID(id, f"{universe!r} is not a valid Universe") from None

    if instance is None:
        instance = 1 if type in (Type.Individual, Type.GameServer) else 0

    return universe << 56 | type << 52 | instance << 32 | id


ID2_REGEX = re.compile(r"STEAM_(?P<universe>\d+):(?P<remainder>[0-1]):(?P<id>\d+)")


def id2_to_tuple(value: str) -> Optional[tuple[int, Literal[Type.Individual], Literal[Universe.Public], Literal[1]]]:
    """
    Parameters
    ----------
    value: :class:`str`
        steam2 e.g. ``STEAM_1:0:1234``.

    Returns
    -------
    Optional[tuple[:class:`int`, :class:`.Type`, :class:`.Universe`, :class:`int`]]
        A tuple of 32 bit ID, type, universe and instance or ``None``
        e.g. (100000, Type.Individual, Universe.Public, 1).

    Note
    ----
    The universe will be always set to ``1``. See :attr:`SteamID.id2_zero`.
    """
    search = ID2_REGEX.search(value)

    if search is None:
        return None

    id = (int(search["id"]) << 1) | int(search["remainder"])
    universe = int(search["universe"])

    # games before orange box used to incorrectly display universe as 0, we support that
    if universe == 0:
        universe = 1

    return id, Type(1), Universe(universe), 1


ID3_REGEX = re.compile(
    rf"\[(?P<type>[i{''.join(TypeChar._member_map_)}]):"
    r"(?P<universe>[0-4]):"
    r"(?P<id>\d{1,10})"
    r"(:(?P<instance>\d+))?]",
)


def id3_to_tuple(value: str) -> Optional[tuple[int, Type, Universe, int]]:
    """Convert a Steam ID3 into its component parts.

    Parameters
    ----------
    value: :class:`str`
        The ID3 e.g. ``[U:1:1234]``.

    Returns
    -------
    Optional[tuple[:class:`int`, :class:`.Type`, :class:`.Universe`, :class:`int`]]
        A tuple of 32 bit ID, type, universe and instance or ``None``
        e.g. (100000, Type.Individual, Universe.Public, 1)
    """
    search = ID3_REGEX.search(value)
    if search is None:
        return None

    id = int(search["id"])
    universe = Universe(int(search["universe"]))
    type_char = search["type"].replace("i", "I")
    type = Type(TypeChar[type_char].value.value)
    instance = search["instance"]

    if type_char in "gT":
        instance = 0
    elif instance is not None:
        instance = int(instance)
    elif type_char == "L":
        instance = InstanceFlag.Lobby
    elif type_char == "c":
        instance = InstanceFlag.Clan
    elif type_char in (Type.Individual, Type.GameServer):
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
INVITE_REGEX = re.compile(rf"(https?://s\.team/p/(?P<code_1>[\-{_INVITE_VALID}]+))|(?P<code_2>[\-{_INVITE_VALID}]+)")


def invite_code_to_tuple(
    code: str,
) -> Optional[tuple[int, Literal[Type.Individual], Literal[Universe.Public], Literal[1]]]:
    """
    Parameters
    ----------
    code: :class:`str`
        The invite code e.g. ``cv-dgb``

    Returns
    -------
    Optional[tuple[:class:`int`, :class:`.Type`, :class:`.Universe`, :class:`int`]]
        A tuple of 32 bit ID, type, universe and instance or ``None``
        e.g. (100000, Type.Individual, Universe.Public, 1).
    """
    search = INVITE_REGEX.search(code)

    if not search:
        return None

    code = (search.group("code_1") or search.group("code_2")).replace("-", "")

    id = int(re.sub(f"[{_INVITE_CUSTOM}]", lambda m: _INVITE_INVERSE_MAPPING[m.group()], code), 16)

    if 0 < id < 2 ** 32:
        return id, Type(1), Universe.Public, 1


URL_REGEX = re.compile(
    r"(?P<clean_url>(?:http[s]?://)?(?:www\.)?steamcommunity\.com/(?P<type>profiles|id|gid|groups)/(?P<value>.+))/?"
)


async def id64_from_url(url: aiohttp.client.StrOrURL, session: Optional[aiohttp.ClientSession] = None) -> Optional[int]:
    """Takes a Steam Community url and returns 64 bit steam ID or ``None``.

    Notes
    -----
    - Each call makes a http request to https://steamcommunity.com.

    - Example URLs:
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

    Returns
    -------
    Optional[:class:`int`]
        The found 64 bit ID or ``None`` if ``https://steamcommunity.com`` is down or no matching account is found.
    """

    search = URL_REGEX.search(str(url))

    if search is None:
        return None

    gave_session = session is not None
    session = session or aiohttp.ClientSession()

    try:
        if search["type"] in ("id", "profiles"):
            # user profile
            r = await session.get(search["clean_url"])
            text = await r.text()
            data_match = re.search(r"g_rgProfileData\s*=\s*(?P<json>{.*?});\s*", text)
            data = json.loads(data_match["json"])
        else:
            # group profile
            r = await session.get(search["clean_url"])
            text = await r.text()
            data = re.search(r"OpenGroupChat\(\s*'(?P<steamid>\d+)'\s*\)", text)
        return int(data["steamid"])
    except (TypeError, AttributeError):
        return None
    finally:
        if not gave_session:
            await session.close()


def parse_trade_url(url: str) -> Optional[re.Match[str]]:
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
        r"(?:http[s]?://)?(?:www\.)?steamcommunity\.com/tradeoffer/new/\?partner=(?P<user_id>\d{,10})"
        r"&token=(?P<token>[\w-]{7,})",
        html.unescape(str(url)),
    )


# some backports
# TODO make a custom cancellable Executor
if sys.version_info >= (3, 9):
    from asyncio import to_thread
else:

    def to_thread(callable: Callable[..., _T], *args: Any, **kwargs: Any) -> asyncio.Future[_T]:
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        partial = functools.partial(ctx.run, callable, *args, **kwargs)
        return loop.run_in_executor(None, partial)


class cached_property(Generic[_T]):
    __slots__ = ("function", "__doc__")

    def __init__(self, function: Callable[[Any], _T]):
        self.function = function
        self.__doc__ = getattr(function, "__doc__", None)

    def __get__(self, instance: Optional[Any], _) -> Union[_T, cached_property]:
        if instance is None:
            return self

        value = self.function(instance)
        setattr(instance, self.function.__name__, value)

        return value


if TYPE_CHECKING:
    from functools import cached_property as cached_property


def ainput(prompt: str = "") -> Coroutine[None, None, str]:
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
        "emoticon",
        "tradeofferlink",
        "tradeoffer",
        "sticker",
        "gameinvite",
        "og",
        "roomeffect",
        "img",
        "url",
    ]
    return any(string.startswith(f"/{bbcode}") for bbcode in bbcodes)


class SupportsChunk(Protocol[_T_co], Sized):
    def __getitem__(self, item: slice) -> _T_co:
        ...


def chunk(iterable: SupportsChunk[_T_co], size: int) -> Generator[_T_co, None, None]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


PACK_FORMATS: Final[dict[str, str]] = {
    "i8": "b",
    "u8": "B",
    "i16": "h",
    "u16": "H",
    "i32": "i",
    "u32": "I",
    "i64": "q",
    "u64": "Q",
    "long": "l",
    "ulong": "L",
    "f32": "f",
    "f64": "d",
}


class StructIOMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any]) -> StructIOMeta:
        for method_name, format in PACK_FORMATS.items():
            exec(f"def write_{method_name}(self, item): self.write_struct('<{format}', item)", {}, namespace)
            exec(
                f"def read_{method_name}(self):"
                f"return self.read_struct('<{format}', {struct.calcsize(f'<{format}')})[0]",
                {},
                namespace,
            )

        return super().__new__(mcs, name, bases, namespace)


class StructIO(BytesIO, metaclass=StructIOMeta):
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(buffer={self.buffer!r}, position={self.position})"

    @property
    def buffer(self) -> bytes:
        return self.getvalue()

    @property
    def position(self) -> int:
        return self.tell()

    def read_struct(self, format: str, position: Optional[int] = None) -> tuple:
        buffer = self.read(position or struct.calcsize(format))
        return struct.unpack(format, buffer)

    def write_struct(self, format: str, *to_write: Any) -> None:
        self.write(struct.pack(format, *to_write))

    def read_cstring(self, terminator=b"\x00") -> bytes:
        starting_position = self.position
        data = self.read()
        null_index = data.find(terminator)
        if null_index == -1:
            raise RuntimeError("Reached end of buffer")
        result = data[:null_index]  # bytes without the terminator
        self.seek(starting_position + null_index + len(terminator))  # advance offset past terminator
        return result

    if TYPE_CHECKING:
        # added by the metaclass
        # fmt: off
        def read_i8(self) -> int: ...
        def write_i8(self, item: int) -> None: ...
        def read_u8(self) -> int: ...
        def write_u8(self, item: int) -> None: ...
        def read_i16(self) -> int: ...
        def write_i16(self, item: int) -> None: ...
        def read_u16(self) -> int: ...
        def write_u16(self, item: int) -> None: ...
        def read_i32(self) -> int: ...
        def write_i32(self, item: int) -> None: ...
        def read_u32(self) -> int: ...
        def write_u32(self, item: int) -> None: ...
        def read_i64(self) -> int: ...
        def write_i64(self, item: int) -> None: ...
        def read_u64(self) -> int: ...
        def write_u64(self, item: int) -> None: ...
        def read_f32(self) -> float: ...
        def write_f32(self, item: float) -> None: ...
        def read_f64(self) -> float: ...
        def write_f64(self, item: float) -> None: ...
        def read_long(self) -> int: ...
        def write_long(self, item: int) -> None: ...
        def read_ulong(self) -> int: ...
        def write_ulong(self, item: int) -> None: ...
        # fmt: on


# everything below here is directly from discord.py's utils
# https://github.com/Rapptz/discord.py/blob/master/discord/utils.py
def find(predicate: Callable[[_T], bool], iterable: Iterable[_T]) -> Optional[_T]:
    """A helper to return the first element found in the sequence.

    Parameters
    -----------
    predicate: Callable[[T], :class:`bool`]
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


def get(iterable: Iterable[_T], **attrs: Any) -> Optional[_T]:
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


async def maybe_coroutine(
    func: Callable[_P, Union[_T, Awaitable[_T]]],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    value = func(*args, **kwargs)
    if isawaitable(value):
        return await value
    return value
