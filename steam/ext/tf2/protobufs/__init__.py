from typing import Final

import betterproto

APP_ID: Final = 440

from ....protobufs.msg import GCProtobufMessage
from . import base as base, sdk as sdk, struct_messages as struct_messages

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
