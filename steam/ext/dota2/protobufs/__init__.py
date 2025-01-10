from typing import Final

import betterproto

APP_ID: Final = 570

from ....protobufs.msg import GCProtobufMessage
from . import (
    client_messages as client_messages,
    common as common,
    sdk as sdk,
    watch as watch,
)

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
