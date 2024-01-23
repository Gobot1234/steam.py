from typing import Final

import betterproto

APP_ID: Final = 570

from ....protobufs.msg import GCProtobufMessage
from . import dota_gcmessages_client_watch as dota_gcmessages_client_watch
from . import gcsdk_gcmessages as gcsdk_gcmessages

[setattr(cls, "_betterproto", betterproto.ProtoClassMetadata(cls)) for cls in GCProtobufMessage.__subclasses__()]
