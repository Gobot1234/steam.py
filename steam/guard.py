# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2016 Michał Bukowski gigibukson@gmail.com
Copyright (c) 2017 Nate the great
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

This contains a copy of
https://github.com/bukson/steampy/blob/master/steampy/guard.py
and https://github.com/Zwork101/steam-trade/blob/master/pytrade/confirmations.py
with extra doc-strings and performance improvements.
"""

import base64
import hmac
import struct
from hashlib import sha1
from time import time
from typing import TYPE_CHECKING, Optional

from .errors import ConfirmationError
from .models import community_route

if TYPE_CHECKING:
    from .state import ConnectionState


__all__ = (
    "generate_one_time_code",
    "generate_confirmation_code",
    "generate_device_id",
    "Confirmation",
)


def generate_one_time_code(shared_secret: str, timestamp: Optional[int] = None) -> str:
    """Generate a Steam Guard code for signing in.

    Parameters
    -----------
    shared_secret: :class:`str`
        Identity secret from steam guard.
    timestamp: Optional[:class:`int`]
        The unix timestamp to generate the key for.

    Returns
    --------
    :class:`str`
        The desired 2FA code for the timestamp.
    """
    timestamp = timestamp or int(time())
    time_buffer = struct.pack(">Q", timestamp // 30)  # pack as Big endian, uint64
    time_hmac = hmac.new(base64.b64decode(shared_secret), time_buffer, digestmod=sha1).digest()
    begin = ord(time_hmac[19:20]) & 0xF
    full_code = struct.unpack(">I", time_hmac[begin : begin + 4])[0] & 0x7FFFFFFF  # unpack as Big endian uint32
    chars = "23456789BCDFGHJKMNPQRTVWXY"
    code = []
    for _ in range(5):
        full_code, i = divmod(full_code, len(chars))
        code.append(chars[i])
    return "".join(code)


def generate_confirmation_code(identity_secret: str, tag: str, timestamp: Optional[int] = None) -> str:
    """Generate a trade confirmation code.

    Parameters
    -----------
    identity_secret: :class:`str`
        Identity secret from steam guard.
    tag: :class:`str`
        Tag to encode to.
    timestamp: Optional[:class:`int`]
        The time to generate the key for.

    Returns
    --------
    :class:`str`
        Confirmation code for the set timestamp.
    """
    timestamp = timestamp or int(time())
    buffer = struct.pack(">Q", timestamp) + tag.encode("ascii")
    return base64.b64encode(hmac.new(base64.b64decode(identity_secret), buffer, digestmod=sha1).digest()).decode()


def generate_device_id(user_id64: str) -> str:
    """
    Parameters
    -----------
    user_id64: :class:`str`
        The 64 bit steam id to generate the device id for.

    Returns
    --------
    :class:`str`
        The device id.
    """
    # it works, however it's different that one generated from mobile app

    hexed_steam_id = sha1(user_id64.encode("ascii")).hexdigest()
    partial_id = [
        hexed_steam_id[:8],
        hexed_steam_id[8:12],
        hexed_steam_id[12:16],
        hexed_steam_id[16:20],
        hexed_steam_id[20:32],
    ]
    return f'android:{"-".join(partial_id)}'


class Confirmation:
    def __init__(self, state: "ConnectionState", id: str, data_confid: int, data_key: str, trade_id: int, tag: str):
        self._state = state
        self.id = id.split("conf")[1]
        self.data_confid = data_confid
        self.data_key = data_key
        self.tag = tag
        self.trade_id = trade_id  # this isn't really always the trade ID, but for our purposes this is fine

    def __repr__(self):
        return f"<Confirmation id={self.id!r} trade_id={self.trade_id}>"

    def __eq__(self, other: "Confirmation"):
        return isinstance(other, Confirmation) and self.trade_id == other.trade_id and self.id == other.id

    def _confirm_params(self, tag) -> dict:
        timestamp = int(time())
        return {
            "p": self._state._device_id,
            "a": self._state._id64,
            "k": self._state._generate_confirmation(tag, timestamp),
            "t": timestamp,
            "m": "android",
            "tag": tag,
        }

    def _assert_valid(self, resp: dict):
        if not resp.get("success", False):
            self._state._confirmations_to_ignore.append(self.id)
            raise ConfirmationError

    async def confirm(self) -> None:
        params = self._confirm_params("allow")
        params["op"] = "allow"
        params["cid"] = self.data_confid
        params["ck"] = self.data_key
        resp = await self._state.request("GET", community_route("mobileconf/ajaxop"), params=params)
        self._assert_valid(resp)

    async def cancel(self) -> None:
        params = self._confirm_params("cancel")
        params["op"] = "cancel"
        params["cid"] = self.data_confid
        params["ck"] = self.data_key
        resp = await self._state.request("GET", community_route("mobileconf/ajaxop"), params=params)
        self._assert_valid(resp)

    async def details(self) -> dict:
        params = self._confirm_params(self.tag)
        resp = await self._state.request("GET", community_route(f"mobileconf/details/{self.id}"), params=params)
        self._assert_valid(resp)
        return resp["html"]
