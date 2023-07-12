"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass
from hashlib import sha1
from time import time
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from ._const import URL
from .errors import ConfirmationError
from .types.id import TradeOfferID

if TYPE_CHECKING:
    from .state import ConnectionState


__all__ = (
    "get_authentication_code",
    "get_confirmation_code",
    "get_device_id",
    "Tags",
    "Confirmation",
)

AUTH_CODE_CHARS: Final = "23456789BCDFGHJKMNPQRTVWXY"
AUTH_CODE_CHARS_LEN: Final = len(AUTH_CODE_CHARS)


def _hmac(secret: str, buffer: bytes) -> bytes:
    return hmac.new(base64.b64decode(secret), buffer, digestmod=sha1).digest()


def get_authentication_code(shared_secret: str, timestamp: int | None = None) -> str:
    """Get a Steam Guard code for signing in.

    Parameters
    -----------
    shared_secret
        Base 64 encoded shared secret from Steam Guard.
    timestamp
        The Unix timestamp to generate the key for. Defaults to the timestamp returned by :func:`time.time`.
    """
    timestamp = timestamp if timestamp is not None else int(time())
    time_hmac = _hmac(shared_secret, (timestamp // 30).to_bytes(8, "big"))
    begin = time_hmac[19] & 0xF

    full_code = int.from_bytes(time_hmac[begin : begin + 4], "big") & 0x7FFFFFFF

    code: list[str] = []
    for _ in range(5):
        full_code, i = divmod(full_code, AUTH_CODE_CHARS_LEN)
        code.append(AUTH_CODE_CHARS[i])
    return "".join(code)


def get_confirmation_code(identity_secret: str, tag: str, timestamp: int | None = None) -> str:
    """Get a trade confirmation code.

    Parameters
    -----------
    identity_secret
        Base 64 encoded identity secret from Steam Guard.
    tag
        The confirmation tag to encode.
    timestamp
        The time to generate the key for. Defaults to the timestamp returned by :func:`time.time`.
    """
    timestamp = timestamp if timestamp is not None else int(time())
    buffer = timestamp.to_bytes(8, "big") + tag.encode("ascii")
    return base64.b64encode(_hmac(identity_secret, buffer)).decode()


def get_device_id(id64: int) -> str:
    """Get the device ID for a user's 64-bit ID.

    Parameters
    -----------
    id64
        The 64-bit Steam ID to generate the device ID for.
    """
    # it works, however it's different that one generated from mobile app

    hexed_steam_id = sha1(str(id64).encode("ascii")).hexdigest()
    partial_id = [
        hexed_steam_id[:8],
        hexed_steam_id[8:12],
        hexed_steam_id[12:16],
        hexed_steam_id[16:20],
        hexed_steam_id[20:32],
    ]
    return f'android:{"-".join(partial_id)}'


Tags: TypeAlias = Literal["conf", "details", "accept", "reject", "list"]
# Tags: TypeAlias = Literal["conf", "details", "allow", "cancel", "list"]
# TODO: I'm not sure if these should also be modified to their old value (in the commented out line)


@dataclass(repr=False, slots=True)
class Confirmation:
    _state: ConnectionState
    id: int
    nonce: int
    creator_id: TradeOfferID  # this isn't really always the trade ID, but for our purposes this is fine

    def __repr__(self) -> str:
        return f"<Confirmation id={self.id} creator_id={self.creator_id}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Confirmation) and self.creator_id == other.creator_id and self.id == other.id

    async def _confirm_params(self, tag: Tags) -> dict[str, str | int]:
        code, timestamp = await self._state._get_confirmation_code(tag)
        return {
            "p": self._state._device_id,
            "a": self._state.user.id64,
            "k": code,
            "t": timestamp,
            "m": "android",
            "tag": tag,
        }

    async def _perform_op(self, op: Tags) -> None:
        params = await self._confirm_params(op) | {"op": op, "cid": self.id, "ck": self.nonce}
        resp = await self._state.http.get(URL.COMMUNITY / "mobileconf/ajaxop", params=params)
        if not resp["success"]:
            raise ConfirmationError(resp.get("message", "Unknown error"))

    # TODO: determine why keywords are right? test `cancel`
    async def confirm(self) -> None:
        await self._perform_op("allow")
        # ^ this is no longer "accept" as of the endpoint update to /mobileconf/getlist/ -- it is "allow", as it... used to be...
        # "yeah idk either" -- @zudsniper

    async def cancel(self) -> None:
        await self._perform_op("cancel")
        # ^ this is a change to conform with the revert of mobile API key words -- so `reject` -> `cancel`
