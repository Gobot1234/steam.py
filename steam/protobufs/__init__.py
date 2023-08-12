"""
steam.protobufs
~~~~~~~~~~~~~~~
The protobufs for the Steam API.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, TypeAlias, cast

import betterproto

PROTOBUFS: Final = cast("Mapping[EMsg, type[ProtobufMessage | Message]]", {})
RequestType: TypeAlias = "type[UnifiedMessage]"
ResponseType: TypeAlias = "type[UnifiedMessage]"
UMS: Final = cast(Mapping[str, tuple[RequestType, ResponseType]], {})
GC_PROTOBUFS: Final = cast("Mapping[AppID, Mapping[IntEnum, type[GCProtobufMessage | GCMessage]]]", {})

from .emsg import *
from .msg import *

if TYPE_CHECKING:
    from ..enums import IntEnum
    from ..types.id import AppID

__all__ = (
    "EMsg",
    "NoMsg",
    "Message",
    "ProtobufMessage",
    "UnifiedMessage",
    "GCProtobufMessage",
    "GCMessage",
    "PROTOBUFS",
    "UMS",
    "GC_PROTOBUFS",
    "REQUEST_EMSGS",
    "RESPONSE_EMSGS",
    "SERVICE_EMSGS",
)

# NOTE all modules need to be included here otherwise messages won't be parsed correctly
from . import (
    app_info as app_info,
    auth as auth,
    base as base,
    chat as chat,
    clan as clan,
    client_server as client_server,
    client_server_2 as client_server_2,
    cloud as cloud,
    community as community,
    content_manifest as content_manifest,
    content_server as content_server,
    econ as econ,
    encrypted_app_ticket as encrypted_app_ticket,
    friend_messages as friend_messages,
    friends as friends,
    game_servers as game_servers,
    leaderboards as leaderboards,
    login as login,
    loyalty_rewards as loyalty_rewards,
    notifications as notifications,
    parental as parental,
    player as player,
    published_file as published_file,
    quest as quest,
    reviews as reviews,
    store as store,
    two_factor as two_factor,
    ucm as ucm,
    user_news as user_news,
    user_stats as user_stats,
)

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in ProtobufMessage.__subclasses__()]
[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in UnifiedMessage.__subclasses__()]
