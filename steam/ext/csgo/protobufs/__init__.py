from typing import Final

import betterproto

APP_ID: Final = 730

from ....protobufs.msg import GCProtobufMessage
from . import base as base, cstrike as cstrike, econ as econ, sdk as sdk, struct_messages as struct_messages

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
