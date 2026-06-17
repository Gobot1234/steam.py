from typing import Final

import betterproto

APP_ID: Final = 1422450

from ....protobufs.msg import GCProtobufMessage
from . import (
    client_messages as client_messages,
    common as common,
    sdk as sdk,
)

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
