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

from typing import Optional, Type, Union

import betterproto

from .emsg import EMsg
from .headers import *
from .protobufs import PROTOBUFS
from .unified import UMS
from ..enums import IntEnum


def get_cmsg(emsg: Union[EMsg, int]) -> Optional[Type[betterproto.Message]]:
    return PROTOBUFS.get(EMsg.try_value(emsg))


def get_um(method_name: str) -> Optional[Type[betterproto.Message]]:
    return UMS.get(method_name)


class _Enum(IntEnum):
    """Protocol buffers enumeration base class. Acts like `enum.IntEnum`."""

    @classmethod
    def from_string(cls, name: str) -> IntEnum:
        """Return the value which corresponds to the string name."""
        try:
            return cls.__members__[name]
        except KeyError as e:
            raise ValueError(f"Unknown value {name} for enum {cls.__name__}") from e


# add in our speeder enum
betterproto.Enum = _Enum


class Msg:
    __slots__ = ('header', 'proto', 'body', 'payload')

    def __init__(self, msg: EMsg,
                 data: bytes = None,
                 extended: bool = False,
                 parse: bool = True,
                 **kwargs):
        self.header = ExtendedMsgHdr(data) if extended else MsgHdr(data)
        self.msg = EMsg.try_value(msg)

        self.proto = False
        self.body: Optional[betterproto.Message] = None
        self.payload: Optional[bytes] = None

        if data:
            self.payload = data[self.header.SIZE:]
        if parse:
            self.parse()
        if kwargs:
            for (key, value) in kwargs.items():
                if isinstance(value, IntEnum):
                    kwargs[key] = value.value
            self.body.from_dict(kwargs)

    def __repr__(self):
        attrs = (
            'msg', 'header',
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        if not isinstance(self.body, str) and self.body is not None:
            resolved.extend([f'{k}={v!r}' for k, v in self.body.to_dict(betterproto.Casing.SNAKE).items()])
        else:
            resolved.append(f'body={self.body!r}')
        return f"<Msg {' '.join(resolved)}>"

    def parse(self):
        if self.body is None:
            proto = get_cmsg(self.msg)

            if proto:
                self.body = proto().parse(self.payload)
                self.payload = None
            else:
                self.body = '!!! Failed to resolve message !!!'

    @property
    def msg(self):
        return self.header.msg

    @msg.setter
    def msg(self, value):
        self.header.msg = EMsg.try_value(value)

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

    def __bytes__(self):
        return bytes(self.header) + bytes(self.body)


class MsgProto:
    __slots__ = ('header', '_header', 'proto', 'body', 'payload', 'um_name')

    def __init__(self, msg: EMsg,
                 data: bytes = None,
                 parse: bool = True,
                 um_name: str = None,
                 **kwargs):
        self._header = MsgHdrProtoBuf(data)
        self.header = self._header.proto
        self.msg = msg
        self.proto = True
        self.um_name = um_name
        self.body: Optional[betterproto.Message] = None
        self.payload: Optional[bytes] = None

        if data:
            self.payload = data[self._header._full_size:]
        if parse:
            self.parse()
        if kwargs:
            for (key, value) in kwargs.items():
                if isinstance(value, IntEnum):
                    kwargs[key] = value.value
            self.body.from_dict(kwargs)

    def __repr__(self):
        attrs = (
            'msg', '_header',
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        if not isinstance(self.body, str) and self.body is not None:
            resolved.extend([f'{k}={v!r}' for k, v in self.body.to_dict(betterproto.Casing.SNAKE).items()])
        else:
            resolved.append(f'body={self.body!r}')
        return f"<MsgProto {' '.join(resolved)}>"

    def parse(self):
        if self.body is None:
            if self.msg in (EMsg.ServiceMethod, EMsg.ServiceMethodResponse,
                            EMsg.ServiceMethodSendToClient, EMsg.ServiceMethodCallFromClient):
                name = self.header.target_job_name or self.um_name
                proto = get_um(name)
                if not name.endswith('_Response') and proto is None:
                    proto = get_um(f'{name}_Response')  # assume its a response
                if name:
                    self.header.target_job_name = name.replace('_Request', '').replace('_Response', '')

            else:
                proto = get_cmsg(self.msg)

            if proto:
                self.body = proto()
                if self.payload:
                    self.body = self.body.parse(self.payload)
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

    def __bytes__(self):
        return bytes(self._header) + bytes(self.body)
