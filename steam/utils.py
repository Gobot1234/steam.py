# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
Copyright (c) 2015-202 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import asyncio
import datetime
import json
import re
import socket
import struct
from base64 import b64decode
from operator import attrgetter
from os import urandom as random_bytes
from types import GeneratorType as _GeneratorType
from typing import Iterable, Callable, Any, Optional, Awaitable, Tuple

import aiohttp
from Cryptodome.Cipher import AES as AES, PKCS1_OAEP
from Cryptodome.Hash import SHA1, HMAC
from Cryptodome.PublicKey.RSA import import_key as rsa_import_key

from .enums import (
    EType,
    EUniverse,
    ETypeChar,
    EInstanceFlag,
)

__all__ = (
    'get',
    'find',
    'make_steam64',
    'sleep_until',
    'parse_trade_url_token',
)

BS = 16
PROTOBUF_MASK = 0x80000000
MAX_ASYNCIO_SECONDS = 3456000
_INVITE_HEX = "0123456789abcdef"
_INVITE_CUSTOM = "bcdfghjkmnpqrtvw"
_INVITE_VALID = f'{_INVITE_HEX}{_INVITE_CUSTOM}'
_INVITE_MAPPING = dict(zip(_INVITE_HEX, _INVITE_CUSTOM))
_INVITE_INVERSE_MAPPING = dict(zip(_INVITE_CUSTOM, _INVITE_HEX))

ETypeChars = ''.join(type_char.name for type_char in ETypeChar)


class UniverseKey:
    Public = rsa_import_key(b64decode("""
MIGdMA0GCSqGSIb3DQEBAQUAA4GLADCBhwKBgQDf7BrWLBBmLBc1OhSwfFkRf53T
2Ct64+AVzRkeRuh7h3SiGEYxqQMUeYKO6UWiSRKpI2hzic9pobFhRr3Bvr/WARvY
gdTckPv+T1JzZsuVcNfFjrocejN1oWI0Rrtgt4Bo+hOneoo3S57G9F1fOpn5nsQ6
6WOiu4gZKODnFMBCiQIBEQ==
"""))


def pad(s):
    return s + (BS - len(s) % BS) * struct.pack('B', BS - len(s) % BS)


def unpad(s):
    return s[0:-s[-1]]


def generate_session_key(hmac_secret=b''):
    session_key = random_bytes(32)
    encrypted_session_key = PKCS1_OAEP.new(UniverseKey.Public, SHA1).encrypt(session_key + hmac_secret)

    return session_key, encrypted_session_key


def symmetric_encrypt(message, key):
    iv = random_bytes(BS)
    return symmetric_encrypt_with_iv(message, key, iv)


def symmetric_encrypt_HMAC(message, key, hmac_secret):
    prefix = random_bytes(3)
    hmac = hmac_sha1(hmac_secret, prefix + message)
    iv = hmac[:13] + prefix
    return symmetric_encrypt_with_iv(message, key, iv)


def symmetric_encrypt_iv(iv, key):
    return AES.new(key, AES.MODE_ECB).encrypt(iv)


def symmetric_encrypt_with_iv(message, key, iv):
    encrypted_iv = symmetric_encrypt_iv(iv, key)
    cyphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(message))
    return encrypted_iv + cyphertext


def symmetric_decrypt(cyphertext, key):
    iv = symmetric_decrypt_iv(cyphertext, key)
    return symmetric_decrypt_with_iv(cyphertext, key, iv)


def symmetric_decrypt_HMAC(cyphertext, key, hmac_secret):
    iv = symmetric_decrypt_iv(cyphertext, key)
    message = symmetric_decrypt_with_iv(cyphertext, key, iv)

    hmac = hmac_sha1(hmac_secret, iv[-3:] + message)

    if iv[:13] != hmac[:13]:
        raise RuntimeError("Unable to decrypt message. HMAC does not match.")

    return message


def symmetric_decrypt_iv(cyphertext, key):
    return AES.new(key, AES.MODE_ECB).decrypt(cyphertext[:BS])


def symmetric_decrypt_with_iv(cyphertext, key, iv):
    return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(cyphertext[BS:]))


def hmac_sha1(secret, data):
    return HMAC.new(secret, data, SHA1).digest()


def ip_from_int(ip: int) -> Tuple[str, str]:
    return socket.inet_ntoa(struct.pack(">L", ip))


def ip_to_int(ip: Tuple[str, str]) -> int:
    return struct.unpack(">L", socket.inet_aton(ip))[0]


def is_proto(emsg: bytes) -> bool:
    return (int(emsg) & PROTOBUF_MASK) > 0


def set_proto_bit(emsg: bytes) -> int:
    return int(emsg) | PROTOBUF_MASK


def clear_proto_bit(emsg: bytes) -> int:
    return int(emsg) & ~PROTOBUF_MASK


_list_types = (list, range, _GeneratorType)


# from the VDF module
class UINT_64(int):
    pass


class INT_64(int):
    pass


class POINTER(int):
    pass


class COLOR(int):
    pass


BIN_NONE = b'\x00'
BIN_STRING = b'\x01'
BIN_INT32 = b'\x02'
BIN_FLOAT32 = b'\x03'
BIN_POINTER = b'\x04'
BIN_WIDESTRING = b'\x05'
BIN_COLOR = b'\x06'
BIN_UINT64 = b'\x07'
BIN_END = b'\x08'
BIN_INT64 = b'\x0A'
BIN_END_ALT = b'\x0B'


def binary_loads(s, mapper=dict, merge_duplicate_keys=True, alt_format=False) -> dict:
    if not isinstance(s, bytes):
        raise TypeError("Expected s to be bytes, got %s" % type(s))
    if not issubclass(mapper, dict):
        raise TypeError("Expected mapper to be subclass of dict, got %s" % type(mapper))

    # helpers
    int32 = struct.Struct('<i')
    uint64 = struct.Struct('<Q')
    int64 = struct.Struct('<q')
    float32 = struct.Struct('<f')

    def read_string(s, idx, wide=False):
        if wide:
            end = s.find(b'\x00\x00', idx)
            if (end - idx) % 2 != 0:
                end += 1
        else:
            end = s.find(b'\x00', idx)

        if end == -1:
            raise SyntaxError("Unterminated cstring (offset: %d)" % idx)
        result = s[idx:end]
        if wide:
            result = result.decode('utf-16')
        elif bytes is not str:
            result = result.decode('utf-8', 'replace')
        else:
            try:
                result.decode('ascii')
            except UnicodeDecodeError:
                result = result.decode('utf-8', 'replace')
        return result, end + (2 if wide else 1)

    stack = [mapper()]
    idx = 0
    CURRENT_BIN_END = BIN_END if not alt_format else BIN_END_ALT

    while len(s) > idx:
        t = s[idx:idx + 1]
        idx += 1

        if t == CURRENT_BIN_END:
            if len(stack) > 1:
                stack.pop()
                continue
            break

        key, idx = read_string(s, idx)

        if t == BIN_NONE:
            if merge_duplicate_keys and key in stack[-1]:
                _m = stack[-1][key]
            else:
                _m = mapper()
                stack[-1][key] = _m
            stack.append(_m)
        elif t == BIN_STRING:
            stack[-1][key], idx = read_string(s, idx)
        elif t == BIN_WIDESTRING:
            stack[-1][key], idx = read_string(s, idx, wide=True)
        elif t in (BIN_INT32, BIN_POINTER, BIN_COLOR):
            val = int32.unpack_from(s, idx)[0]

            if t == BIN_POINTER:
                val = POINTER(val)
            elif t == BIN_COLOR:
                val = COLOR(val)

            stack[-1][key] = val
            idx += int32.size
        elif t == BIN_UINT64:
            stack[-1][key] = UINT_64(uint64.unpack_from(s, idx)[0])
            idx += uint64.size
        elif t == BIN_INT64:
            stack[-1][key] = INT_64(int64.unpack_from(s, idx)[0])
            idx += int64.size
        elif t == BIN_FLOAT32:
            stack[-1][key] = float32.unpack_from(s, idx)[0]
            idx += float32.size
        else:
            raise SyntaxError("Unknown data type at offset %d: %s" % (idx - 1, repr(t)))

    if len(s) != idx or len(stack) != 1:
        raise SyntaxError("Binary VDF ended at offset %d, but length is %d" % (idx, len(s)))

    return stack.pop()


def make_steam64(id: int = 0, *args, **kwargs) -> int:
    """Returns a Steam 64-bit ID from various other representations.

    .. code:: python

        make_steam64()  # invalid steam_id
        make_steam64(12345)  # account_id
        make_steam64('12345')
        make_steam64(id=12345, type='Invalid', universe='Invalid', instance=0)
        make_steam64(103582791429521412)  # steam64
        make_steam64('103582791429521412')
        make_steam64('STEAM_1:0:2')  # steam2
        make_steam64('[g:1:4]')  # steam3
        make_steam64('cv-dgb')  # invite code

    Raises
    ------
    :exc:`TypeError`
        Too many arguments have been given.

    Returns
    -------
    :class:`int`
        The 64-bit Steam ID.
    """

    etype = EType.Invalid
    universe = EUniverse.Invalid
    instance = None

    if len(args) == 0 and len(kwargs) == 0:
        value = str(id)

        # numeric input
        if value.isdigit():
            value = int(value)

            # 32 bit account id
            if 0 < value < 2 ** 32:
                id = value
                etype = EType.Individual
                universe = EUniverse.Public
            # 64 bit
            elif value < 2 ** 64:
                return value
            else:
                id = 0

        # textual input e.g. [g:1:4]
        else:
            result = steam2_to_tuple(value) or steam3_to_tuple(value) or invite_code_to_tuple(value)

            if result:
                id, etype, universe, instance = result
            else:
                id = 0

    elif len(args) > 0:
        length = len(args)
        if length == 1:
            etype, = args
        elif length == 2:
            etype, universe = args
        elif length == 3:
            etype, universe, instance = args
        else:
            raise TypeError(f"Takes at most 4 arguments ({length} given)")

    if len(kwargs) > 0:
        etype = kwargs.get('type', etype)
        universe = kwargs.get('universe', universe)
        instance = kwargs.get('instance', instance)

    etype = (EType(int(etype)) if isinstance(etype, (int, EType)) else EType[etype])
    universe = (EUniverse(int(universe)) if isinstance(universe, (int, EUniverse)) else EUniverse[universe])

    if instance is None:
        instance = 1 if etype in (EType.Individual, EType.GameServer) else 0

    return (universe.value << 56) | (etype.value << 52) | (instance << 32) | id


def steam2_to_tuple(value: str) -> Optional[Tuple[int, EType, EUniverse, int]]:
    """
    Parameters
    ----------
    value: :class:`str`
        steam2 e.g. ``STEAM_1:0:1234``.

    Returns
    -------
    Optional[:class:`tuple`]
        e.g. (account_id, type, universe, instance) or ``None``.

    .. note::
        The universe will be always set to ``1``. See :attr:`SteamID.as_steam2`.
    """
    match = re.match(
        r"^STEAM_(?P<universe>\d+)"
        r":(?P<reminder>[0-1])"
        r":(?P<id>\d+)$", value
    )

    if not match:
        return None

    steam_32 = (int(match.group('id')) << 1) | int(match.group('reminder'))
    universe = int(match.group('universe'))

    # Games before orange box used to incorrectly display universe as 0, we support that
    if universe == 0:
        universe = 1

    return steam_32, EType(1), EUniverse(universe), 1


def steam3_to_tuple(value: str) -> Optional[Tuple[int, EType, EUniverse, int]]:
    """
    Parameters
    ----------
    value: :class:`str`
        steam3 e.g. ``[U:1:1234]``.

    Returns
    -------
    Optional[:class:`tuple`]
        e.g. (account_id, type, universe, instance) or ``None``.
    """
    match = re.match(
        rf"^\[(?P<type>[i{ETypeChars}]):"  # type char
        r"(?P<universe>[0-4]):"  # universe
        r"(?P<id>\d{1,10})"  # accountid
        r"(:(?P<instance>\d+))?\]$",  # instance
        value
    )
    if not match:
        return None

    steam_32 = int(match.group('id'))
    universe = EUniverse(int(match.group('universe')))
    typechar = match.group('type').replace('i', 'I')
    etype = EType(ETypeChar[typechar])
    instance = match.group('instance')

    if typechar in 'gT':
        instance = 0
    elif instance is not None:
        instance = int(instance)
    elif typechar == 'L':
        instance = EInstanceFlag.Lobby
    elif typechar == 'c':
        instance = EInstanceFlag.Clan
    elif etype in (EType.Individual, EType.GameServer):
        instance = 1
    else:
        instance = 0

    instance = int(instance)

    return steam_32, etype, universe, instance


def invite_code_to_tuple(code: str) -> Optional[Tuple[int, EType, EUniverse, int]]:
    """
    Parameters
    ----------
    code: :class:`str`
        The invite code e.g. ``cv-dgb``

    Returns
    -------
    Optional[:class:`tuple`]
        e.g. (account_id, type, universe, instance) or ``None``.
    """
    match = re.match(rf'(https?://s\.team/p/(?P<code1>[\-{_INVITE_VALID}]+))'
                     rf'|(?P<code2>[\-{_INVITE_VALID}]+$)', code)
    if not match:
        return None

    code = (match.group('code1') or match.group('code2')).replace('-', '')

    def repl_mapper(x):
        return _INVITE_INVERSE_MAPPING[x.group()]

    steam_32 = int(re.sub(f"[{_INVITE_CUSTOM}]", repl_mapper, code), 16)

    if 0 < steam_32 < 2 ** 32:
        return steam_32, EType(1), EUniverse.Public, 1


async def steam64_from_url(url: str, timeout=30) -> Optional[int]:
    """Takes a Steam Community url and returns steam64 or None

    .. note::
        Each call makes a http request to steamcommunity.com

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
    timeout: :class:`int`
        How long to wait on http request before turning ``None``.

    Returns
    -------
    steam64: Optional[:class:`int`]
        If ``steamcommunity.com`` is down or no matching account is found returns ``None``
    """

    match = re.match(r'^(?P<clean_url>https?://steamcommunity.com/'
                     r'(?P<type>profiles|id|gid|groups)/(?P<value>.*?))(?:/(?:.*)?)?$', str(url))

    if match is None:
        return None

    session = aiohttp.ClientSession()

    try:
        # user profiles
        if match.group('type') in ('id', 'profiles'):
            async with session.get(match.group('clean_url'), timeout=timeout) as r:
                text = await r.text()
                await session.close()
            data_match = re.search("g_rgProfileData = (?P<json>{.*?});\s*", text)

            if data_match:
                data = json.loads(data_match.group('json'))
                return int(data['steamid'])
        # group profiles
        else:
            async with session.get(match.group('clean_url'), timeout=timeout) as r:
                text = await r.text()
                await session.close()
            data_match = re.search(r"OpenGroupChat\( *'(?P<steamid>\d+)'", text)

            if data_match:
                return int(data_match.group('steamid'))
    except aiohttp.InvalidURL:
        return None


def parse_trade_url_token(url: str) -> Optional[str]:
    """Parses a trade URL for an user's token.

    Parameters
    -----------
    url: :class:`str`
        The URL to search for a token.

    Returns
    -------
    Optional[:class:`str`]
        The found token. ``None`` if the URL doesn't match the regex.
    """
    search = re.search(r"(?:http[s]?://|)(?:www.|)steamcommunity.com/tradeoffer/new/\?partner=\d{7,}"
                       r"(?:&|&amp;)token=(?P<token>[\w-]{7,})", url)
    if search:
        return search.group('token')
    return None


def ainput(prompt: str = '', loop: asyncio.AbstractEventLoop = None) -> Awaitable:
    loop = loop or asyncio.get_event_loop()
    return loop.run_in_executor(None, input, prompt)


# everything below here is directly from discord.py's utils
# https://github.com/rapptz/discord.py/blob/master/discord/utils.py


def find(predicate: Callable[..., bool], seq: Iterable) -> Optional[Any]:
    """A helper to return the first element found in the sequence.

    Parameters
    -----------
    predicate: Callable[..., bool]
        A function that returns a boolean-like result.
    seq: Iterable
        The iterable to search through.
    """

    for element in seq:
        if predicate(element):
            return element
    return None


def get(iterable: Iterable, **attrs) -> Optional[Any]:
    r"""A helper that returns the first element in the iterable that meets
    all the traits passed in ``attrs``. This is an alternative for
    :func:`utils.find`.

    Parameters
    -----------
    iterable: Iterable
        An iterable to search through.
    \*\*attrs
        Keyword arguments that denote attributes to search with.
    """

    # global -> local
    _all = all
    attrget = attrgetter

    # Special case the single element call
    if len(attrs) == 1:
        k, v = attrs.popitem()
        pred = attrget(k.replace('__', '.'))
        for elem in iterable:
            if pred(elem) == v:
                return elem
        return None

    converted = [
        (attrget(attr.replace('__', '.')), value)
        for attr, value in attrs.items()
    ]

    for elem in iterable:
        if _all(pred(elem) == value for pred, value in converted):
            return elem
    return None


async def sleep_until(when: datetime.datetime, result: Any = None) -> Awaitable:
    """|coro|
    Sleep until a specified time.
    If the time supplied is in the past this function will yield instantly.

    Parameters
    -----------
    when: :class:`datetime.datetime`
        The timestamp in which to sleep until.
    result: Any
        If provided is returned to the caller when the coroutine completes.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = (when - now).total_seconds()
    while delta > MAX_ASYNCIO_SECONDS:
        await asyncio.sleep(MAX_ASYNCIO_SECONDS)
        delta -= MAX_ASYNCIO_SECONDS
    return await asyncio.sleep(max(delta, 0), result)
