"""Classes to (de)serialize various struct messages"""

import struct

from .emsg import EMsg
from ..enums import EResult, EUniverse
from ..utils import binary_loads

_emsg_map = dict()


def get_struct(emsg):
    return _emsg_map.get(emsg, None)


class StructReader:
    def __init__(self, data):
        """Simplifies parsing of struct data from bytes
        :param data: data bytes
        :type  data: :class:`bytes`
        """
        if not isinstance(data, bytes):
            raise ValueError("Only works with bytes")
        self.data = data
        self.offset = 0

    def __len__(self):
        return len(self.data)

    def rlen(self):
        """Number of remaining bytes that can be read
        :return: number of remaining bytes
        :rtype: :class:`int`
        """
        return max(0, len(self) - self.offset)

    def read(self, n=1):
        """Return n bytes
        :param n: number of bytes to return
        :type  n: :class:`int`
        :return: bytes
        :rtype: :class:`bytes`
        """
        self.offset += n
        return self.data[self.offset - n:self.offset]

    def read_cstring(self, terminator=b'\x00'):
        """Reads a single null termianted string
        :return: string without bytes
        :rtype: :class:`bytes`
        """
        null_index = self.data.find(terminator, self.offset)
        if null_index == -1:
            raise RuntimeError("Reached end of buffer")
        result = self.data[self.offset:null_index]  # bytes without the terminator
        self.offset = null_index + len(terminator)  # advance offset past terminator
        return result

    def unpack(self, format_text):
        """Unpack bytes using struct modules format
        :param format_text: struct's module format
        :type  format_text: :class:`str`
        :return data: result from :func:`struct.unpack_from`
        :rtype: :class:`tuple`
        """
        data = struct.unpack_from(format_text, self.data, self.offset)
        self.offset += struct.calcsize(format_text)
        return data

    def skip(self, n):
        """Skips the next ``n`` bytes
        :param n: number of bytes to skip
        :type  n: :class:`int`
        """
        self.offset += n


class StructMessageMeta(type):
    """Automatically adds subclasses of :class:`StructMessage` to the ``EMsg`` map"""

    def __new__(mcs, name, bases, class_dict):
        cls = super().__new__(mcs, name, bases, class_dict)

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
        (self.protocolVersion, universe) = struct.unpack_from("<II", data)

        self.universe = EUniverse(universe)

        if len(data) > 8:
            self.challenge = data[8:]

    def __str__(self):
        return '\n'.join(["protocolVersion: %s" % self.protocolVersion,
                          "universe: %s" % repr(self.universe),
                          "challenge: %s" % repr(self.challenge),
                          ])


class ChannelEncryptResponse(StructMessage):
    protocolVersion = 1
    keySize = 128
    key = ''
    crc = 0

    def serialize(self):
        return struct.pack("<II128sII", self.protocolVersion, self.keySize, self.key, self.crc, 0)

    def load(self, data):
        (self.protocolVersion, self.keySize, self.key, self.crc, _) = struct.unpack_from("<II128sII", data)

    def __str__(self):
        return '\n'.join(["protocolVersion: %s" % self.protocolVersion,
                          "keySize: %s" % self.keySize,
                          "key: %s" % repr(self.key),
                          "crc: %s" % self.crc,
                          ])


class ChannelEncryptResult(StructMessage):
    eresult = EResult.Invalid

    def serialize(self):
        return struct.pack("<I", self.eresult)

    def load(self, data):
        (result,) = struct.unpack_from("<I", data)
        self.eresult = EResult(result)

    def __str__(self):
        return "eresult: %s" % repr(self.eresult)


class ClientLogOnResponse(StructMessage):
    eresult = EResult.Invalid

    def serialize(self):
        return struct.pack("<I", self.eresult)

    def load(self, data):
        (result,) = struct.unpack_from("<I", data)
        self.eresult = EResult(result)


class ClientVACBanStatus(StructMessage):
    class VACBanRange:
        start = 0
        end = 0

        def __str__(self):
            return """
            {
            start: {}
            end: {}
            }
            """.format(self.start, self.end)

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
        text = ["numBans: %d" % self.numBans]

        for m in self.ranges:  # emulate Protobuf text format
            text.append("ranges " + str(m).replace("\n", "\n    ", 2))

        return '\n'.join(text)


class ClientChatMsg(StructMessage):
    steamIdChatter = 0
    steamIdChatRoom = 0
    ChatMsgType = 0
    text = ""

    def serialize(self):
        rbytes = struct.pack("<QQI", self.steamIdChatter, self.steamIdChatRoom, self.ChatMsgType)
        # utf-8 encode only when unicode in py2 and str in py3
        rbytes += (self.text.encode('utf-8') if isinstance(self.text, str) else self.text) + b'\x00'

        return rbytes

    def load(self, data):
        buf = StructReader(data)
        self.steamIdChatter, self.steamIdChatRoom, self.ChatMsgType = buf.unpack("<QQI")
        self.text = buf.read_cstring().decode('utf-8')

    def __str__(self):
        return '\n'.join(["steamIdChatter: %d" % self.steamIdChatter,
                          "steamIdChatRoom: %d" % self.steamIdChatRoom,
                          "ChatMsgType: %d" % self.ChatMsgType,
                          "text: %s" % repr(self.text),
                          ])


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
        return '\n'.join(["steamIdChat: %d" % self.steamIdChat,
                          "type: %r" % self.type,
                          "steamIdUserActedOn: %d" % self.steamIdUserActedOn,
                          "chatAction: %d" % self.chatAction,
                          "steamIdUserActedBy: %d" % self.steamIdUserActedBy
                          ])


class ClientMarketingMessageUpdate2(StructMessage):
    class MarketingMessage:
        id = 0
        url = ''
        flags = 0

    def __init__(self, data):
        super().__init__(data)
        self.time = 0
        self.messages = list()

    def load(self, data):
        buf = StructReader(data)
        self.time, count = buf.unpack("<II")

        for _ in range(count):
            m = self.MarketingMessage()
            self.messages.append(m)

            length, m.id = buf.unpack("<IQ")
            m.url = buf.read_cstring().decode('utf-8')
            m.flags = buf.unpack("<I")

    def __str__(self):
        text = ["time: %s" % self.time,
                "count: %d" % self.count,
                ]

        for m in self.messages:  # emulate Protobuf text format
            text.append("messages " + str(m).replace("\n", "\n    ", 3))

        return '\n'.join(text)

    @property
    def count(self):
        return len(self.messages)


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

        (self.steamIdChat, self.steamIdFriend, self.chatRoomType, self.steamIdOwner,
         self.steamIdClan, self.chatFlags, self.enterResponse, self.numMembers
         ) = buf.unpack("<QQIQQ?II")
        self.chatRoomName = buf.read_cstring().decode('utf-8')

        for _ in range(self.numMembers):
            self.memberList.append(binary_loads(buf.read(64))['MessageObject'])

        self.UNKNOWN1, = buf.unpack("<I")

    def __str__(self):
        return '\n'.join(["steamIdChat: %d" % self.steamIdChat,
                          "steamIdFriend: %d" % self.steamIdFriend,
                          "chatRoomType: %r" % self.chatRoomType,
                          "steamIdOwner: %d" % self.steamIdOwner,
                          "steamIdClan: %d" % self.steamIdClan,
                          "chatFlags: %r" % self.chatFlags,
                          "enterResponse: %r" % self.enterResponse,
                          "numMembers: %r" % self.numMembers,
                          "chatRoomName: %s" % repr(self.chatRoomName),
                          ] + map(lambda x: "memberList: %s" % x, self.memberList))
