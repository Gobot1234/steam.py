# -*- coding: utf-8 -*-

"""
MIT License

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

This is a copy of https://github.com/ValvePython/steam/tree/master/steam/core/msg
"""

from typing import Union, Optional, Type

import betterproto
import stringcase

from . import (
    steammessages_base,
    steammessages_clientserver_2,
    steammessages_clientserver_friends,
    steammessages_clientserver_login,
    steammessages_clientserver
)
from .emsg import EMsg
from .headers import MsgHdr, ExtendedMsgHdr, MsgHdrProtoBuf, GCMsgHdr, GCMsgHdrProto
from .protobufs import protobufs
from .structs import get_struct, StructMessage
from .unified import get_um
from ..enums import Enum, IntEnum


def get_cmsg(emsg: Union[EMsg, int]) -> Optional[Type[betterproto.Message]]:
    if isinstance(emsg, int):
        emsg = EMsg(emsg)

    return protobufs.get(emsg, None)


class _Casing(Enum):
    """Casing constants for serialization."""

    CAMEL = stringcase.camelcase
    SNAKE = stringcase.snakecase


class _Enum(IntEnum):
    """Protocol buffers enumeration base class. Acts like `enum.IntEnum`."""

    @classmethod
    def from_string(cls, name: str) -> int:
        """Return the value which corresponds to the string name."""
        try:
            return cls.__members__[name]
        except KeyError as e:
            raise ValueError(f"Unknown value {name} for enum {cls.__name__}") from e


# add in our speeder enum
betterproto.Casing = _Casing
betterproto.Enum = _Enum


class Msg:
    def __init__(self, msg, data: bytes = None, extended: bool = False, parse: bool = True):
        self.extended = extended
        self.header = ExtendedMsgHdr(data) if extended else MsgHdr(data)
        self.msg = EMsg.try_value(msg)

        self.proto = False
        self.body: Optional[StructMessage] = None  #: message instance
        self.payload: Optional[betterproto.Message] = None  # body payload, if we fail to find matching message class

        if data:
            self.payload = data[self.header._size:]

        if parse:
            self.parse()

    def __repr__(self):
        attrs = (
            'header', 'body', 'msg'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Msg {' '.join(resolved)}>"

    def parse(self):
        """Parses :attr:`payload` into :attr:`body` instance"""
        if self.body is None:
            deserializer = get_struct(self.msg)

            if deserializer:
                self.body = deserializer(self.payload)
                self.payload = None
            else:
                self.body = '!!! Failed to resolve message !!!'

    @property
    def msg(self):
        return self.header.msg

    @msg.setter
    def msg(self, value):
        self.header.msg = EMsg(value)

    @property
    def steam_id(self):
        return self.header.steam_id if isinstance(self.header, ExtendedMsgHdr) else None

    @steam_id.setter
    def steam_id(self, value):
        if isinstance(self.header, ExtendedMsgHdr):
            self.header.steam_id = value

    @property
    def session_id(self):
        return self.header.session_id if isinstance(self.header, ExtendedMsgHdr) else None

    @session_id.setter
    def session_id(self, value):
        if isinstance(self.header, ExtendedMsgHdr):
            self.header.session_id = value

    def serialize(self):
        return self.header.serialize() + self.body.serialize()


class MsgProto:

    def __init__(self, msg: EMsg, data: bytes = None, parse: bool = True, **kwargs):
        self._header = MsgHdrProtoBuf(data)
        self.header = self._header.proto
        self.msg = msg
        self.proto = True
        self.body: Optional[betterproto.Message] = None  #: protobuf message instance
        self.payload = None  #: Will contain body payload, if we fail to find correct proto message

        if data:
            self.payload = data[self._header._fullsize:]

        if parse:
            self.parse()

        if kwargs:
            self.body.from_dict(kwargs)

    def __repr__(self):
        attrs = (
            'msg', 'proto'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        resolved.extend([f'{key}={repr(value)}' for key, value in self.body.to_dict().items()])
        return f"<MsgProto {' '.join(resolved)}>"

    def parse(self):
        """Parses :attr:`payload` into :attr:`body` instance"""
        if self.body is None:
            if self.msg in (EMsg.ServiceMethod, EMsg.ServiceMethodResponse, EMsg.ServiceMethodSendToClient):
                proto = get_um(self.header.target_job_name)
            else:
                proto = get_cmsg(self.msg)

            if proto:
                self.body = proto()
                if self.payload:
                    self.body.FromString(self.payload)
                    self.payload = None
            else:
                self.body = '!!! Failed to resolve message !!!'

    @property
    def msg(self):
        return self._header.msg

    @msg.setter
    def msg(self, value):
        self._header.msg = EMsg.try_value(value)

    @property
    def steam_id(self):
        return self.header.steamid

    @steam_id.setter
    def steam_id(self, value):
        self.header.steamid = value

    @property
    def session_id(self):
        return self.header.client_sessionid

    @session_id.setter
    def session_id(self, value):
        self.header.client_sessionid = value

    def serialize(self):
        return self._header.serialize() + self.body.SerializeToString()
