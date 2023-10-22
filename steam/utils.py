"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/Rapptz/discord.py/blob/master/discord/utils.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import abc
import asyncio
import base64
import collections
import functools
import html
import itertools
import re
import struct
import sys
import textwrap
import threading
import weakref
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    Awaitable,
    Callable,
    Generator,
    Iterable,
    Iterator,
    Mapping,
    Sized,
)
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from inspect import getmembers, isawaitable
from io import BytesIO
from itertools import zip_longest
from operator import attrgetter
from types import MemberDescriptorType
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    Final,
    Generic,
    Literal,
    ParamSpec,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
    overload,
)

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ._const import JSON_LOADS, MISSING, UNIX_EPOCH, URL
from .enums import Type, _is_descriptor, classproperty as classproperty
from .id import _URL_START, ID, id64_from_url as id64_from_url, parse_id64 as parse_id64

if TYPE_CHECKING:
    from typing_extensions import Self, deprecated

    from .types.http import Coro, StrOrURL
    from .types.user import IndividualID


_T = TypeVar("_T")
_P = ParamSpec("_P")


def unpad(s: bytes, /) -> bytes:
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
        (
            "1572435756163492767473017547683098671778311221560259237468446760604065883521072242173339019599191749864"
            "5577395742561473053175122897795413393419038630648254894306773660858554891146738442477393264257606729213"
            "7056263003121836768211312089498275802694267916711103128551999842076575732754013467986241640244933837449"
        )
    ),
)


def verify_signature(data: bytes, signature: bytes) -> bool:
    try:
        STEAM_PUBLIC_KEY.public_key().verify(signature, data, padding.PKCS1v15(), hashes.SHA1())
    except InvalidSignature:
        return False
    else:
        return True


@dataclass(slots=True)
class TradeURLInfo:
    id: IndividualID
    token: str | None = None

    @property
    def url(self) -> str:
        """The full trade URL."""
        url = URL.COMMUNITY / "tradeoffer/new" % {"partner": self.id.id}
        return str(url % {"token": self.token}) if self.token else str(url)

    def __str__(self) -> str:
        return self.url


def parse_trade_url(url: StrOrURL, /) -> TradeURLInfo | None:
    """Parses a trade URL for useful information.

    Parameters
    -----------
    url
        The trade URL to search.

    Returns
    -------
    .. source:: TradeURLInfo
    """
    if (
        match := re.match(
            (
                rf"{_URL_START}steamcommunity\.com/tradeoffer/new/?\?partner=(?P<user_id>\d{{,10}})"
                r"(?:&token=(?P<token>[\w-]{7,}))?"
            ),
            html.unescape(str(url)),
        )
    ) is None:
        return None

    return TradeURLInfo(ID(match["user_id"], type=Type.Individual), match["token"] or None)


_SelfT = TypeVar("_SelfT", covariant=True)
_T_co = TypeVar("_T_co", covariant=True)


class cached_property(Generic[_SelfT, _T_co]):
    __slots__ = ("function", "__doc__")

    def __init__(self, function: Callable[[_SelfT], _T_co], /):
        self.function = function
        self.__doc__: str | None = getattr(function, "__doc__", None)

    @overload
    def __get__(self, instance: None, _) -> Self:
        ...

    @overload
    def __get__(self, instance: _SelfT, _) -> _T_co:  # type: ignore
        ...

    def __get__(self, instance: _SelfT | None, _) -> _T_co | Self:
        if instance is None:
            return self

        value = self.function(instance)
        setattr(instance, self.function.__name__, value)

        return value

    if TYPE_CHECKING:

        def __set__(self, instance: _SelfT, value: _T_co) -> None:  # type: ignore
            ...


@overload
def cached_slot_property(function: Callable[[_SelfT], _T_co], /) -> CachedSlotProperty[_SelfT, _T_co]:
    ...


@overload
def cached_slot_property(name: str, /) -> Callable[[Callable[[_SelfT], _T_co]], CachedSlotProperty[_SelfT, _T_co]]:
    ...


def cached_slot_property(function_or_name: Any, /) -> Any:  # required to be a function to appease type checkers
    if isinstance(function_or_name, str):

        def wrapper(function: Callable[[_SelfT], _T_co]) -> CachedSlotProperty[_SelfT, _T_co]:
            return CachedSlotProperty(function, function_or_name)

        return wrapper
    return CachedSlotProperty(function_or_name, f"_{function_or_name.__name__}_cs")


class CachedSlotProperty(Generic[_SelfT, _T_co]):
    __slots__ = ("function", "__doc__", "name")

    def __init__(self, function: Callable[[_SelfT], _T_co], name: str):
        self.function = function
        self.__doc__: str | None = getattr(function, "__doc__", None)
        self.name = name
        if __debug__:  # sanity check slots are present
            try:
                slots = sys._getframe(2).f_locals["__slots__"]
            except KeyError:
                slots = sys._getframe(3).f_locals["__slots__"]
            assert name in slots, f"Slot {name} must exist"

    @overload
    def __get__(self, instance: None, _) -> Self:
        ...

    @overload
    def __get__(self, instance: _SelfT, _) -> _T_co:  # type: ignore
        ...

    def __get__(self, instance: _SelfT | None, _) -> _T_co | Self:
        if instance is None:
            return self

        try:
            return getattr(instance, self.name)
        except AttributeError:
            value = self.function(instance)
            setattr(instance, self.name, value)
            return value

    def __set__(self, instance: _SelfT, value: _T_co) -> None:  # type: ignore
        setattr(instance, self.name, value)


F_no_wait = TypeVar("F_no_wait", bound="Callable[Concatenate[Any, ...], Awaitable[None]]")
F_wait = TypeVar("F_wait", bound="Callable[Concatenate[Any, ...], Awaitable[Any]]")


@overload
def call_once(func: F_no_wait, /) -> F_no_wait:
    ...


@overload
def call_once(*, wait: Literal[False] = False) -> Callable[[F_no_wait], F_no_wait]:
    ...


@overload
def call_once(*, wait: Literal[True]) -> Callable[[F_wait], F_wait]:
    ...


def call_once(func: F_wait | None = None, /, *, wait: bool = False) -> F_wait | Callable[[F_wait], F_wait]:
    def get_inner(func: F_wait) -> F_wait:
        locks = weakref.WeakKeyDictionary[object, asyncio.Lock]()
        being_called = weakref.WeakSet[object]()

        if wait:
            futures = dict[object, asyncio.Future[Any]]()

            async def inner(self: Any, *args: Any, **kwargs: Any) -> None:
                try:
                    lock = locks[self]
                except KeyError:
                    lock = locks[self] = asyncio.Lock()

                async with lock:
                    if self in being_called:
                        return await futures[self]

                    being_called.add(self)
                    futures[self] = future = asyncio.get_running_loop().create_future()

                try:
                    res = await func(self, *args, **kwargs)
                except Exception as exc:
                    future.set_exception(exc)
                    raise exc
                else:
                    future.set_result(res)
                    return res
                finally:
                    being_called.remove(self)
                    del futures[self]

        else:

            async def inner(self: Any, *args: Any, **kwargs: Any) -> None:
                try:
                    lock = locks[self]
                except KeyError:
                    lock = locks[self] = asyncio.Lock()

                async with lock:
                    if self in being_called:
                        return

                    being_called.add(self)

                try:
                    await func(self, *args, **kwargs)
                finally:
                    being_called.remove(self)

        return cast(F_wait, functools.wraps(func)(inner))

    return get_inner if func is None else get_inner(func)


async def ainput(prompt: object = "", /) -> str:
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    threading.Thread(target=lambda: loop.call_soon_threadsafe(future.set_result, input(prompt)), daemon=True).start()
    return await future


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


class DateTime:
    """UTC aware datetime factory functions."""

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def from_timestamp(timestamp: float, /) -> datetime:
        # work around python/cpython#75395
        return UNIX_EPOCH + timedelta(seconds=timestamp)

    @staticmethod
    def strptime(input: str, format: str) -> datetime:
        dt = datetime.strptime(input, format)
        if dt.tzinfo is not None:
            return dt
        return dt.replace(tzinfo=timezone.utc)

    @staticmethod  # TODO actually make this reliable for languages other than english
    def parse_steam_date(input: str, /, *, full_month: bool = True) -> datetime | None:
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


PACK_FORMATS: Final = cast(Mapping[str, str], {
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
            exec(f"def write_{method_name}(self, item, /): self.write_struct('<{format}', item)", {}, namespace)
            exec(
                textwrap.dedent(
                    f"""def read_{method_name}(self):
                        (value,) = self.read_struct('<{format}', {struct.calcsize(f'<{format}')})
                        return value
                    """
                ),
                {},
                namespace,
            )

        return super().__new__(mcs, name, bases, namespace)


class StructIO(
    BytesIO, metaclass=type if TYPE_CHECKING else StructIOMeta
):  # type[BytesIO] is a subclass of ABCMeta at type time
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

    def __len__(self) -> int:
        return len(self.getbuffer())

    def read_struct(self, format: str, /, position: int | None = None) -> tuple[Any, ...]:
        buffer = self.read(position or struct.calcsize(format))
        return struct.unpack(format, buffer)

    @overload
    def write_struct(self, format: str, to_write_1: Any, /, *to_write: Any) -> None:  # type: ignore
        ...

    def write_struct(self, format: str, /, *to_write: Any) -> None:
        self.write(struct.pack(format, *to_write))

    def read_cstring(self, terminator: bytes = b"\x00") -> bytes:
        data = self.getbuffer()[self.position :]
        for i, chars in enumerate(as_chunks(data, len(terminator))):
            if bytes(chars) == terminator:
                result = bytes(data[: i * len(terminator)])
                self.position += len(result) + len(terminator)
                return result

        raise RuntimeError("Reached end of buffer")

    def write_cstring(self, string: bytes, terminator: bytes = b"\x00") -> None:
        self.write(string)
        self.write(terminator)

    if TYPE_CHECKING:
        # added by the metaclass
        # fmt: off
        def read_i8(self) -> int: ...
        def write_i8(self, item: int, /) -> None: ...
        def read_u8(self) -> int: ...
        def write_u8(self, item: int, /) -> None: ...
        def read_i16(self) -> int: ...
        def write_i16(self, item: int, /) -> None: ...
        def read_u16(self) -> int: ...
        def write_u16(self, item: int, /) -> None: ...
        def read_i32(self) -> int: ...
        def write_i32(self, item: int, /) -> None: ...
        def read_u32(self) -> int: ...
        def write_u32(self, item: int, /) -> None: ...
        def read_i64(self) -> int: ...
        def write_i64(self, item: int, /) -> None: ...
        def read_u64(self) -> int: ...
        def write_u64(self, item: int, /) -> None: ...
        def read_f32(self) -> float: ...
        def write_f32(self, item: float, /) -> None: ...
        def read_f64(self) -> float: ...
        def write_f64(self, item: float, /) -> None: ...
        def read_long(self) -> int: ...
        def write_long(self, item: int, /) -> None: ...
        def read_ulong(self) -> int: ...
        def write_ulong(self, item: int, /) -> None: ...
        # fmt: on


_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


class ChainMap(collections.ChainMap[_KT, _VT]):
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

    @overload
    def pop(self, key: _KT) -> _VT:
        ...

    @overload
    def pop(self, key: _KT, default: _VT | _T) -> _VT | _T:
        ...

    def pop(self, key: _KT, default: _VT | _T = MISSING) -> _VT | _T:
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


class JWTToken(TypedDict):
    iss: Literal["steam"]
    sub: str  # SteamID
    aud: list[str]
    exp: int
    nbf: int
    iat: int
    jti: str
    oat: int
    per: int
    ip_subject: str
    ip_confirmer: str


def decode_jwt(token: str, /) -> JWTToken:
    try:
        _, jwt, _ = token.split(".")
    except TypeError:
        raise ValueError("Invalid JWT") from None

    # python doesn't like the lack of padding on the end of the JWT so we need to add it back
    return JSON_LOADS(base64.b64decode(f"{jwt}==", altchars=b"-_"))


@dataclass(slots=True)
class BBCodeTag:
    name: str
    position: tuple[int, int]
    attributes: dict[str, str]
    inner: str


class BBCodeStr(str):
    tags: list[BBCodeTag]

    def __new__(cls, string: str, tags: list[BBCodeTag]) -> Self:
        self = super().__new__(cls, string)
        self.tags = tags
        return self


BB_CODE_RE: Final = re.compile(
    r"""
    (?<!\\)
    \[(?P<name>[\w]+)\s*
    (?P<attributes>(?:\s*\w*=[^]]+)*)
    \]
    (?P<inner>.*?)
    (?<!\\)
    \[/(?P=name)\]
    """,
    re.VERBOSE,
)

BB_CODE_ATTRIBUTES_RE: Final = re.compile(
    r"""
    (?P<key>[\w]*)
    \s*=\s*
    (?P<quote>["']?)
    (?P<value>[^ ]*)
    (?P=quote)
    """,
    re.VERBOSE,
)


def parse_bb_code(string: str, /) -> BBCodeStr:
    tags = list[BBCodeTag]()
    for match in BB_CODE_RE.finditer(string):
        tag = BBCodeTag(
            match["name"],
            match.span(),
            {key: value for key, _, value in BB_CODE_ATTRIBUTES_RE.findall(match["attributes"])},
            match["inner"],
        )
        tags.append(tag)

        new_start, new_end = tag.position
        tags += [  # AFAICT steam chat only ever has a maximum of one level of nesting on "inner" so this is fine
            BBCodeTag(
                match["name"],
                match.span(),
                {key: value for key, _, value in BB_CODE_ATTRIBUTES_RE.findall(match["attributes"])},
                match["inner"],
            )
            for match in BB_CODE_RE.finditer(string, new_start + 1, new_end - 1)
        ]

    return BBCodeStr(string, tags=tags)


CHAT_COMMANDS = "|".join(
    rf"{command_name}\s*"
    for command_name in (
        "me",
        "code",
        "pre",
        "giphy",
        "spoiler",
        "quote",
        "random",
        "flip",
        "sticker",
        "store",
    )
)
CHAT_COMMANDS_RE: Final = re.compile(rf"""/(?:{CHAT_COMMANDS})""")


def contains_chat_command(string: str, /) -> bool:
    return bool(CHAT_COMMANDS_RE.match(string))


if TYPE_CHECKING:
    todo = deprecated("This method is not yet implemented")
else:

    def todo(func):
        def wrapper(*args: Any, **kwargs: Any) -> None:
            raise NotImplementedError(f"{func.__name__} is not yet implemented")

        return wrapper


# everything below here is directly from discord.py's utils
# https://github.com/Rapptz/discord.py/blob/master/discord/utils.py
_Iter: TypeAlias = Iterable[_T] | AsyncIterable[_T]


if sys.version_info >= (3, 12):
    _chunk = itertools.batched
else:

    def _chunk(
        iterable: Iterable[_T],
        max_size: int,
        iter: Callable[[Iterable[_T]], Iterator[_T]] = iter,
        tuple: type[tuple[_T, ...]] = tuple,
        islice: type[itertools.islice[_T]] = itertools.islice,
        /,
    ) -> Generator[tuple[_T, ...], None, None]:
        it = iter(iterable)
        while batch := tuple(islice(it, max_size)):
            yield batch


async def _achunk(
    iterable: AsyncIterable[_T], max_size: int, len: Callable[[Sized], int] = len, /
) -> AsyncGenerator[tuple[_T, ...], None]:
    ret: list[_T] = []
    async for item in iterable:
        ret.append(item)
        if len(ret) == max_size:
            yield tuple(ret)
            ret = []
    if ret:
        yield tuple(ret)


@overload
def as_chunks(iterable: AsyncIterable[_T], /, max_size: int) -> AsyncGenerator[tuple[_T, ...], None]:
    ...


@overload
def as_chunks(iterable: Iterable[_T], /, max_size: int) -> Generator[tuple[_T, ...], None, None]:
    ...


def as_chunks(iterable: _Iter[_T], /, max_size: int) -> _Iter[tuple[_T, ...]]:
    """A helper function that collects an iterable into chunks of a given size.

    Parameters
    ----------
    iterable
        The iterable to chunk, can be sync or async.
    max_size
        The maximum chunk size.

    Warning
    -------
    The last chunk collected may not be as large as ``max_size``.

    Returns
    --------
    A new iterator which yields chunks of a given size.
    """
    if max_size <= 0:
        raise ValueError("max_size must be greater than 0")

    return _achunk(iterable, max_size) if hasattr(iterable, "__aiter__") else _chunk(iterable, max_size)  # type: ignore


@overload
def find(predicate: Callable[[_T], bool], iterable: AsyncIterable[_T], /) -> Coro[_T | None]:
    ...


@overload
def find(predicate: Callable[[_T], bool], iterable: Iterable[_T], /) -> _T | None:
    ...


def find(predicate: Callable[[_T], bool], iterable: _Iter[_T], /) -> _T | Coro[_T | None] | None:
    """A helper to return the first element found in the sequence.

    Examples
    --------
    .. code:: python

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

    if hasattr(iterable, "__aiter__"):  # isinstance(iterable, collections.abc.AsyncIterable) is too slow
        return anext((element async for element in iterable if predicate(element)), None)  # type: ignore
    else:
        return next((element for element in iterable if predicate(element)), None)  # type: ignore


def _get(
    iterable: Iterable[_T],
    all: Callable[[Iterable[bool]], bool] = all,
    attrgetter: type[attrgetter[_T]] = attrgetter,
    /,
    **attrs: Any,
) -> _T | None:
    # Special case the single element call
    if len(attrs) == 1:
        k, v = attrs.popitem()
        pred = attrgetter(k.replace("__", "."))
        return next((elem for elem in iterable if pred(elem) == v), None)

    converted = [(attrgetter(attr.replace("__", ".")), value) for attr, value in attrs.items()]

    return next((elem for elem in iterable if all(pred(elem) == value for pred, value in converted)), None)


def _aget(
    iterable: AsyncIterable[_T],
    all: Callable[[Iterable[bool]], bool] = all,
    attrgetter: type[attrgetter[_T]] = attrgetter,
    /,
    **attrs: Any,
) -> Coro[_T | None]:
    # Special case the single element call
    if len(attrs) == 1:
        k, v = attrs.popitem()
        pred = attrgetter(k.replace("__", "."))
        return anext((elem async for elem in iterable if pred(elem) == v), None)

    converted = [(attrgetter(attr.replace("__", ".")), value) for attr, value in attrs.items()]

    return anext((elem async for elem in iterable if all(pred(elem) == value for pred, value in converted)), None)


@overload
def get(iterable: AsyncIterable[_T], /, **attrs: Any) -> Coro[_T | None]:
    ...


@overload
def get(iterable: Iterable[_T], /, **attrs: Any) -> _T | None:
    ...


def get(iterable: _Iter[_T], /, **attrs: Any) -> _T | None | Coro[_T | None]:
    """A helper that returns the first element in the iterable that meets all the traits passed in ``attrs``. This
    is an alternative for :func:`find`.

    Examples
    --------
    .. code:: python

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
    return (
        _aget(iterable, **attrs)  # type: ignore
        if hasattr(iterable, "__aiter__")  # isinstance(iterable, collections.abc.AsyncIterable) is too slow
        else _get(iterable, **attrs)  # type: ignore
    )


async def maybe_coroutine(
    func: Callable[_P, _T | Awaitable[_T]],
    /,
    *args: _P.args,
    **kwargs: _P.kwargs,
) -> _T:
    value = func(*args, **kwargs)
    return await value if isawaitable(value) else value
