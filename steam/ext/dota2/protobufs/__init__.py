from typing import Final

import betterproto

APP_ID: Final = 570

from ....protobufs.msg import GCProtobufMessage
from . import (
    client_messages as client_messages,
    common as common,
    lobby as lobby,
    sdk as sdk,
    shared_enums as shared_enums,
    watch as watch,
)

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
