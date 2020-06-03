import struct

from . import steammessages_base, foobar
from .emsg import EMsg
from ..utils import set_proto_bit, clear_proto_bit


class MsgHdr:
    SIZE = struct.calcsize("<Iqq")

    def __init__(self, data: bytes = None):
        self.msg = EMsg.Invalid
        self.target_job_id = -1
        self.source_job_id = -1
        if data:
            self.load(data)

    def __repr__(self):
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in dir(self)
                    if attr[0] != '_']
        return f'<MsgHdr {" ".join(resolved)}>'

    def serialize(self):
        return struct.pack("<Iqq", self.msg, self.target_job_id, self.source_job_id)

    def load(self, data):
        (msg, self.target_job_id, self.source_job_id) = struct.unpack_from("<Iqq", data)
        self.msg = EMsg(msg)


class ExtendedMsgHdr:
    SIZE = struct.calcsize("<IBHqqBqi")

    def __init__(self, data: bytes = None):
        self.msg = EMsg.Invalid
        self.header_size = 36
        self.header_version = 2
        self.target_job_id = -1
        self.source_job_id = -1
        self.header_canary = 239
        self.steam_id = -1
        self.session_id = -1
        if data:
            self.load(data)

    def __repr__(self):
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in dir(self)
                    if attr[0] != '_']
        return f'<ExtendedMsgHdr {" ".join(resolved)}>'

    def serialize(self):
        return struct.pack("<IBHqqBqi", self.msg, self.header_size, self.header_version, self.target_job_id,
                           self.source_job_id, self.header_canary, self.steam_id, self.session_id)

    def load(self, data: bytes):
        (msg, self.header_size, self.header_version, self.target_job_id, self.source_job_id,
         self.header_canary, self.steam_id, self.session_id) = struct.unpack_from("<IBHqqBqi", data)

        self.msg = EMsg(msg)

        if self.header_size != 36 or self.header_version != 2:
            raise RuntimeError("Failed to parse header")


class MsgHdrProtoBuf:
    SIZE = _fullsize = struct.calcsize("<II")

    def __init__(self, data: bytes = None):
        self.proto = steammessages_base.CMsgProtoBufHeader()
        self.msg = EMsg.Invalid

        if data:
            self.load(data)

    def serialize(self) -> bytes:
        proto_data = self.proto.SerializeToString()
        return struct.pack("<II", set_proto_bit(self.msg.value), len(proto_data)) + proto_data

    def load(self, data: bytes) -> None:
        msg, proto_length = struct.unpack_from("<II", data)

        self.msg = EMsg(clear_proto_bit(msg))
        self._fullsize = self.SIZE + proto_length
        self.proto.FromString(data[self.SIZE:self._fullsize])


class GCMsgHdr:
    _size = struct.calcsize("<Hqq")
    proto = None
    headerVersion = 1
    targetJobID = -1
    sourceJobID = -1

    def __init__(self, msg, data=None):
        self.msg = clear_proto_bit(msg)

        if data:
            self.load(data)

    def serialize(self):
        return struct.pack("<Hqq", self.headerVersion, self.targetJobID, self.sourceJobID)

    def load(self, data):
        (self.headerVersion, self.targetJobID, self.sourceJobID) = struct.unpack_from("<Hqq", data)


class GCMsgHdrProto:
    _size = struct.calcsize("<Ii")
    headerLength = 0

    def __init__(self, msg, data=None):
        self.proto = foobar.CMsgProtoBufHeader()
        self.msg = clear_proto_bit(msg)

        if data:
            self.load(data)

    def serialize(self):
        proto_data = self.proto.SerializeToString()
        self.headerLength = len(proto_data)

        return struct.pack("<Ii", set_proto_bit(self.msg), self.headerLength) + proto_data

    def load(self, data):
        (msg, self.headerLength) = struct.unpack_from("<Ii", data)

        self.msg = clear_proto_bit(msg)

        if self.headerLength:
            x = GCMsgHdrProto._size
            self.proto.FromString(data[x:x + self.headerLength])
