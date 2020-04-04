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

This is a copy of https://github.com/ValvePython/steam/blob/master/steam/enums/emsg.py
"""

import fnmatch

from . import steammessages_base_pb2 as message_base
from . import steammessages_clientserver_2_pb2 as client_server_2
from . import steammessages_clientserver_friends_pb2 as client_server_friends
from . import steammessages_clientserver_login_pb2 as client_server_login
from . import steammessages_clientserver_pb2 as client_server
from .emsg import EMsg
from .headers import MsgHdr, ExtendedMsgHdr, MsgHdrProtoBuf, GCMsgHdr, GCMsgHdrProto
from .structs import get_struct
from .unified import get_um

cmsg_lookup_predefined = {
    EMsg.Multi: message_base.CMsgMulti,
    EMsg.ClientToGC: client_server_2.CMsgGCClient,
    EMsg.ClientFromGC: client_server_2.CMsgGCClient,
    EMsg.ClientServiceMethod: client_server_2.CMsgClientServiceMethodLegacy,
    EMsg.ClientServiceMethodResponse: client_server_2.CMsgClientServiceMethodLegacyResponse,
    EMsg.ClientGetNumberOfCurrentPlayersDP: client_server_2.CMsgDPGetNumberOfCurrentPlayers,
    EMsg.ClientGetNumberOfCurrentPlayersDPResponse: client_server_2.CMsgDPGetNumberOfCurrentPlayersResponse,
    EMsg.ClientLogonGameServer: client_server_login.CMsgClientLogon,
    EMsg.ClientCurrentUIMode: client_server_2.CMsgClientUIMode,
    EMsg.ClientChatOfflineMessageNotification: client_server_2.CMsgClientOfflineMessageNotification,
}

cmsg_lookup = dict()

for proto_module in [client_server, client_server_2, client_server_friends, client_server_login]:
    cmsg_list = proto_module.__dict__
    cmsg_list = fnmatch.filter(cmsg_list, 'CMsg*')
    cmsg_lookup.update(dict(zip(map(lambda cmsg_name: cmsg_name.lower(), cmsg_list),
                                map(lambda cmsg_name: getattr(proto_module, cmsg_name), cmsg_list))))


def get_cmsg(emsg):
    """Get protobuf for a given EMsg
    :param emsg: EMsg
    :type  emsg: :class:`steam.enums.emsg.EMsg`, :class:`int`
    :return: protobuf message
    """
    if not isinstance(emsg, EMsg):
        emsg = EMsg(emsg)

    if emsg in cmsg_lookup_predefined:
        return cmsg_lookup_predefined[emsg]
    else:
        enum_name = emsg.name.lower()
        if enum_name.startswith("econ"):  # special case for 'EconTrading_'
            enum_name = enum_name[4:]
        cmsg_name = "cmsg" + enum_name

    return cmsg_lookup.get(cmsg_name, None)


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
    proto = True
    body = None  #: protobuf message instance
    payload = None  #: Will contain body payload, if we fail to find correct proto message

    def __init__(self, msg, data=None, parse=True):
        self._header = MsgHdrProtoBuf(data)
        self.header = self._header.proto
        self.msg = msg

        if data:
            self.payload = data[self._header._fullsize:]

        if parse:
            self.parse()

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
    def msg(self):
        return self._header.msg

    @msg.setter
    def msg(self, value):
        self._header.msg = EMsg(value)

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
