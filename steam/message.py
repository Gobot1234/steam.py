'''import fnmatch
import re
import struct
from importlib import import_module'''

from .abc import Messageable

'''from .enums import EMsg
from .utils import proto_fill_from_dict, set_proto_bit, clear_proto_bit
from .protobufs import steammessages_base_pb2, steammessages_clientserver_pb2, steammessages_clientserver_2_pb2, \
                       steammessages_clientserver_friends_pb2, steammessages_clientserver_login_pb2
'''


class Message(Messageable):

    async def _get_channel(self):
        pass

    def __init__(self):
        pass

    def __repr__(self):
        return '<author={0.author!r} flags={0.flags}>'.format(self)

    @property
    def author(self):
        pass

    @property
    def content(self):
        pass

    @property
    def time_created_at(self):
        pass


'''
def send_um(self, method_name, params=None):
    """Send service method request
    :param method_name: method name (e.g. ``Player.GetGameBadgeLevels#1``)
    :type  method_name: :class:`str`
    :param params: message parameters
    :type  params: :class:`dict`
    :return: ``job_id`` identifier
    :rtype: :class:`str`
    Listen for ``jobid`` on this object to catch the response.
    """
    proto = get_um(method_name)

    if proto is None:
        raise ValueError("Failed to find method named: %s" % method_name)

    message = MsgProto(EMsg.ServiceMethodCallFromClient)
    message.header.target_job_name = method_name
    message.body = proto()

    if params:
        proto_fill_from_dict(message.body, params)

    return self.send_job(message)


def get_um(method_name, response=False):
    """Get protobuf for given method name
    :param method_name: full method name (e.g. ``Player.GetGameBadgeLevels#1``)
    :type method_name: :class:`str`
    :param response: whether to return proto for response or request
    :type response: :class:`bool`
    :return: protobuf message
    """
    key = (method_name, response)

    if key not in method_lookup:
        match = re.findall(r'^([a-z]+)\.([a-z]+)#(\d)?$', method_name, re.I)
        if not match:
            return None

        interface, method, version = match[0]

        if interface not in service_lookup:
            return None

        package = import_module(service_lookup[interface])

        service = getattr(package, interface, None)
        if service is None:
            return None

        for method_desc in service.GetDescriptor().methods:
            name = "%s.%s#%d" % (interface, method_desc.name, 1)

            method_lookup[(name, False)] = getattr(package, method_desc.input_type.full_name, None)
            method_lookup[(name, True)] = getattr(package, method_desc.output_type.full_name, None)

    return method_lookup[key]


service_lookup = {
    'Broadcast': 'steam.protobufs.steammessages_broadcast_pb2',
    'BroadcastClient': 'steam.protobufs.steammessages_broadcast_pb2',
    'Chat': 'steam.protobufs.steammessages_chat_pb2',
    'ChatRoom': 'steam.protobufs.steammessages_chat_pb2',
    'ChatRoomClient': 'steam.protobufs.steammessages_chat_pb2',
    'ChatUsability': 'steam.protobufs.steammessages_chat_pb2',
    'ChatUsabilityClient': 'steam.protobufs.steammessages_chat_pb2',
    'ClanChatRooms': 'steam.protobufs.steammessages_chat_pb2',
    'Cloud': 'steam.protobufs.steammessages_cloud_pb2',
    'Credentials': 'steam.protobufs.steammessages_credentials_pb2',
    'DataPublisher': 'steam.protobufs.steammessages_datapublisher_pb2',
    'ValveHWSurvey': 'steam.protobufs.steammessages_datapublisher_pb2',
    'ContentBuilder': 'steam.protobufs.steammessages_depotbuilder_pb2',
    'DeviceAuth': 'steam.protobufs.steammessages_deviceauth_pb2',
    'Econ': 'steam.protobufs.steammessages_econ_pb2',
    'FriendMessages': 'steam.protobufs.steammessages_friendmessages_pb2',
    'FriendMessagesClient': 'steam.protobufs.steammessages_friendmessages_pb2',
    'GameNotifications': 'steam.protobufs.steammessages_gamenotifications_pb2',
    'GameNotificationsClient': 'steam.protobufs.steammessages_gamenotifications_pb2',
    'GameServers': 'steam.protobufs.steammessages_gameservers_pb2',
    'Inventory': 'steam.protobufs.steammessages_inventory_pb2',
    'InventoryClient': 'steam.protobufs.steammessages_inventory_pb2',
    'CommunityLinkFilter': 'steam.protobufs.steammessages_linkfilter_pb2',
    'Offline': 'steam.protobufs.steammessages_offline_pb2',
    'Parental': 'steam.protobufs.steammessages_parental_pb2',
    'PartnerApps': 'steam.protobufs.steammessages_partnerapps_pb2',
    'PhysicalGoods': 'steam.protobufs.steammessages_physicalgoods_pb2',
    'Player': 'steam.protobufs.steammessages_player_pb2',
    'PlayerClient': 'steam.protobufs.steammessages_player_pb2',
    'PublishedFile': 'steam.protobufs.steammessages_publishedfile_pb2',
    'PublishedFileClient': 'steam.protobufs.steammessages_publishedfile_pb2',
    'Secrets': 'steam.protobufs.steammessages_secrets_pb2',
    'Shader': 'steam.protobufs.steammessages_shader_pb2',
    'SiteLicense': 'steam.protobufs.steammessages_site_license_pb2',
    'SiteManagerClient': 'steam.protobufs.steammessages_site_license_pb2',
    'Store': 'steam.protobufs.steammessages_store_pb2',
    'TwoFactor': 'steam.protobufs.steammessages_twofactor_pb2',
    'AccountLinking': 'steam.protobufs.steammessages_useraccount_pb2',
    'EmbeddedClient': 'steam.protobufs.steammessages_useraccount_pb2',
    'UserAccount': 'steam.protobufs.steammessages_useraccount_pb2',
    'FovasVideo': 'steam.protobufs.steammessages_video_pb2',
    'Video': 'steam.protobufs.steammessages_video_pb2',
    'VideoClient': 'steam.protobufs.steammessages_video_pb2',
    'Clan': 'steam.protobufs.steammessages_webui_friends_pb2',
    'Community': 'steam.protobufs.steammessages_webui_friends_pb2',
    'ExperimentService': 'steam.protobufs.steammessages_webui_friends_pb2',
    'FriendsList': 'steam.protobufs.steammessages_webui_friends_pb2',
    'FriendsListClient': 'steam.protobufs.steammessages_webui_friends_pb2',
    'SteamTV': 'steam.protobufs.steammessages_webui_friends_pb2',
    'VoiceChat': 'steam.protobufs.steammessages_webui_friends_pb2',
    'VoiceChatClient': 'steam.protobufs.steammessages_webui_friends_pb2',
    'WebRTCClient': 'steam.protobufs.steammessages_webui_friends_pb2',
    'WebRTCClientNotifications': 'steam.protobufs.steammessages_webui_friends_pb2',
}

method_lookup = {}
cmsg_lookup = {}

for proto_module in [steammessages_clientserver_pb2, steammessages_clientserver_2_pb2,
                     steammessages_clientserver_friends_pb2, steammessages_clientserver_login_pb2]:
    cmsg_list = proto_module.__dict__
    cmsg_list = fnmatch.filter(cmsg_list, 'CMsg*')
    cmsg_lookup.update(
        dict(zip(map(lambda cmsg_name: cmsg_name.lower(), cmsg_list),
                 map(lambda cmsg_name: getattr(proto_module, cmsg_name), cmsg_list)
                 ))
    )

cmsg_lookup_predefined = {
    EMsg.Multi: steammessages_base_pb2.CMsgMulti,
    EMsg.ClientToGC: steammessages_clientserver_2_pb2.CMsgGCClient,
    EMsg.ClientFromGC: steammessages_clientserver_2_pb2.CMsgGCClient,
    EMsg.ClientServiceMethod: steammessages_clientserver_2_pb2.CMsgClientServiceMethodLegacy,
    EMsg.ClientServiceMethodResponse: steammessages_clientserver_2_pb2.CMsgClientServiceMethodLegacyResponse,
    EMsg.ClientGetNumberOfCurrentPlayersDP: steammessages_clientserver_2_pb2.CMsgDPGetNumberOfCurrentPlayers,
    EMsg.ClientGetNumberOfCurrentPlayersDPResponse: steammessages_clientserver_2_pb2.CMsgDPGetNumberOfCurrentPlayersResponse,
    EMsg.ClientLogonGameServer: steammessages_clientserver_login_pb2.CMsgClientLogon,
    EMsg.ClientCurrentUIMode: steammessages_clientserver_2_pb2.CMsgClientUIMode,
    EMsg.ClientChatOfflineMessageNotification: steammessages_clientserver_2_pb2.CMsgClientOfflineMessageNotification,
}


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


class MsgHdrProtoBuf:
    _size = _fullsize = struct.calcsize("<II")
    msg = EMsg.Invalid

    def __init__(self, data=None):
        self.proto = steammessages_base_pb2.CMsgProtoBufHeader()

        if data:
            self.load(data)

    def serialize(self):
        proto_data = self.proto.SerializeToString()
        return struct.pack("<II", set_proto_bit(self.msg), len(proto_data)) + proto_data

    def load(self, data):
        msg, proto_length = struct.unpack_from("<II", data)

        self.msg = EMsg(clear_proto_bit(msg))
        size = MsgHdrProtoBuf._size
        self._fullsize = size + proto_length
        self.proto.ParseFromString(data[size:self._fullsize])


class MsgProto(object):

    def __init__(self, msg, data=None, parse=True):
        self._header = MsgHdrProtoBuf(data)
        self.header = self._header.proto
        self._msg = msg
        self.proto = True
        self.body = None  #: protobuf message instance
        self.payload = None  #: Will contain body payload, if we fail to find correct proto message

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
        return EMsg(self._header.msg)

    def serialize(self):
        return self._header.serialize() + self.body.SerializeToString()

    @property
    def steamID(self):
        return self.header.steamid

    @property
    def sessionID(self):
        return self.header.client_sessionid
'''
