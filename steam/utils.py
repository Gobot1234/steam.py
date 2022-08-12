"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/Rapptz/discord.py/blob/master/discord/utils.py
The appropriate licenses are in LICENSE
"""

from __future__ import annotations

import abc
import asyncio
import collections
import functools
import html
import re
import struct
from collections.abc import Awaitable, Callable, Coroutine, Generator, Iterable, Mapping
from datetime import datetime, timezone
from inspect import getmembers, isawaitable
from io import BytesIO
from itertools import zip_longest
from operator import attrgetter
from types import MemberDescriptorType
from typing import TYPE_CHECKING, Any, Final, Generic, ParamSpec, TypeVar, cast, overload

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from typing_extensions import Self

from .enums import _is_descriptor, classproperty as classproperty
from .id import (
    MISSING as MISSING,
    parse_id2 as parse_id2,
    parse_id3 as parse_id3,
    parse_id64 as parse_id64,
    parse_invite_code as parse_invite_code,
)

if TYPE_CHECKING:
    from .types.http import StrOrURL


_T = TypeVar("_T")
_P = ParamSpec("_P")
_PROTOBUF_MASK = 0x80000000


# inlined as these are some of the most called functions in the library
is_proto: Callable[[int], bool] = _PROTOBUF_MASK.__and__  # type: ignore  # this is boolean like for a bit of extra speed
set_proto_bit = _PROTOBUF_MASK.__or__
clear_proto_bit = (~_PROTOBUF_MASK).__and__


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
    return asyncio.to_thread(input, prompt)


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

    return next((element for element in iterable if predicate(element)), None)


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
        return next((elem for elem in iterable if pred(elem) == v), None)
    converted = [(attrget(attr.replace("__", ".")), value) for attr, value in attrs.items()]

    return next(
        (elem for elem in iterable if _all(pred(elem) == value for pred, value in converted)),
        None,
    )


async def maybe_coroutine(
    func: Callable[_P, _T | Awaitable[_T]],
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    value = func(*args, **kwargs)
    return await value if isawaitable(value) else value  # type: ignore
