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

from . import (
    steammessages_base_pb2 as message_base,
    steammessages_clientserver_2_pb2 as client_server_2,
    steammessages_clientserver_friends_pb2 as client_server_friends,
    steammessages_clientserver_login_pb2 as client_server_login,
    steammessages_clientserver_pb2 as client_server
)
from .emsg import EMsg
from .headers import MsgHdr, ExtendedMsgHdr, MsgHdrProtoBuf, GCMsgHdr, GCMsgHdrProto
from .protobufs import protobufs
from .structs import get_struct
from .unified import get_um
from ..utils import proto_fill_from_dict


def get_cmsg(emsg):
    if not isinstance(emsg, EMsg):
        emsg = EMsg(emsg)

    return protobufs.get(emsg, None)


class Msg:
    proto = False
    body = None  #: message instance
    payload = None  #: Will contain body payload, if we fail to find correct message class

    def __init__(self, msg, data=None, extended=False, parse=True):
        self.extended = extended
        self.header = ExtendedMsgHdr(data) if extended else MsgHdr(data)
        self.msg = msg

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
    def steamID(self):
        return self.header.steamID if isinstance(self.header, ExtendedMsgHdr) else None

    @steamID.setter
    def steamID(self, value):
        if isinstance(self.header, ExtendedMsgHdr):
            self.header.steamID = value

    @property
    def sessionID(self):
        return self.header.sessionID if isinstance(self.header, ExtendedMsgHdr) else None

    @sessionID.setter
    def sessionID(self, value):
        if isinstance(self.header, ExtendedMsgHdr):
            self.header.sessionID = value

    def serialize(self):
        return self.header.serialize() + self.body.serialize()


class MsgProto:

    def __init__(self, msg, data=None, parse=True, **kwargs):
        self._header = MsgHdrProtoBuf(data)
        self.header = self._header.proto
        self.msg = msg or self._header.msg
        self.proto = True
        self.body = None  #: protobuf message instance
        self.payload = None  #: Will contain body payload, if we fail to find correct proto message

        if data:
            self.payload = data[self._header._fullsize:]

        if parse:
            self.parse()

        if kwargs:
            proto_fill_from_dict(self.body, kwargs, False)

    def __repr__(self):
        attrs = (
            'msg', 'proto'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        resolved.extend([f'{proto.name}={repr(value)}' for proto, value in self.body.ListFields()])
        return f"<MsgProto {' '.join(resolved)}>"

    def parse(self):
        """Parses :attr:`payload` into :attr:`body` instance"""
        if self.body is None:
            if self.msg in (EMsg.ServiceMethod, EMsg.ServiceMethodResponse, EMsg.ServiceMethodSendToClient):
                is_resp = False if self.msg == EMsg.ServiceMethod else True
                proto = get_um(self.header.target_job_name, response=is_resp)
            else:
                proto = get_cmsg(self.msg)

            if proto:
                self.body = proto()
                if self.payload:
                    self.body.ParseFromString(self.payload)
                    self.payload = None
            else:
                self.body = '!!! Failed to resolve message !!!'

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
