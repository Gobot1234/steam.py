"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
https://github.com/Rapptz/discord.py/blob/master/discord/utils.py
The appropriate licenses are in LICENSE
"""

from __future__ import annotations

import abc
import asyncio
import collections
import contextvars
import functools
import html
import json
import re
import struct
import sys
from collections.abc import Awaitable, Callable, Coroutine, Generator, Iterable, Mapping
from datetime import datetime, timezone
from inspect import getmembers, isawaitable
from io import BytesIO
from itertools import zip_longest
from operator import attrgetter
from types import MemberDescriptorType
from typing import TYPE_CHECKING, Any, Generic, SupportsInt, TypeVar, cast, overload

import aiohttp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from typing_extensions import Final, Literal, ParamSpec, Self, TypeAlias

from .enums import InstanceFlag, Type, TypeChar, Universe, _is_descriptor, classproperty as classproperty
from .errors import InvalidSteamID

if TYPE_CHECKING:
    from typing import SupportsIndex  # doesn't exist in 3.7

    from .types.http import StrOrURL
    from .types.id import ID32, ID64


_T = TypeVar("_T")
_P = ParamSpec("_P")
_PROTOBUF_MASK = 0x80000000


def is_proto(emsg: int) -> bool:
    return emsg & _PROTOBUF_MASK  # type: ignore  # this is boolean like for a bit of extra speed


def set_proto_bit(emsg: int) -> int:
    return emsg | _PROTOBUF_MASK


def clear_proto_bit(emsg: int) -> int:
    return emsg & ~_PROTOBUF_MASK


Intable: TypeAlias = "SupportsInt | SupportsIndex | str | bytes"  # anything int(x) wouldn't normally fail on
TypeType: TypeAlias = """
Type | Literal[
    'Invalid', 'Individual', 'Multiseat', 'GameServer', 'AnonGameServer', 'Pending', 'ContentServer', 'Clan',
    'Chat', 'ConsoleUser', 'AnonUser', 'Max', 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
]
"""
UniverseType: TypeAlias = """
    Universe | Literal['Invalid', 'Public', 'Beta', 'Internal', 'Dev', 'Max', 0, 1, 2, 3, 4, 5, 6]
"""
InstanceType: TypeAlias = "InstanceFlag | str | int"


def make_id64(
    id: Intable = 0,
    type: TypeType | None = None,
    universe: UniverseType | None = None,
    instance: InstanceType | None = None,
) -> ID64:
    """Convert various representations of Steam IDs to its Steam 64-bit ID.

    Parameters
    ----------
    id
        The ID to convert.
    type
        The type of the ID. Can be the name, the integer value of the type or the recommended way is to use
        :class:`steam.Type`\\.
    universe
        The universe of the ID. Can be the name, the integer value of the universe or the recommended way is to use
        :class:`steam.Universe`\\.
    instance
        The instance of the ID.

    Examples
    --------
    .. code-block:: python3

        make_id64()  # invalid
        make_id64(12345)
        make_id64("12345")  # account ids
        make_id64(12345, type=steam.Type.Clan)  # makes the clan id into a clan id64
        make_id64(103582791429521412)
        make_id64("103582791429521412")  # id64s
        make_id64("STEAM_1:0:2")  # id2
        make_id64("[g:1:4]")  # id3

    Raises
    ------
    :exc:`.InvalidSteamID`
        The created 64-bit Steam ID would be invalid.

    Returns
    -------
    The 64 bit Steam ID.
    """
    # format of a 64-bit steam ID:
    # 0b0000000100010000000000000000000100010001001001110100110011000010
    #   └───┰──┘└─┰┘└─────────┰────────┘└──────────────┰───────────────┘
    #       │     │           │                        │
    #   universe  └ type      │                        │
    #   (8 bits)    (4 bits)  └ instance (20 bits)     │
    #                                                  └  account id
    #                                                     (32 bits)
    if not any((id, type, universe, instance)):
        return 0

    try:
        id = int(id)
    except ValueError:
        # textual input e.g. [g:1:4]
        try:
            id, type, universe, instance = id2_to_tuple(id) or id3_to_tuple(id)
        except TypeError:
            raise InvalidSteamID(id, "it cannot be parsed") from None
    else:
        # numeric input
        # 32 bit account id
        if 0 <= id < 2**32:
            type = type or Type.Individual
            universe = universe or Universe.Public
        # 64 bit
        elif id < 2**64:
            value = id
            id = id & 0xFFFFFFFF
            instance = (value >> 32) & 0xFFFFF
            type = (value >> 52) & 0xF
            universe = (value >> 56) & 0xFF
        else:
            raise InvalidSteamID(id, "it is too large" if id > 2**64 else "it is too small")

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


ID2_REGEX = re.compile(r"STEAM_(?P<universe>\d+):(?P<remainder>[0-1]):(?P<id>\d{1,10})")


def id2_to_tuple(value: str) -> tuple[ID32, Literal[Type.Individual], Universe, Literal[InstanceFlag.Desktop]] | None:
    """Convert an ID2 into its component parts.

    Parameters
    ----------
    value
        The ID2 e.g. ``STEAM_1:0:1234``.

    Note
    ----
    The universe will be always set to ``1``. See :attr:`SteamID.id2_zero`.

    Returns
    -------
    A tuple of 32 bit ID, type, universe and instance or ``None``

    e.g. (100000, Type.Individual, Universe.Public, InstanceFlag.Desktop).
    """
    search = ID2_REGEX.search(value)

    if search is None:
        return None

    id = (int(search["id"]) << 1) | int(search["remainder"])
    universe = int(search["universe"])

    # games before orange box used to incorrectly display universe as 0, we support that
    if universe == 0:
        universe = 1

    return id, Type.Individual, Universe(universe), InstanceFlag.Desktop


ID3_REGEX = re.compile(
    rf"\[(?P<type>[i{''.join(TypeChar._member_map_)}]):"
    r"(?P<universe>[0-4]):"
    r"(?P<id>[0-9]{1,10})"
    r"(:(?P<instance>\d+))?]",
)


def id3_to_tuple(value: str) -> tuple[ID32, Type, Universe, InstanceFlag] | None:
    """Convert a Steam ID3 into its component parts.

    Parameters
    ----------
    value
        The ID3 e.g. ``[U:1:1234]``.

    Returns
    -------
    A tuple of 32 bit ID, type, universe and instance or ``None``

    e.g. (100000, Type.Individual, Universe.Public, InstanceFlag.Desktop)
    """
    search = ID3_REGEX.search(value)
    if search is None:
        return None

    id = int(search["id"])
    universe = Universe(int(search["universe"]))
    type_char = search["type"].replace("i", "I")
    type = Type(TypeChar[type_char])
    instance_ = search["instance"]

    if type_char in "gT" or instance_ is None:
        instance = InstanceFlag.All
    else:
        instance = InstanceFlag.try_value(int(instance_))
    if type_char == "L":
        instance |= InstanceFlag.ChatLobby
    if type_char == "c":
        instance |= InstanceFlag.ChatClan
    if type_char in (Type.Individual, Type.GameServer):
        instance = InstanceFlag.Desktop

    return id, type, universe, instance


_INVITE_HEX = "0123456789abcdef"
_INVITE_CUSTOM = "bcdfghjkmnpqrtvw"
_INVITE_VALID = f"{_INVITE_HEX}{_INVITE_CUSTOM}"
_INVITE_MAPPING = dict(zip(_INVITE_HEX, _INVITE_CUSTOM))
_INVITE_INVERSE_MAPPING = dict(zip(_INVITE_CUSTOM, _INVITE_HEX))
INVITE_REGEX = re.compile(rf"(https?://s\.team/p/(?P<code_1>[\-{_INVITE_VALID}]+))|(?P<code_2>[\-{_INVITE_VALID}]+)")


def invite_code_to_tuple(
    code: str,
) -> tuple[ID32, Literal[Type.Individual], Literal[Universe.Public], Literal[InstanceFlag.Desktop]] | None:
    """Convert an invitation code into its component parts.

    Parameters
    ----------
    code
        The invite code e.g. ``cv-dgb``

    Returns
    -------
    A tuple of 32 bit ID, type, universe and instance or ``None``

    e.g. (100000, Type.Individual, Universe.Public, InstanceFlag.Desktop).
    """
    search = INVITE_REGEX.search(code)

    if not search:
        return None

    code = (search["code_1"] or search["code_2"]).replace("-", "")

    id = int(re.sub(f"[{_INVITE_CUSTOM}]", lambda m: _INVITE_INVERSE_MAPPING[m.group()], code), 16)

    if 0 < id < 2**32:
        return id, Type.Individual, Universe.Public, InstanceFlag.Desktop


URL_REGEX = re.compile(
    r"(?P<clean_url>https?(www\.)?://steamcommunity\.com/(?P<type>profiles|id|gid|groups|app|games)/(?P<value>.+))"
)
USER_ID64_FROM_URL_REGEX = re.compile(r"g_rgProfileData\s*=\s*(?P<json>{.*?});\s*")
CLAN_ID64_FROM_URL_REGEX = re.compile(r"OpenGroupChat\(\s*'(?P<steamid>\d+)'\s*\)")


async def id64_from_url(url: StrOrURL, session: aiohttp.ClientSession | None = None) -> ID64 | None:
    """Takes a Steam Community url and returns 64-bit Steam ID or ``None``.

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

        https://steamcommunity.com/app/570

    Parameters
    ----------
    url
        The Steam community url.
    session
        The session to make the request with. If ``None`` is passed a new one is generated.

    Returns
    -------
    The found 64-bit ID or ``None`` if ``https://steamcommunity.com`` is down or no matching account is found.
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
            data_match = USER_ID64_FROM_URL_REGEX.search(text)
            data = json.loads(data_match["json"])  # type: ignore  # handled by try+except
        else:
            # clan profile
            r = await session.get(search["clean_url"])
            text = await r.text()
            data = CLAN_ID64_FROM_URL_REGEX.search(text)
        return int(data["steamid"])  # type: ignore  # handled by try+except
    except (TypeError, AttributeError):
        return None
    finally:
        if not gave_session:
            await session.close()


def unpad(s: bytes) -> bytes:
    return s[: -s[-1]]


def symmetric_decrypt(text: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    iv = decryptor.update(text[:16])
    decryptor.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    return unpad(decryptor.update(text[16:]))


STEAM_PUBLIC_KEY: Final = rsa.RSAPublicNumbers(
    17,
    int(
        "1572435756163492767473017547683098671778311221560259237468446760604065883521072242173339019599191749864"
        "5577395742561473053175122897795413393419038630648254894306773660858554891146738442477393264257606729213"
        "7056263003121836768211312089498275802694267916711103128551999842076575732754013467986241640244933837449"
    ),
)


def verify_signature(data: bytes, signature: bytes) -> bool:
    try:
        STEAM_PUBLIC_KEY.public_key().verify(signature, data, padding.PKCS1v15(), hashes.SHA1())
    except InvalidSignature:
        return False
    else:
        return True


def parse_trade_url(url: StrOrURL) -> re.Match[str] | None:
    """Parses a trade URL for useful information.

    Parameters
    -----------
    url
        The trade URL to search.

    Returns
    -------
    A :class:`re.Match` object with ``token`` and ``user_id`` :meth:`re.Match.group` objects or ``None``.
    """
    return re.search(
        r"(?:https?://)?(?:www\.)?steamcommunity\.com/tradeoffer/new/?\?partner=(?P<user_id>[0-9]{,10})"
        r"&token=(?P<token>[\w-]{7,})",
        html.unescape(str(url)),
    )


# some backports
# TODO make a custom cancellable Executor
if sys.version_info >= (3, 9):
    from asyncio import to_thread
else:

    async def to_thread(callable: Callable[_P, _T], *args: _P.args, **kwargs: _P.kwargs) -> _T:
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        partial = functools.partial(ctx.run, callable, *args, **kwargs)
        return await loop.run_in_executor(None, partial)


_SelfT = TypeVar("_SelfT")
_T_co = TypeVar("_T_co", covariant=True)


class cached_property(Generic[_SelfT, _T_co]):
    __slots__ = ("function", "__doc__")

    def __init__(self, function: Callable[[_SelfT], _T_co]):
        self.function = function
        self.__doc__: str | None = getattr(function, "__doc__", None)

    @overload
    def __get__(self, instance: None, _) -> Self:
        ...

    @overload
    def __get__(self, instance: _SelfT, _) -> _T_co:
        ...

    def __get__(self, instance: _SelfT | None, _) -> _T_co | Self:
        if instance is None:
            return self

        value = self.function(instance)
        setattr(instance, self.function.__name__, value)

        return value


class cached_slot_property(cached_property[_SelfT, _T_co]):
    @overload
    def __get__(self, instance: None, _) -> Self:
        ...

    @overload
    def __get__(self, instance: _SelfT, _) -> _T_co:
        ...

    def __get__(self, instance: _SelfT | None, _) -> _T_co | Self:
        if instance is None:
            return self

        slot_name = f"_{self.function.__name__}_cs"
        try:
            return getattr(instance, slot_name)
        except AttributeError:
            value = self.function(instance)
            setattr(instance, slot_name, value)
            return value


def ainput(prompt: str = "") -> Coroutine[None, None, str]:
    return to_thread(input, prompt)


def contains_bbcode(string: str) -> bool:
    bbcodes = {
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
    }
    return any(string.startswith(f"/{bbcode}") for bbcode in bbcodes)


def _get_avatar_url(sha: bytes) -> str:
    hexed = sha.hex()
    hash = hexed if hexed != "\x00" * 20 else "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"
    return f"https://avatars.cloudflare.steamstatic.com/{hash}_full.jpg"


def chunk(iterable: Iterable[_T], size: int) -> Generator[list[_T], None, None]:
    chunk: list[_T] = []

    for element in iterable:
        if len(chunk) == size:
            yield chunk
            chunk = []
        chunk.append(element)

    yield chunk


def _int_chunks(len: int, size: int) -> Generator[tuple[int, int], None, None]:
    idxs = range(0, len, size)
    second = iter(idxs)
    next(second)
    yield from zip_longest(idxs, second, fillvalue=len)


def update_class(
    instance: Any,
    new_instance: Any,
) -> Any:  # technically _T1 & _T2
    cls = instance.__class__
    is_descriptor = _is_descriptor

    for name, attr in getmembers(instance):
        attr = getattr(instance, name)
        cls_attr = getattr(cls, name, None)
        if (
            not is_descriptor(cls_attr)
            or isinstance(cls_attr, MemberDescriptorType)  # might be a slot member
            or (isinstance(cls_attr, property) and cls_attr.fset is not None)
        ) and not (name.startswith("__") and name.endswith("__")):
            try:
                setattr(new_instance, name, attr)
            except (AttributeError, TypeError):
                pass

    return new_instance


def call_once(func: Callable[_P, Awaitable[None]]) -> Callable[_P, Awaitable[None]]:
    called = False

    @functools.wraps(func)
    async def inner(*args: _P.args, **kwargs: _P.kwargs) -> None:
        nonlocal called

        if called:  # call becomes a noop
            return await asyncio.sleep(0)

        called = True
        try:
            await func(*args, **kwargs)
        finally:
            called = False

    return inner


class DateTime:
    """UTC aware datetime factory functions."""

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def from_timestamp(timestamp: float) -> datetime:
        return datetime.fromtimestamp(timestamp, timezone.utc)

    @staticmethod
    def strptime(input: str, format: str) -> datetime:
        return datetime.strptime(input, format).replace(tzinfo=timezone.utc)

    @staticmethod
    def parse_steam_date(input: str, *, full_month: bool = True) -> datetime | None:
        if ", " not in input:
            input += f"{input}, {DateTime.now().year}"  # assume current year

        british = input.split()[0].isdigit()  # starts with a number
        format = f"%d %{'B' if full_month else 'b'}, %Y" if british else f"%{'B' if full_month else 'b'} %d, %Y"
        try:
            return DateTime.strptime(input, format)
        except ValueError:
            return None


class AsyncInit(metaclass=abc.ABCMeta):
    __slots__ = ()

    @abc.abstractmethod
    async def __ainit__(self) -> None:
        ...

    async def __await_inner__(self) -> Self:
        await self.__ainit__()
        return self

    def __await__(self) -> Generator[Any, None, Self]:
        return self.__await_inner__().__await__()


PACK_FORMATS: Final = cast("Mapping[str, str]", {
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
})  # fmt: skip


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

    @position.setter
    def position(self, value: int) -> None:
        self.seek(value)

    def read_struct(self, format: str, position: int | None = None) -> tuple[Any, ...]:
        buffer = self.read(position or struct.calcsize(format))
        return struct.unpack(format, buffer)

    def write_struct(self, format: str, *to_write: Any) -> None:
        self.write(struct.pack(format, *to_write))

    def read_cstring(self, terminator: bytes = b"\x00") -> bytes:
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


_KT = TypeVar("_KT")
_VT = TypeVar("_VT")
MISSING: Final[Any] = object()


class ChainMap(collections.ChainMap[_KT, _VT] if TYPE_CHECKING else collections.ChainMap):
    # this is different to the standard library's ChainMap because it is always O(n),
    # keys should be unique between maps
    def __delitem__(self, key: _KT) -> None:
        for map in self.maps:
            try:
                del map[key]
                return
            except KeyError:
                pass
        raise KeyError(key)

    def popitem(self) -> tuple[_KT, _VT]:
        for map in self.maps:
            try:
                return map.popitem()
            except KeyError:
                pass
        raise KeyError()

    def pop(self, key: _KT, default: _T = MISSING) -> _VT | _T:
        for map in self.maps:
            try:
                return map.pop(key)
            except KeyError:
                pass
        if default is not MISSING:
            return default
        raise KeyError(key)

    def clear(self) -> None:
        for map in self.maps:
            map.clear()


# TODO consider in V1 making these allow async iterables after async iterator rework?
# everything below here is directly from discord.py's utils
# https://github.com/Rapptz/discord.py/blob/master/discord/utils.py
def find(predicate: Callable[[_T], bool], iterable: Iterable[_T]) -> _T | None:
    """A helper to return the first element found in the sequence.

    Examples
    --------
    .. code-block:: python3

        first_active_offer = steam.utils.find(
            lambda trade: trade.state == TradeOfferState.Active,
            client.trades,
        )
        # how to get an object using a conditional

    Parameters
    -----------
    predicate
        A function that returns a boolean and takes an element from the ``iterable`` as its first argument.
    iterable
        The iterable to search through.

    Returns
    -------
    The first element from the ``iterable`` for which the ``predicate`` returns ``True`` or if no matching element was
    found returns ``None``.
    """

    for element in iterable:
        if predicate(element):
            return element
    return None


def get(iterable: Iterable[_T], **attrs: Any) -> _T | None:
    """A helper that returns the first element in the iterable that meets all the traits passed in ``attrs``. This
    is an alternative for :func:`find`.

    Examples
    --------
    .. code-block:: python3

        bff = steam.utils.get(client.users, name="Gobot1234")
        trade = steam.utils.get(client.trades, state=TradeOfferState.Active, partner=message.author)
        # multiple attributes are also accepted

    Parameters
    -----------
    iterable
        An iterable to search through.
    attrs
        Keyword arguments that denote attributes to match.

    Returns
    -------
    The first element from the ``iterable`` which matches all the traits passed in ``attrs`` or ``None`` if no matching
    element was found.
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
    func: Callable[_P, _T | Awaitable[_T]],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    value = func(*args, **kwargs)
    if isawaitable(value):
        return await value
    return value  # type: ignore
