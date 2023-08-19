from typing import Final

import betterproto

APP_ID: Final = 440

from ....protobufs.msg import GCProtobufMessage
from . import (
    base as base,
    econ as econ,
    sdk as sdk,
    struct_messages as struct_messages,
    system_messages as system_messages,
    tf as tf,
)

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
