# -*- coding: utf-8 -*-

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
from typing import Any, Optional, Union

from betterproto import snake_case

from ..enums import EResult
from ..utils import clear_proto_bit, set_proto_bit
from . import steammessages_base
from .emsg import EMsg

__all__ = (
    "MsgHdr",
    "GCMsgHdr",
    "GCMsgHdrProto",
    "ExtendedMsgHdr",
    "MsgHdrProtoBuf",
)


class _MsgHdrBody:
    __slots__ = ("msg",)

    def __init__(self, msg: Union[MsgHdr, ExtendedMsgHdr]):
        self.msg = msg

    def __getattr__(self, item: str) -> Any:
        return getattr(self.msg, item)


class MsgHdr:
    """The message header for :class:`steam.protobufs.Msg` objects."""

    __slots__ = ("msg", "eresult", "job_name_target", "job_id_target", "job_id_source", "body")
    SIZE = 20

    def __init__(self, data: Optional[bytes] = None):
        self.msg = None
        self.eresult = EResult.Invalid
        self.job_name_target = None
        self.job_id_target = -1
        self.job_id_source = -1
        if data:
            self.parse(data)

        self.body = _MsgHdrBody(self)

    def __repr__(self) -> str:
        attrs = ("msg", "job_id_target", "job_id_source")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<MsgHdr {' '.join(resolved)}>"

    def __bytes__(self) -> bytes:
        return struct.pack("<Iqq", self.msg, self.job_id_target, self.job_id_source)

    def parse(self, data: bytes) -> None:
        """Parse the header."""
        msg, self.job_id_target, self.job_id_source = struct.unpack_from("<Iqq", data)
        self.msg = EMsg(msg)


class ExtendedMsgHdr:
    """The extended message header for :class:`steam.protobufs.Msg` objects."""

    __slots__ = (
        "body",
        "msg",
        "steam_id",
        "session_id",
        "header_size",
        "header_version",
        "header_canary",
        "job_name_target",
        "job_id_target",
        "job_id_source",
    )
    SIZE = 36

    def __init__(self, data: Optional[bytes] = None):
        self.msg = None
        self.header_size = 36
        self.header_version = 2
        self.job_name_target = None
        self.job_id_target = -1
        self.job_id_source = -1
        self.header_canary = 239
        self.steam_id = -1
        self.session_id = -1
        if data:
            self.parse(data)

        self.body = _MsgHdrBody(self)

    def __repr__(self) -> str:
        attrs = ("msg", "steam_id", "session_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<ExtendedMsgHdr {' '.join(resolved)}>"

    def __bytes__(self) -> bytes:
        return struct.pack(
            "<IBHqqBqi",
            self.msg,
            self.header_size,
            self.header_version,
            self.job_id_target,
            self.job_id_source,
            self.header_canary,
            self.steam_id,
            self.session_id,
        )

    def parse(self, data: bytes) -> None:
        """Parse the header."""
        (
            msg,
            self.header_size,
            self.header_version,
            self.job_id_target,
            self.job_id_source,
            self.header_canary,
            self.steam_id,
            self.session_id,
        ) = struct.unpack_from("<IBHqqBqi", data)

        self.msg = EMsg(msg)

        if self.header_size != 36 or self.header_version != 2:
            raise RuntimeError("Failed to parse header")


class MsgHdrProtoBuf:
    """The message header for :class:`steam.protobufs.MsgProto` objects."""

    SIZE = 8
    __slots__ = ("body", "msg", "_full_size")

    def __init__(self, data: Optional[bytes] = None):
        self.msg = None
        self.body = steammessages_base.CMsgProtoBufHeader()
        self._full_size = 0

        if data:
            self.parse(data)

    def __repr__(self) -> str:
        attrs = ("msg",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(snake_case).items())
        return f"<MsgHdrProtoBuf {' '.join(resolved)}>"

    def __bytes__(self) -> bytes:
        proto_data = bytes(self.body)
        return struct.pack("<II", set_proto_bit(self.msg), len(proto_data)) + proto_data

    def parse(self, data: bytes) -> None:
        """Parse the header."""
        msg, proto_length = struct.unpack_from("<II", data)

        self.msg = EMsg(clear_proto_bit(msg))
        self._full_size = self.SIZE + proto_length
        self.body.parse(data[self.SIZE : self._full_size])


class GCMsgHdr:
    """The message header for :class:`steam.protobufs.MsgProto` objects."""

    __slots__ = ("header_version", "target_job_id", "source_job_id", "msg")
    SIZE = 18

    def __init__(self, data: Optional[bytes] = None):
        self.msg = None

        self.header_version = 1
        self.target_job_id = -1
        self.source_job_id = 0  # might be -1 again

        if data:
            self.parse(data)

    def __repr__(self) -> str:
        return f"<GCMsgHdr {' '.join(f'{attr}={getattr(self, attr)!r}' for attr in self.__slots__)}>"

    def __bytes__(self) -> bytes:
        return struct.pack("<Hqq", self.header_version, self.target_job_id, self.source_job_id)

    def parse(self, data: bytes) -> None:
        (
            self.header_version,
            self.target_job_id,
            self.source_job_id,
        ) = struct.unpack_from("<Hqq", data)


class GCMsgHdrProto:
    __slots__ = ("msg", "body", "header_length")
    SIZE = 8

    def __init__(self, data: Optional[bytes] = None):
        self.msg = None
        self.body = steammessages_base.CMsgProtoBufHeader()
        self.header_length = 0

        if data:
            self.parse(data)

    def __repr__(self) -> str:
        attrs = ("msg",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(snake_case).items())
        return f"<GCMsgHdrProto {' '.join(resolved)}>"

    def __bytes__(self) -> bytes:
        proto_data = bytes(self.body)
        self.header_length = len(proto_data)
        return struct.pack("<Ii", set_proto_bit(self.msg), self.header_length) + proto_data

    def parse(self, data: bytes) -> None:
        msg, self.header_length = struct.unpack_from("<Ii", data)

        self.msg = clear_proto_bit(msg)

        if self.header_length:
            self.body = self.body.parse(data[self.SIZE : self.SIZE + self.header_length])
