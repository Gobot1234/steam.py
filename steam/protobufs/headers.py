"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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

This is an updated copy of
https://github.com/ValvePython/steam/blob/master/steam/core/msg/headers.py
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any, ClassVar, cast

import betterproto

from ..enums import Result
from ..utils import clear_proto_bit, set_proto_bit  # noqa
from .base import CMsgProtoBufHeader
from .emsg import EMsg  # noqa

__all__ = (
    "do_nothing_case",
    "MsgHdr",
    "ExtendedMsgHdr",
    "MsgHdrProto",
    "GCMsgHdr",
    "GCMsgHdrProto",
)

try:
    from _typing import _idfunc as do_nothing_case  # a fair bit faster than the python noop version
except ImportError:

    def do_nothing_case(value: str) -> str:
        return value


do_nothing_case = cast(betterproto.Casing, do_nothing_case)


class BaseMsgHdr:
    __slots__ = ()

    STRUCT: ClassVar[struct.Struct]
    PACK: ClassVar[tuple[str, ...]]
    body: ClassVar[Any]

    def __init_subclass__(cls, proto: bool = False, cast_msg_to_emsg: bool = True) -> None:
        if cls.__name__ == "GCMsgHdr":
            return  # can't generate parse and bytes for this as it doesn't have a "normal" structure

        # generate the parse and __bytes__ methods
        cast = "EMsg" if cast_msg_to_emsg else ""

        # this is a bit of a mess but this unpacks the data from self.STRUCT
        # then sets self.msg and optionally converts it to an EMsg
        # then if `proto`, sets the header length and parses the body
        exec(
            f"""
def parse(self, data: bytes) -> None:
    msg, {", ".join(f"self.{p}" for p in cls.PACK[1:])} = self.STRUCT.unpack_from(data)
    {f"self.msg = {cast}({'clear_proto_bit(msg)' if proto else 'msg'})"}

    {f"self.length += {cls.STRUCT.size}" if proto else ""}
    {f"self.body = self.body.parse(data[{cls.STRUCT.size} : self.length])" if proto else ""}

cls.parse = parse
"""
        )

        # again a bit of a mess but this serializes the body
        # alters self.length to be the proto length (hack to get picked up in cls.PACK)
        # packs self using self.STRUCT
        # then if `proto`, adds the protobuf info
        exec(
            f"""
def __bytes__(self) -> bytes:
    {"proto_data = bytes(self.body)" if proto else ""}
    {f"self.length = len(proto_data)" if proto else ""}
    return self.STRUCT.pack(
        {"set_proto_bit(self.msg)" if proto else "self.msg"},
        {", ".join(f"self.{p}" for p in cls.PACK[1:])}
    ) {"+ proto_data" if proto else ""}

cls.__bytes__ = __bytes__
"""
        )

    def __repr__(self) -> str:
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in self.PACK]
        if self.body is not self:
            resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(do_nothing_case).items())
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    if TYPE_CHECKING:

        def parse(self, data: bytes) -> None:
            ...

        def __bytes__(self) -> bytes:
            ...


class MsgHdr(BaseMsgHdr):
    __slots__ = (
        "msg",
        "eresult",
        "job_name_target",
        "job_id_target",
        "job_id_source",
        "body",
    )

    STRUCT = struct.Struct("<Iqq")
    PACK = ("msg", "job_id_target", "job_id_source")
    body: MsgHdr

    def __init__(self, data: bytes | None = None):
        self.msg = None
        self.eresult = Result.Invalid
        self.job_name_target = None
        self.job_id_target = -1
        self.job_id_source = -1
        self.body = self

        if data:
            self.parse(data)


class ExtendedMsgHdr(BaseMsgHdr):
    __slots__ = (
        "body",
        "job_name_target",
        "msg",
        "header_size",
        "header_version",
        "job_id_target",
        "job_id_source",
        "header_canary",
        "steam_id",
        "session_id",
    )

    STRUCT = struct.Struct("<IBHqqBqi")
    PACK = __slots__[2:]
    body: ExtendedMsgHdr

    def __init__(self, data: bytes | None = None):
        self.msg = None
        self.header_size = 36
        self.header_version = 2
        self.job_name_target = None
        self.job_id_target = 0
        self.job_id_source = 0
        self.header_canary = 239
        self.steam_id = -1
        self.session_id = -1
        self.body = self

        if data:
            self.parse(data)

            if self.header_size != 36 or self.header_version != 2:
                raise RuntimeError("Failed to parse header")


class MsgHdrProto(BaseMsgHdr, proto=True):
    __slots__ = ("body", "msg", "length")

    STRUCT = struct.Struct("<II")
    PACK = ("msg", "length")
    body: CMsgProtoBufHeader

    def __init__(self, data: bytes | None = None):
        self.msg = None
        self.body = CMsgProtoBufHeader()
        self.length = 0

        if data:
            self.parse(data)


class GCMsgHdr(BaseMsgHdr, cast_msg_to_emsg=False):
    __slots__ = ("header_version", "job_id_target", "job_id_source", "msg", "body")

    STRUCT = struct.Struct("<Hqq")
    PACK = ()
    body: GCMsgHdr

    def __init__(self, data: bytes | None = None):
        self.msg = None

        self.header_version = 1
        self.job_id_target = -1
        self.job_id_source = 0
        self.body = self

        if data:
            self.parse(data)

    # special cases
    def __bytes__(self) -> bytes:
        return self.STRUCT.pack(self.header_version, self.job_id_target, self.job_id_source)

    def parse(self, data: bytes) -> None:
        (
            self.header_version,
            self.job_id_target,
            self.job_id_source,
        ) = self.STRUCT.unpack_from(data)


class GCMsgHdrProto(BaseMsgHdr, proto=True, cast_msg_to_emsg=False):
    __slots__ = ("msg", "body", "length")

    STRUCT = struct.Struct("<Ii")
    PACK = ("msg", "length")
    body: CMsgProtoBufHeader

    def __init__(self, data: bytes | None = None):
        self.msg = None
        self.body = CMsgProtoBufHeader()
        self.length = 0

        if data:
            self.parse(data)
