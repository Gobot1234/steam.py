import re
from typing import TYPE_CHECKING, Optional

from . import (
    steammessages_econ,
    steammessages_chat,
    steammessages_cloud,
    steammessages_video,
    steammessages_player,
    steammessages_secrets,
    steammessages_parental,
    steammessages_broadcast,
    steammessages_inventory,
    steammessages_twofactor,
    steammessages_credentials,
    steammessages_gameservers,
    steammessages_useraccount,
    steammessages_webui_friends,
    steammessages_friendmessages,
    steammessages_gamenotifications,
)

if TYPE_CHECKING:
    from betterproto import Message

service_lookup = {
    'Broadcast': steammessages_broadcast,
    'BroadcastClient': steammessages_broadcast,
    'Chat': steammessages_chat,
    'ChatRoom': steammessages_chat,
    'ChatRoomClient': steammessages_chat,
    'ChatUsability': steammessages_chat,
    'ChatUsabilityClient': steammessages_chat,
    'ClanChatRooms': steammessages_chat,
    'Cloud': steammessages_cloud,
    'Credentials': steammessages_credentials,
    'Econ': steammessages_econ,
    'FriendMessages': steammessages_friendmessages,
    'FriendMessagesClient': steammessages_friendmessages,
    'GameNotifications': steammessages_gamenotifications,
    'GameNotificationsClient': steammessages_gamenotifications,
    'GameServers': steammessages_gameservers,
    'Inventory': steammessages_inventory,
    'InventoryClient': steammessages_inventory,
    'Parental': steammessages_parental,
    'Player': steammessages_player,
    'PlayerClient': steammessages_player,
    'Secrets': steammessages_secrets,
    'TwoFactor': steammessages_twofactor,
    'AccountLinking': steammessages_useraccount,
    'EmbeddedClient': steammessages_useraccount,
    'UserAccount': steammessages_useraccount,
    'FovasVideo': steammessages_video,
    'Video': steammessages_video,
    'VideoClient': steammessages_video,
    'Clan': steammessages_webui_friends,
    'Community': steammessages_webui_friends,
    'ExperimentService': steammessages_webui_friends,
    'FriendsList': steammessages_webui_friends,
    'FriendsListClient': steammessages_webui_friends,
    'SteamTV': steammessages_webui_friends,
    'VoiceChat': steammessages_webui_friends,
    'VoiceChatClient': steammessages_webui_friends,
    'WebRTCClient': steammessages_webui_friends,
    'WebRTCClientNotifications': steammessages_webui_friends,
}

method_lookup = {}


def get_um(method_name: str, response: bool = False) -> Optional['Message']:
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
