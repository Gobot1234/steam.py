"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import base64
import dataclasses
import hmac
import struct
from hashlib import sha1
from time import time
from typing import TYPE_CHECKING, Any

from ._const import URL
from .errors import ConfirmationError
from .utils import Intable

if TYPE_CHECKING:
    from .state import ConnectionState


__all__ = (
    "generate_one_time_code",
    "generate_confirmation_code",
    "generate_device_id",
    "Confirmation",
)


def generate_one_time_code(shared_secret: str, timestamp: int | None = None) -> str:
    """Generate a Steam Guard code for signing in or at a specific time.

    Parameters
    -----------
    shared_secret
        Shared secret from steam guard.
    timestamp
        The unix timestamp to generate the key for.
    """
    timestamp = timestamp or int(time())
    time_buffer = struct.pack(">Q", timestamp // 30)  # pack as Big endian, uint64
    time_hmac = hmac.new(base64.b64decode(shared_secret), time_buffer, digestmod=sha1).digest()
    begin = time_hmac[19] & 0xF

    full_code = struct.unpack(">I", time_hmac[begin : begin + 4])[0] & 0x7FFFFFFF  # unpack as Big endian uint32

    chars = "23456789BCDFGHJKMNPQRTVWXY"
    code = []
    for _ in range(5):
        full_code, i = divmod(full_code, len(chars))
        code.append(chars[i])
    return "".join(code)


def generate_confirmation_code(identity_secret: str, tag: str, timestamp: int | None = None) -> str:
    """Generate a trade confirmation code.

    Parameters
    -----------
    identity_secret
        Identity secret from steam guard.
    tag
        Tag to encode to.
    timestamp
        The time to generate the key for.
    """
    timestamp = timestamp or int(time())
    buffer = struct.pack(">Q", timestamp) + tag.encode("ascii")
    return base64.b64encode(hmac.new(base64.b64decode(identity_secret), buffer, digestmod=sha1).digest()).decode()


def generate_device_id(user_id64: Intable) -> str:
    """Generate the device id for a user's 64-bit ID.

    Parameters
    -----------
    user_id64
        The 64 bit steam id to generate the device id for.
    """
    # it works, however it's different that one generated from mobile app

    hexed_steam_id = sha1(str(int(user_id64)).encode("ascii")).hexdigest()
    partial_id = [
        hexed_steam_id[:8],
        hexed_steam_id[8:12],
        hexed_steam_id[12:16],
        hexed_steam_id[16:20],
        hexed_steam_id[20:32],
    ]
    return f'android:{"-".join(partial_id)}'


@dataclasses.dataclass
class Confirmation:
    __slots__ = (
        "_state",
        "id",
        "nonce",
        "creator_id",
    )
    _state: ConnectionState
    id: int
    nonce: int
    creator_id: int  # this isn't really always the trade ID, but for our purposes this is fine

    def __repr__(self) -> str:
        return f"<Confirmation id={self.id} creator_id={self.creator_id}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Confirmation) and self.creator_id == other.creator_id and self.id == other.id

    async def _confirm_params(self, tag: str) -> dict[str, str | int]:
        code, timestamp = await self._state._generate_confirmation_code(tag)
        return {
            "p": self._state._device_id,
            "a": self._state.user.id64,
            "k": code,
            "t": timestamp,
            "m": "android",
            "tag": tag,
        }

    async def _perform_op(self, op: str) -> None:
        params = await self._confirm_params(op) | {"op": op, "cid": self.id, "ck": self.nonce}
        resp = await self._state.http.get(URL.COMMUNITY / "mobileconf/ajaxop", params=params)
        if not resp["success"]:
            raise ConfirmationError(resp.get("message", "Unknown error"))

    async def confirm(self) -> None:
        await self._perform_op("allow")

    async def cancel(self) -> None:
        await self._perform_op("cancel")

    async def details(self) -> str:
        params = await self._confirm_params(f"details{self.id}")
        resp = await self._state.http.get(URL.COMMUNITY / f"mobileconf/details/{self.id}", params=params)
        if not resp["success"]:
            raise ConfirmationError(resp.get("message", "Unknown error"))
        return resp["html"]
