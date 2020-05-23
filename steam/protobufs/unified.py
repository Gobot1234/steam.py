import re
from typing import TYPE_CHECKING, Optional, Type

from . import (
    steammessages_econ,
    steammessages_chat,
    steammessages_cloud,
    steammessages_video,
    steammessages_player,
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

METHOD_MATCH = re.compile(r'^([a-z]+)\.([a-z]+)?$', re.I)


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


def get_um(method_name: str) -> Optional[Type['Message']]:
    findall = METHOD_MATCH.findall(method_name)
    if not findall:
        return None

    interface, method = findall[0]

    if interface not in service_lookup:
        return None

    return getattr(service_lookup[interface], method)
