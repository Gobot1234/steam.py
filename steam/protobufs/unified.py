import re

from . import (
    steammessages_econ_pb2,
    steammessages_chat_pb2,
    steammessages_cloud_pb2,
    steammessages_store_pb2,
    steammessages_video_pb2,
    steammessages_player_pb2,
    steammessages_shader_pb2,
    steammessages_offline_pb2,
    steammessages_secrets_pb2,
    steammessages_parental_pb2,
    steammessages_broadcast_pb2,
    steammessages_inventory_pb2,
    steammessages_twofactor_pb2,
    steammessages_deviceauth_pb2,
    steammessages_linkfilter_pb2,
    steammessages_credentials_pb2,
    steammessages_gameservers_pb2,
    steammessages_partnerapps_pb2,
    steammessages_useraccount_pb2,
    steammessages_depotbuilder_pb2,
    steammessages_site_license_pb2,
    steammessages_datapublisher_pb2,
    steammessages_physicalgoods_pb2,
    steammessages_publishedfile_pb2,
    steammessages_webui_friends_pb2,
    steammessages_friendmessages_pb2,
    steammessages_gamenotifications_pb2,
)

service_lookup = {
    'Broadcast': steammessages_broadcast_pb2,
    'BroadcastClient': steammessages_broadcast_pb2,
    'Chat': steammessages_chat_pb2,
    'ChatRoom': steammessages_chat_pb2,
    'ChatRoomClient': steammessages_chat_pb2,
    'ChatUsability': steammessages_chat_pb2,
    'ChatUsabilityClient': steammessages_chat_pb2,
    'ClanChatRooms': steammessages_chat_pb2,
    'Cloud': steammessages_cloud_pb2,
    'Credentials': steammessages_credentials_pb2,
    'DataPublisher': steammessages_datapublisher_pb2,
    'ValveHWSurvey': steammessages_datapublisher_pb2,
    'ContentBuilder': steammessages_depotbuilder_pb2,
    'DeviceAuth': steammessages_deviceauth_pb2,
    'Econ': steammessages_econ_pb2,
    'FriendMessages': steammessages_friendmessages_pb2,
    'FriendMessagesClient': steammessages_friendmessages_pb2,
    'GameNotifications': steammessages_gamenotifications_pb2,
    'GameNotificationsClient': steammessages_gamenotifications_pb2,
    'GameServers': steammessages_gameservers_pb2,
    'Inventory': steammessages_inventory_pb2,
    'InventoryClient': steammessages_inventory_pb2,
    'CommunityLinkFilter': steammessages_linkfilter_pb2,
    'Offline': steammessages_offline_pb2,
    'Parental': steammessages_parental_pb2,
    'PartnerApps': steammessages_partnerapps_pb2,
    'PhysicalGoods': steammessages_physicalgoods_pb2,
    'Player': steammessages_player_pb2,
    'PlayerClient': steammessages_player_pb2,
    'PublishedFile': steammessages_publishedfile_pb2,
    'PublishedFileClient': steammessages_publishedfile_pb2,
    'Secrets': steammessages_secrets_pb2,
    'Shader': steammessages_shader_pb2,
    'SiteLicense': steammessages_site_license_pb2,
    'SiteManagerClient': steammessages_site_license_pb2,
    'Store': steammessages_store_pb2,
    'StoreClient': steammessages_store_pb2,
    'TwoFactor': steammessages_twofactor_pb2,
    'AccountLinking': steammessages_useraccount_pb2,
    'EmbeddedClient': steammessages_useraccount_pb2,
    'UserAccount': steammessages_useraccount_pb2,
    'FovasVideo': steammessages_video_pb2,
    'Video': steammessages_video_pb2,
    'VideoClient': steammessages_video_pb2,
    'Clan': steammessages_webui_friends_pb2,
    'Community': steammessages_webui_friends_pb2,
    'ExperimentService': steammessages_webui_friends_pb2,
    'FriendsList': steammessages_webui_friends_pb2,
    'FriendsListClient': steammessages_webui_friends_pb2,
    'SteamTV': steammessages_webui_friends_pb2,
    'VoiceChat': steammessages_webui_friends_pb2,
    'VoiceChatClient': steammessages_webui_friends_pb2,
    'WebRTCClient': steammessages_webui_friends_pb2,
    'WebRTCClientNotifications': steammessages_webui_friends_pb2,
}

method_lookup = {}


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

        package = service_lookup[interface]

        service = getattr(package, interface, None)
        if service is None:
            return None

        for method_desc in service.GetDescriptor().methods:
            name = f"{interface}.{method_desc.name}#1"

            method_lookup[(name, False)] = getattr(package, method_desc.input_type.full_name, None)
            method_lookup[(name, True)] = getattr(package, method_desc.output_type.full_name, None)

    return method_lookup[key]
