"""Classes to (de)serialize various struct messages"""

import struct

from .emsg import EMsg
from ..enums import EResult, EUniverse
from ..utils import binary_loads

_emsg_map = dict()


def get_struct(emsg: EMsg) -> 'StructMessage':
    return _emsg_map.get(emsg)


class StructReader:
    def __init__(self, data):
        if not isinstance(data, bytes):
            raise ValueError("Only works with bytes")
        self.data = data
        self.offset = 0

    def __len__(self):
        return len(self.data)

    def rlen(self):
        return max(0, len(self) - self.offset)

    def read(self, n=1):
        self.offset += n
        return self.data[self.offset - n:self.offset]

    def read_cstring(self, terminator=b'\x00'):
        null_index = self.data.find(terminator, self.offset)
        if null_index == -1:
            raise RuntimeError("Reached end of buffer")
        result = self.data[self.offset:null_index]  # bytes without the terminator
        self.offset = null_index + len(terminator)  # advance offset past terminator
        return result

    def unpack(self, format_text):
        data = struct.unpack_from(format_text, self.data, self.offset)
        self.offset += struct.calcsize(format_text)
        return data

    def skip(self, n):
        self.offset += n


class StructMessageMeta(type):
    """Automatically adds subclasses of :class:`StructMessage` to the ``EMsg`` map"""

    def __new__(mcs, name, bases, attrs):
        cls = super().__new__(mcs, name, bases, attrs)
        if name != 'StructMessage':
            try:
                _emsg_map[EMsg[name]] = cls
            except KeyError:
                pass

        return cls


class StructMessage(metaclass=StructMessageMeta):
    def __init__(self, data=None):
        if data:
            self.load(data)

    def serialize(self):
        raise NotImplementedError

    def load(self, data):
        raise NotImplementedError


class ChannelEncryptRequest(StructMessage):
    protocolVersion = 1
    universe = EUniverse.Invalid
    challenge = b''

    def serialize(self):
        return struct.pack("<II", self.protocolVersion, self.universe) + self.challenge

    def load(self, data):
        self.protocolVersion, universe = struct.unpack_from("<II", data)
        self.universe = EUniverse(universe)
        if len(data) > 8:
            self.challenge = data[8:]

    def __str__(self):
        return f"""
        protocolVersion {self.protocolVersion}
        universe: {self.universe!r}
        challenge: {self.challenge!r}
        """


class ChannelEncryptResponse(StructMessage):
    protocolVersion = 1
    keySize = 128
    key = ''
    crc = 0

    def serialize(self):
        return struct.pack("<II128sII", self.protocolVersion, self.keySize, self.key, self.crc, 0)

    def load(self, data):
        self.protocolVersion, self.keySize, self.key, self.crc, _ = struct.unpack_from("<II128sII", data)

    def __str__(self):
        return f"""
        protocolVersion: {self.protocolVersion}
        keySize: {self.keySize}
        key: {self.key!r}
        crc: {self.crc}
        """


class ChannelEncryptResult(StructMessage):
    eresult = EResult.Invalid

    def serialize(self):
        return struct.pack("<I", self.eresult)

    def load(self, data):
        result = struct.unpack_from("<I", data)[0]
        self.eresult = EResult(result)

    def __str__(self):
        return f"eresult: {self.eresult!r}"


class ClientLogOnResponse(StructMessage):
    eresult = EResult.Invalid

    def serialize(self):
        return struct.pack("<I", self.eresult)

    def load(self, data):
        result = struct.unpack_from("<I", data)[0]
        self.eresult = EResult(result)


class ClientVACBanStatus(StructMessage):
    class VACBanRange:
        start = 0
        end = 0

        def __str__(self):
            return f"""
            start: {self.start}
            end: {self.end}
            """

    @property
    def numBans(self):
        return len(self.ranges)

    def __init__(self, _):
        super().__init__(self)
        self.ranges = list()

    def load(self, data):
        buf = StructReader(data)
        numBans, = buf.unpack("<I")

        for _ in range(numBans):
            m = self.VACBanRange()
            self.ranges.append(m)

            m.start, m.end, _ = buf.unpack("<III")

            if m.start > m.end:
                m.start, m.end = m.end, m.start

    def __str__(self):
        text = [f"numBans: {self.numBans}"]

        for m in self.ranges:  # emulate Protobuf text format
            m = str(m).replace("\n", "\n    ", 2)
            text.append(f'ranges {m}')

        return '\n'.join(text)


class ClientChatMsg(StructMessage):
    steamIdChatter = 0
    steamIdChatRoom = 0
    ChatMsgType = 0
    text = ""

    def serialize(self):
        rbytes = struct.pack("<QQI", self.steamIdChatter, self.steamIdChatRoom, self.ChatMsgType)
        rbytes += self.text.encode('utf-8') + b'\x00'
        return rbytes

    def load(self, data):
        buf = StructReader(data)
        self.steamIdChatter, self.steamIdChatRoom, self.ChatMsgType = buf.unpack("<QQI")
        self.text = buf.read_cstring().decode('utf-8')

    def __str__(self):
        return f"""
        steamIdChatter: {self.steamIdChatter}
        steamIdChatRoom: {self.steamIdChatRoom}
        ChatMsgType: {self.ChatMsgType}
        text: {self.text!r}
        """


class ClientJoinChat(StructMessage):
    steamIdChat = 0
    isVoiceSpeaker = False

    def serialize(self):
        return struct.pack("<Q?", self.steamIdChat, self.isVoiceSpeaker)

    def load(self, data):
        (self.steamIdChat, self.isVoiceSpeaker) = struct.unpack_from("<Q?", data)


class ClientChatMemberInfo(StructMessage):
    steamIdChat = 0
    type = 0
    steamIdUserActedOn = 0
    chatAction = 0
    steamIdUserActedBy = 0

    def serialize(self):
        return struct.pack("<QIQIQ", self.steamIdChat, self.type, self.steamIdUserActedOn, self.chatAction,
                           self.steamIdUserActedBy)

    def load(self, data):
        (self.steamIdChat,
         self.type,
         self.steamIdUserActedOn,
         self.chatAction,
         self.steamIdUserActedBy
         ) = struct.unpack_from("<QIQIQ", data)

    def __str__(self):
        return f"""
        steamIdChat: {self.steamIdChat}
        type: {self.type}
        steamIdUserActedOn: {self.steamIdUserActedOn}
        chatAction: {self.chatAction}
        steamIdUserActedBy: {self.steamIdUserActedBy}
        """


class ClientChatEnter(StructMessage):
    steamIdChat = 0
    steamIdFriend = 0
    chatRoomType = 0
    steamIdOwner = 0
    steamIdClan = 0
    chatFlags = 0
    enterResponse = 0
    numMembers = 0
    chatRoomName = ""
    memberList = []

    def __init__(self, data=None):
        super().__init__(data)
        if data:
            self.load(data)

    def load(self, data):
        buf, self.memberList = StructReader(data), list()

        (self.steamIdChat,
         self.steamIdFriend,
         self.chatRoomType,
         self.steamIdOwner,
         self.steamIdClan,
         self.chatFlags,
         self.enterResponse,
         self.numMembers) = buf.unpack("<QQIQQ?II")
        
        self.chatRoomName = buf.read_cstring().decode('utf-8')

        for _ in range(self.numMembers):
            self.memberList.append(binary_loads(buf.read(64))['MessageObject'])

        self.UNKNOWN1, = buf.unpack("<I")

    def __str__(self):
        members_list = '\n'.join([f"memberList: {m}" for m in self.memberList])
        return f"""
        steamIdChat: {self.steamIdChat}
        steamIdFriend: {self.steamIdFriend}
        chatRoomType: {self.chatRoomType!r}
        steamIdOwner: {self.steamIdOwner}
        steamIdClan: {self.steamIdClan}
        chatFlags: {self.chatFlags!r}
        enterResponse: {self.enterResponse!r}
        numMembers: {self.numMembers!r}
        chatRoomName: {self.chatRoomName!r}
        {members_list}
        """
