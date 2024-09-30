# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: gcsdk_gcmessages.proto
# plugin: python-betterproto

from __future__ import annotations

from dataclasses import dataclass

import betterproto

from ....protobufs.msg import GCProtobufMessage
from ..enums import EMsg


class ESourceEngine(betterproto.Enum):
    Source1 = 0
    Source2 = 1


class PartnerAccountType(betterproto.Enum):
    NONE = 0
    PerfectWorld = 1
    Invalid = 3


class GCConnectionStatus(betterproto.Enum):
    HaveSession = 0
    GcGoingDown = 1
    NoSession = 2
    NoSessionInLogonQueue = 3
    NoSteam = 4
    Suspended = 5
    SteamGoingDown = 6


@dataclass(eq=False, repr=False)
class SOIDOwner(betterproto.Message):
    type: int = betterproto.uint32_field(1)
    id: int = betterproto.uint64_field(2)


@dataclass(eq=False, repr=False)
class SOCacheHaveVersion(betterproto.Message):
    soid: SOIDOwner = betterproto.message_field(1)
    version: float = betterproto.fixed64_field(2)
    service_id: int = betterproto.uint32_field(3)
    cached_file_version: int = betterproto.uint32_field(4)


class ClientHello(GCProtobufMessage, msg=EMsg.ClientHello):
    version: int = betterproto.uint32_field(1)
    socache_have_versions: list[SOCacheHaveVersion] = betterproto.message_field(2)
    client_session_need: int = betterproto.uint32_field(3)
    client_launcher: PartnerAccountType = betterproto.enum_field(4)
    secret_key: str = betterproto.string_field(5)
    client_language: int = betterproto.uint32_field(6)
    engine: ESourceEngine = betterproto.enum_field(7)
    steamdatagram_login: bytes = betterproto.bytes_field(8)
    platform_id: int = betterproto.uint32_field(9)
    game_msg: bytes = betterproto.bytes_field(10)
    os_type: int = betterproto.int32_field(11)
    render_system: int = betterproto.uint32_field(12)
    render_system_req: int = betterproto.uint32_field(13)
    screen_width: int = betterproto.uint32_field(14)
    screen_height: int = betterproto.uint32_field(15)
    screen_refresh: int = betterproto.uint32_field(16)
    render_width: int = betterproto.uint32_field(17)
    render_height: int = betterproto.uint32_field(18)
    swap_width: int = betterproto.uint32_field(19)
    swap_height: int = betterproto.uint32_field(20)
    is_steam_china: bool = betterproto.bool_field(22)
    is_steam_china_client: bool = betterproto.bool_field(24)
    platform_name: str = betterproto.string_field(23)


@dataclass(eq=False, repr=False)
class CExtraMsgBlock(betterproto.Message):
    msg_type: int = betterproto.uint32_field(1)
    contents: bytes = betterproto.bytes_field(2)
    msg_key: int = betterproto.uint64_field(3)
    is_compressed: bool = betterproto.bool_field(4)


@dataclass(eq=False, repr=False)
class ClientWelcomeLocation(betterproto.Message):
    latitude: float = betterproto.float_field(1)
    longitude: float = betterproto.float_field(2)
    country: str = betterproto.string_field(3)


class ConnectionStatus(GCProtobufMessage, msg=EMsg.ClientConnectionStatus):
    status: GCConnectionStatus = betterproto.enum_field(1)
    client_session_need: int = betterproto.uint32_field(2)
    queue_position: int = betterproto.int32_field(3)
    queue_size: int = betterproto.int32_field(4)
    wait_seconds: int = betterproto.int32_field(5)
    estimated_wait_seconds_remaining: int = betterproto.int32_field(6)


@dataclass(eq=False, repr=False)
class SOCacheSubscriptionCheck(betterproto.Message):
    version: float = betterproto.fixed64_field(2)
    owner_soid: SOIDOwner = betterproto.message_field(3)
    service_id: int = betterproto.uint32_field(4)
    service_list: list[int] = betterproto.uint32_field(5)
    sync_version: float = betterproto.fixed64_field(6)


@dataclass(eq=False, repr=False)
class SOCacheSubscribedSubscribedType(betterproto.Message):
    type_id: int = betterproto.int32_field(1)
    object_data: list[bytes] = betterproto.bytes_field(2)


@dataclass(eq=False, repr=False)
class SOCacheSubscribed(betterproto.Message):
    objects: list[SOCacheSubscribedSubscribedType] = betterproto.message_field(2)
    version: float = betterproto.fixed64_field(3)
    owner_soid: SOIDOwner = betterproto.message_field(4)
    service_id: int = betterproto.uint32_field(5)
    service_list: list[int] = betterproto.uint32_field(6)
    sync_version: float = betterproto.fixed64_field(7)


class ClientWelcome(GCProtobufMessage, msg=EMsg.ClientWelcome):
    version: int = betterproto.uint32_field(1)
    game_data: bytes = betterproto.bytes_field(2)
    outofdate_subscribed_caches: list[SOCacheSubscribed] = betterproto.message_field(3)
    uptodate_subscribed_caches: list[SOCacheSubscriptionCheck] = betterproto.message_field(4)
    location: ClientWelcomeLocation = betterproto.message_field(5)
    save_game_key: bytes = betterproto.bytes_field(6)
    gc_socache_file_version: int = betterproto.uint32_field(9)
    txn_country_code: str = betterproto.string_field(10)
    game_data2: bytes = betterproto.bytes_field(11)
    rtime32_gc_welcome_timestamp: int = betterproto.uint32_field(12)
    currency: int = betterproto.uint32_field(13)
    balance: int = betterproto.uint32_field(14)
    balance_url: str = betterproto.string_field(15)
    has_accepted_china_ssa: bool = betterproto.bool_field(16)
    is_banned_steam_china: bool = betterproto.bool_field(17)
    additional_welcome_msgs: CExtraMsgBlock = betterproto.message_field(18)
    # steam_learn_server_info: SteamLearnServerInfo = betterproto.message_field(20) # steam nonsense