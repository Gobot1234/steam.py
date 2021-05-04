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
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar

import betterproto
from typing_extensions import TypeAlias

from ..enums import IE, Result
from .emsg import *
from .headers import *
from .protobufs import *
from .unified import *

M = TypeVar("M", bound=betterproto.Message)
GetProtoType: TypeAlias = "Optional[type[betterproto.Message]]"
ALLOWED_HEADERS = (ExtendedMsgHdr, MsgHdrProto, GCMsgHdrProto)
betterproto.safe_snake_case = do_nothing_case


def get_cmsg(msg: IE) -> GetProtoType:
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

    def __init__(self, msg: IE, data: Optional[bytes], **kwargs: Any):
        self.msg: IE = msg
        self.body: Optional[M] = None
        self.payload: Optional[bytes] = data[self.skip :] if data else None

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

    def _parse(self, proto: Optional[type[M]]) -> None:
        if proto:
            self.body = proto()
            if self.payload:
                self.body.parse(self.payload)

    @property
    def msg(self) -> IE:
        """:class:`IntEnum`: The :attr:`header.msg`."""
        return self.header.msg

    @msg.setter
    def msg(self, value: int) -> None:
        self.header.msg = value

    @property
    def steam_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The :attr:`header`'s 64 bit Steam ID."""
        return self.header.body.steam_id if isinstance(self.header, ALLOWED_HEADERS) else None

    @steam_id.setter
    def steam_id(self, value: int) -> None:
        if isinstance(self.header, ALLOWED_HEADERS):
            self.header.body.steam_id = value

    @property
    def session_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The :attr:`header`'s session ID."""
        return self.header.body.session_id if isinstance(self.header, ALLOWED_HEADERS) else None

    @session_id.setter
    def session_id(self, value: int) -> None:
        if isinstance(self.header, ALLOWED_HEADERS):
            self.header.body.session_id = value

    @property
    def result(self) -> Optional[Result]:
        """Optional[:class:`.Result`]: The :attr:`header`'s eresult."""
        if isinstance(self.header, ALLOWED_HEADERS):
            return Result.try_value(getattr(self.body, "eresult", 0) or self.header.body.eresult)

    def parse(self) -> None:
        """Parse the payload/data into a protobuf."""
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
        data: Optional[bytes] = None,
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
        data: Optional[bytes] = None,
        um_name: Optional[str] = None,
        **kwargs: Any,
    ):
        self.header = MsgHdrProto(data)
        if um_name:
            self.header.body.job_name_target = um_name
        self.skip = self.header.length
        super().__init__(msg, data, **kwargs)

    def parse(self) -> None:
        """Parse the payload/data into a protobuf."""
        if self.msg in (
            EMsg.ServiceMethod,
            EMsg.ServiceMethodResponse,
            EMsg.ServiceMethodSendToClient,
            EMsg.ServiceMethodCallFromClient,
        ):
            name = self.header.body.job_name_target
            if name:
                self.header.body.job_name_target = name = name.rsplit("#", maxsplit=1)[0]
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
        msg: IE,
        data: Optional[bytes] = None,
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
        msg: IE,
        data: Optional[bytes] = None,
        **kwargs: Any,
    ):
        self.header = GCMsgHdrProto(data)
        self.skip = self.header.length
        super().__init__(msg, data, **kwargs)
