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
import re
import socket
import struct
from base64 import b64decode
from operator import attrgetter
from os import urandom as random_bytes
from types import GeneratorType as _GeneratorType
from typing import Iterable, Callable

from Cryptodome.Cipher import AES as AES, PKCS1_OAEP
from Cryptodome.Hash import SHA1, HMAC
from Cryptodome.PublicKey.RSA import import_key as rsa_import_key
from google.protobuf.message import Message as _ProtoMessageType

__all__ = (
    'get',
    'find',
    'sleep_until',
    'parse_trade_url_token',
)

MAX_ASYNCIO_SECONDS = 3456000


class UniverseKey:
    Public = rsa_import_key(b64decode("""
MIGdMA0GCSqGSIb3DQEBAQUAA4GLADCBhwKBgQDf7BrWLBBmLBc1OhSwfFkRf53T
2Ct64+AVzRkeRuh7h3SiGEYxqQMUeYKO6UWiSRKpI2hzic9pobFhRr3Bvr/WARvY
gdTckPv+T1JzZsuVcNfFjrocejN1oWI0Rrtgt4Bo+hOneoo3S57G9F1fOpn5nsQ6
6WOiu4gZKODnFMBCiQIBEQ==
"""))


BS = 16


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


def ip_from_int(ip):
    return socket.inet_ntoa(struct.pack(">L", ip))


def ip_to_int(ip):
    return struct.unpack(">L", socket.inet_aton(ip))[0]


protobuf_mask = 0x80000000


def is_proto(emsg):
    return (int(emsg) & protobuf_mask) > 0


def set_proto_bit(emsg):
    return int(emsg) | protobuf_mask


def clear_proto_bit(emsg):
    return int(emsg) & ~protobuf_mask


def proto_to_dict(message):
    if not isinstance(message, _ProtoMessageType):
        raise TypeError("Expected `message` to be a instance of protobuf message")

    data = {}

    for desc, field in message.ListFields():
        if desc.type == desc.TYPE_MESSAGE:
            if desc.label == desc.LABEL_REPEATED:
                data[desc.name] = list(map(proto_to_dict, field))
            else:
                data[desc.name] = proto_to_dict(field)
        else:
            data[desc.name] = list(field) if desc.label == desc.LABEL_REPEATED else field

    return data


_list_types = (list, range, _GeneratorType)


def proto_fill_from_dict(message, data, clear=True):
    if clear:
        message.Clear()
    field_descs = message.DESCRIPTOR.fields_by_name

    for key, val in data.items():
        desc = field_descs[key]

        if desc.type == desc.TYPE_MESSAGE:
            if desc.label == desc.LABEL_REPEATED:
                if not isinstance(val, _list_types):
                    raise TypeError("Expected %s to be of type list, got %s" % (repr(key), type(val)))

                list_ref = getattr(message, key)

                # Takes care of overwriting list fields when merging partial data (clear=False)
                if not clear:
                    del list_ref[:]  # clears the list

                for item in val:
                    item_message = getattr(message, key).add()
                    proto_fill_from_dict(item_message, item)
            else:
                if not isinstance(val, dict):
                    raise TypeError("Expected %s to be of type dict, got %s" % (repr(key), type(dict)))

                proto_fill_from_dict(getattr(message, key), val)
        else:
            if isinstance(val, _list_types):
                list_ref = getattr(message, key)
                if not clear:
                    del list_ref[:]  # clears the list
                list_ref.extend(val)
            else:
                setattr(message, key, val)

    return message


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


def binary_loads(s, mapper=dict, merge_duplicate_keys=True, alt_format=False):
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


def parse_trade_url_token(url: str):
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
    search = re.search(r"(?:https://|)(?:www.|)steamcommunity.com/tradeoffer/new/\?partner=\d{7,}"
                       r"(?:&|&amp;)token=(?P<token>[\w-]{7,})", url)
    if search:
        return search.group('token')
    return None


# everything below here is directly from discord.py's utils
# https://github.com/rapptz/discord.py/blob/master/discord/utils.py


def find(predicate: Callable[..., bool], seq: Iterable):
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


def get(iterable: Iterable, **attrs):
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


async def sleep_until(when, result=None):
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