# -*- coding: utf-8 -*-

"""
MIT License

Copyright (c) 2016 Michał Bukowski gigibukson@gmail.com

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

This copy of
https://github.com/bukson/steampy/blob/master/steampy/guard.py
with extra doc-strings and it's slightly sped up
"""

from base64 import b64decode, b64encode
from hashlib import sha1
from hmac import new
from json import loads
from os.path import isfile
from struct import pack, unpack
from time import time

from steam.errors import SteamAuthenticatorError


def load_steam_guard(steam_guard: str) -> dict:
    """Load a Steam Guard :class:`dict` or :mod:`json` file.

    Parameters
    ----------
    steam_guard: :class:`str`
        The location of the Steam Guard info.

    Raises
    ------
    :exc:`SteamAuthenticatorError`
        The file wasn't loadable.

    Returns
    -------
    :class:`dict`
        Dictionary of the Steam Guard info.
    """
    if isfile(steam_guard):
        with open(steam_guard, 'r') as f:
            try:
                return loads(f.read())
            except Exception as e:
                raise SteamAuthenticatorError(f'{steam_guard} is not able to be loaded\n{" ".join(e.args)}')
            finally:
                f.close()
    else:
        try:
            return loads(steam_guard)
        except Exception as e:
            raise SteamAuthenticatorError(f'{steam_guard} is not able to be loaded\n{" ".join(e.args)}')


def generate_one_time_code(shared_secret: str, timestamp: int = int(time())) -> str:
    """Generate a Steam Guard code for signing in.

    Parameters
    ----------
    shared_secret: :class:`str`
        Identity secret from steam guard.
    timestamp: Optional[:class:`int`]
        The time to generate the key for the set time.

    Returns
    -------
    code: :class:`str`
        The desired 2FA code for the timestamp.
    """
    time_buffer = pack('>Q', timestamp // 30)  # pack as Big endian, uint64
    time_hmac = new(b64decode(shared_secret), time_buffer, digestmod=sha1).digest()
    begin = ord(time_hmac[19:20]) & 0xf
    full_code = unpack('>I', time_hmac[begin:begin + 4])[0] & 0x7fffffff  # unpack as Big endian uint32
    chars = '23456789BCDFGHJKMNPQRTVWXY'
    code = []
    for _ in range(5):
        full_code, i = divmod(full_code, len(chars))
        code.append(chars[i])
    return ''.join(code)  # faster than string concatenation


def generate_confirmation_key(identity_secret: str, tag: str, timestamp: int = int(time())) -> bytes:
    """Generate a trade confirmation key.

    Parameters
    ----------
    identity_secret: :class:`str`
        Identity secret from steam guard.
    tag: :class:`str`
        Tag to encode to
    timestamp: Optional[:class:`int`]
        The time to generate the key for.

    Returns
    -------
    key: :class:`bytes`
        Confirmation key for the set timestamp.
    """
    buffer = f'{pack(">Q", timestamp)}{tag.encode("ascii")}'
    return b64encode(new(b64decode(identity_secret), buffer, digestmod=sha1).digest())


def generate_device_id(steam_id: str) -> str:
    """
    Parameters
    ----------
    steam_id: :class:`str`
        The steam id to generate the id for

    Returns
    -------
    id: :class:`str`
        The device id
    """
    # It works, however it's different that one generated from mobile app

    hexed_steam_id = sha1(steam_id.encode('ascii')).hexdigest()
    partial_id = [
        hexed_steam_id[:8],
        hexed_steam_id[8:12],
        hexed_steam_id[12:16],
        hexed_steam_id[16:20],
        hexed_steam_id[20:32]
    ]
    return f'android:{"-".join(partial_id)}'
