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

This is an updated version of https://github.com/ValvePython/steam/tree/master/steam/core/msg
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import betterproto
from typing_extensions import TypeAlias

from ..enums import IntEnum, Result
from .emsg import *
from .headers import *
from .protobufs import *
from .unified import *

M = TypeVar("M", bound=betterproto.Message, covariant=True)
GetProtoType: TypeAlias = "type[betterproto.Message] | None"
ALLOWED_HEADERS = (ExtendedMsgHdr, MsgHdrProto, GCMsgHdrProto)
betterproto.safe_snake_case = do_nothing_case


def get_cmsg(msg: IntEnum) -> GetProtoType:
    """Get a protobuf from its EMsg."""
    try:
        return PROTOBUFS[msg]
    except KeyError:
        return None


def get_um(name: str, request: bool = True) -> GetProtoType:
    """Get the protobuf for a certain Unified Message."""
    try:
        return UMS[f"{name}#1_{'Request' if request else 'Response'}"]
    except KeyError:
        return None


class MsgBase(Generic[M]):
    __slots__ = ("header", "body", "payload", "skip")

    if sys.version_info < (3, 9):  # see https://bugs.python.org/issue39168 for the rational behind this

        def __new__(cls, *args: Any, **kwargs: Any):  # type: ignore
            return object.__new__(cls)

    def __init__(self, msg: IntEnum, data: bytes | None, **kwargs: Any):
        self.msg = msg
        self.body: M = None  # type: ignore
        self.payload: bytes | None = data[self.skip :] if data else None

        self.parse()
        if kwargs and self.body is not None:
            self.body.from_dict(kwargs)

    def __repr__(self) -> str:
        attrs = ("msg", "header")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        if self.body is not None:
            resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(do_nothing_case).items())
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __bytes__(self) -> bytes:
        return bytes(self.header) + bytes(self.body)

    def _parse(self, proto: type[M] | None) -> None:
        if proto:
            self.body = proto()
            if self.payload:
                self.body.parse(self.payload)

    @property
    def msg(self) -> IntEnum:
        return self.header.msg

    @msg.setter
    def msg(self, value: IntEnum) -> None:
        self.header.msg = value

    @property
    def steam_id(self) -> int:
        return self.header.body.steam_id

    @steam_id.setter
    def steam_id(self, value: int) -> None:
        self.header.body.steam_id = value

    @property
    def session_id(self) -> int:
        return self.header.body.session_id

    @session_id.setter
    def session_id(self, value: int) -> None:
        self.header.body.session_id = value

    @property
    def result(self) -> Result:
        return Result.try_value(getattr(self.body, "eresult", 0) or self.header.body.eresult)

    def parse(self) -> None:
        proto = get_cmsg(self.msg)
        self._parse(proto)


if not TYPE_CHECKING:
    MsgBase.__class_getitem__ = classmethod(
        lambda cls, params: cls
    )  # really don't want this to be picked up by linters


class Msg(MsgBase[M]):
    """A wrapper around received messages."""

    __slots__ = ()

    def __init__(
        self,
        msg: EMsg,
        data: bytes | None = None,
        extended: bool = False,
        **kwargs: Any,
    ):
        self.header = ExtendedMsgHdr(data) if extended else MsgHdr(data)
        self.skip = self.header.STRUCT.size
        super().__init__(msg, data, **kwargs)


class MsgProto(MsgBase[M]):
    """A wrapper around received protobuf messages."""

    __slots__ = ()

    def __init__(
        self,
        msg: EMsg,
        data: bytes | None = None,
        um_name: str | None = None,
        **kwargs: Any,
    ):
        self.header = MsgHdrProto(data)
        if um_name:
            self.header.body.job_name_target = um_name
        self.skip = self.header.length
        super().__init__(msg, data, **kwargs)

    def parse(self) -> None:
        if self.msg in (
            EMsg.ServiceMethod,
            EMsg.ServiceMethodResponse,
            EMsg.ServiceMethodSendToClient,
            EMsg.ServiceMethodCallFromClient,
        ):
            name = self.header.body.job_name_target
            if name:
                name, _, __ = name.partition("#")
                self.header.body.job_name_target = name
                proto = get_um(name, self.msg in (EMsg.ServiceMethod, EMsg.ServiceMethodCallFromClient))
            else:
                proto = None

        else:
            proto = get_cmsg(self.msg)

        self._parse(proto)


class GCMsg(MsgBase[M]):
    """A wrapper around received GC messages, mainly for extensions."""

    __slots__ = ()

    def __init__(
        self,
        msg: IntEnum,
        data: bytes | None = None,
        **kwargs: Any,
    ):
        self.header = GCMsgHdr(data)
        self.skip = self.header.STRUCT.size
        super().__init__(msg, data, **kwargs)


class GCMsgProto(MsgBase[M]):
    """A wrapper around received GC protobuf messages, mainly for extensions."""

    __slots__ = ()

    def __init__(
        self,
        msg: IntEnum,
        data: bytes | None = None,
        **kwargs: Any,
    ):
        self.header = GCMsgHdrProto(data)
        self.skip = self.header.length
        super().__init__(msg, data, **kwargs)
