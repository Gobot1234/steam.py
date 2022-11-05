"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import logging
import struct
import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Final, TypeVar, get_type_hints

import betterproto
from typing_extensions import Self, dataclass_transform

from .._const import MISSING, SET_PROTO_BIT
from ..enums import IntEnum, Result
from ..types.id import AppID
from ..utils import classproperty
from . import GC_PROTOBUFS, PROTOBUFS, UMS
from .emsg import *
from .headers import *
from .headers import MessageHeader
from .struct_messages import StructMessage

if TYPE_CHECKING:
    from ..types.id import AppID

log = logging.getLogger(__name__)
WRITE_U32: Callable[[int], bytes] = struct.Struct("<I").pack

__all__ = (
    "Message",
    "ProtobufMessage",
    "UnifiedMessage",
    "GCMessage",
    "GCProtobufMessage",
)

TT = TypeVar("TT", bound=type[object])


def load_annotations(cls: TT) -> TT:
    """Needed so dataclasses don't break when evaluating ForwardRefs"""
    cls.__annotations__ = get_type_hints(cls)
    return cls


class NoMsg(IntEnum):
    NONE = -2


@load_annotations
class MessageBase:
    __slots__ = ()

    MSG: ClassVar[IntEnum] = NoMsg.NONE
    header: MessageHeader | ProtobufMessageHeader | GCMessageHeader

    def __init_subclass__(cls, **kwargs: Any) -> object:
        if cls.__module__ == __name__:
            return load_annotations(cls)

        if keys := cls.__annotations__.keys() & {"header", "result", "parse", "MSG", "UM_NAME", "APP_ID"}:
            raise TypeError(f"{', '.join(keys)} is/are a reserved field name(s)")

        return dataclass(**({"repr": False, "eq": False} | kwargs))(cls)

    @property
    def result(self) -> Result:
        return Result.try_value(getattr(self, "eresult", 0) or self.header.eresult)

    if not TYPE_CHECKING:
        # shim to make betterproto's repr work
        @classproperty
        def __dataclass_fields__(cls: type[Self], value: MappingProxyType[Any, Any] = MappingProxyType({})) -> Any:
            return value

        @classproperty
        def __dataclass_params__(cls: type[Self], value=dataclasses.make_dataclass("", ()).__dataclass_params__) -> Any:
            return value


@load_annotations
class MessageMessageBase:
    __slots__ = ()

    MSG: ClassVar[EMsg]

    def __init_subclass__(cls, msg: EMsg = MISSING, **kwargs: bool) -> object:
        if cls.__module__ == __name__:
            return super().__init_subclass__(**kwargs)

        if msg is MISSING:
            # should be a dataclass with added slots (it recreates the class so the kwarg is removed)
            try:
                msg = cls.MSG
            except AttributeError:
                raise TypeError(
                    "MessageMessageBase.__init_subclass__() missing 1 required positional argument: 'msg'"
                ) from None
        cls.MSG = msg
        PROTOBUFS[msg] = cls  # type: ignore
        return super().__init_subclass__(**kwargs)


@dataclass_transform()
class Message(MessageMessageBase, StructMessage, MessageBase):
    __slots__ = ("header",)

    def __init__(self, **kwargs: Any):
        self.header: MessageHeader = MessageHeader()
        super().__init__(**kwargs)

    def __init_subclass__(cls, msg: EMsg = MISSING, **kwargs: bool) -> object:
        return super().__init_subclass__(msg, repr=True, eq=True, **kwargs)

    def __bytes__(self) -> bytes:
        return WRITE_U32(SET_PROTO_BIT(self.__class__.MSG)) + bytes(self.header) + super().__bytes__()

    def parse(self, data: bytes, msg: int = MISSING) -> Self:
        if msg is MISSING:  # case CMsgMulti().parse(data)
            return StructMessage.parse(self, data)

        try:
            new_class: type[Self] = PROTOBUFS[msg]  # type: ignore
        except KeyError:
            log.debug(f"Received an unknown {EMsg(msg)!r} (%s)", data)
            return self

        self.header.parse(data)
        self.__class__ = new_class
        return StructMessage.parse(self, data[self.header.length :])


class ProtobufWrappedMessage(MessageBase, betterproto.Message):
    __slots__ = ()
    header: ProtobufMessageHeader

    def __post_init__(self) -> None:
        self.header = ProtobufMessageHeader(job_name_target=getattr(self.__class__, "UM_NAME", ""))
        return super().__post_init__()

    def __bytes__(self) -> bytes:
        return WRITE_U32(SET_PROTO_BIT(self.__class__.MSG)) + bytes(self.header) + betterproto.Message.__bytes__(self)


REQUEST_EMSGS: Final = frozenset(
    {EMsg.ServiceMethod, EMsg.ServiceMethodCallFromClient, EMsg.ServiceMethodCallFromClientNonAuthed}
)
RESPONSE_EMSGS: Final = frozenset({EMsg.ServiceMethodResponse, EMsg.ServiceMethodSendToClient})
SERVICE_EMSGS: Final = frozenset({*REQUEST_EMSGS, *RESPONSE_EMSGS})


@dataclass_transform()
class ProtobufMessage(MessageMessageBase, ProtobufWrappedMessage):
    def __init__(self, **kwargs: Any) -> None:
        self.header = ProtobufMessageHeader()
        super().__init__(**kwargs)
        self.__post_init__()

    def parse(self, data: bytes, msg: int = MISSING) -> Self:
        if msg is MISSING:  # case CMsgMulti().parse(data)
            return betterproto.Message.parse(self, data)

        self.header.parse(data)
        if msg in SERVICE_EMSGS:
            try:
                new_class = UMS[self.header.job_name_target][msg in RESPONSE_EMSGS]
            except KeyError:
                log.debug(f"Received an unknown UM {self.header.job_name_target} (%s)", data)
                return self
        else:
            try:
                new_class: type[Self] = PROTOBUFS[msg]  # type: ignore  # save the extra lookup when casting to EMsg
            except KeyError:
                log.debug(f"Received an unknown {EMsg(msg)!r} (%s)", data)
                return self

        try:
            self.__class__ = new_class
        except TypeError:
            # setting to MISSING
            log.info(f"Received an unknown {EMsg(msg)!r} %r (%s)", data, self.header.job_name_target)
            return self
        return betterproto.Message.parse(self, data[self.header.length :])  # type: ignore


@dataclass_transform()
class UnifiedMessage(ProtobufMessage):
    UM_NAME: ClassVar[str]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.header = ProtobufMessageHeader(job_name_target=self.__class__.UM_NAME)

    def __init_subclass__(cls, um_name: str, msg: EMsg = MISSING) -> None:
        cls.UM_NAME = sys.intern(f"{um_name}#1")

        if msg is MISSING:
            msg = (
                EMsg.ServiceMethodCallFromClient
                if cls.__name__.endswith(("Request", "Notification"))
                else EMsg.ServiceMethodSendToClient
            )

        try:
            um = UMS[cls.UM_NAME]
        except KeyError:
            UMS[cls.UM_NAME] = um = (MISSING, MISSING)  # type: ignore

        UMS[cls.UM_NAME] = (cls, um[1]) if msg in REQUEST_EMSGS else (um[0], cls)  # type: ignore

        super().__init_subclass__(msg)


@functools.lru_cache()
def get_app_id(module: str) -> AppID:
    gc_protobuf_locations, _, _ = module.rpartition(".")
    protobufs_module = importlib.import_module(gc_protobuf_locations)
    return protobufs_module.APP_ID


class GCMessageBase:
    __slots__ = ()

    if TYPE_CHECKING:
        APP_ID: ClassVar[int]
        MSG: ClassVar[int]

    def __init_subclass__(cls, msg: IntEnum = MISSING) -> None:
        if cls.__module__ == __name__:
            return super().__init_subclass__()

        if msg is MISSING:
            raise TypeError("GCMessageBase.__init_subclass__() missing 1 required positional argument: 'msg'")

        cls.APP_ID = get_app_id(cls.__module__)
        try:
            GC_PROTOBUFS[cls.APP_ID][msg] = cls  # type: ignore
        except KeyError:
            GC_PROTOBUFS[cls.APP_ID] = {msg: cls}  # type: ignore
        super().__init_subclass__()
        cls.MSG = msg


@dataclass_transform()
class GCMessage(GCMessageBase, StructMessage, MessageBase):
    """A wrapper around received GC messages, mainly for extensions."""

    __slots__ = ("header",)
    header: GCMessageHeader

    def __init__(self, **kwargs: Any):
        self.header = GCMessageHeader()
        super().__init__(**kwargs)

    def __bytes__(self) -> bytes:
        return bytes(self.header) + super().__bytes__()

    def parse(self, data: bytes, msg: int = MISSING) -> Self:
        if msg is MISSING:  # case CMsgMulti().parse(data)
            return StructMessage.parse(self, data)

        cls = self.__class__
        try:
            new_class: type[Self] = GC_PROTOBUFS[cls.APP_ID][msg]  # type: ignore  # save the extra lookup when casting to IntEnum
        except KeyError:
            log.debug(f"Received an unknown Language {msg!r} (%s)", data)
            return self

        self.header = GCMessageHeader().parse(data)
        self.__class__ = new_class
        return StructMessage.parse(self, data)


@dataclass_transform()
class GCProtobufMessage(GCMessageBase, ProtobufWrappedMessage):
    """A wrapper around received GC protobuf messages, mainly for extensions."""

    __slots__ = ("header",)

    def __init__(self, **kwargs: Any):
        self.header = ProtobufMessageHeader()
        super().__init__(**kwargs)

    def parse(self, data: bytes, msg: int = MISSING) -> Self:
        if msg is MISSING:  # case CMsgMulti().parse(data)
            return betterproto.Message.parse(self, data)

        cls = self.__class__
        try:
            new_class: type[Self] = GC_PROTOBUFS[cls.APP_ID][msg]  # type: ignore  # save the extra lookup when casting to IntEnum
        except KeyError:
            log.debug(f"Received an unknown Language {msg!r} {cls.APP_ID} (%s)", data)
            return self

        self.header = ProtobufMessageHeader().parse(data)
        # ideally this'd be a __class__ assignment but that doesn't work here
        self.__class__ = new_class
        return betterproto.Message.parse(self, data[self.header.length :])
