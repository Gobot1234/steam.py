"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import betterproto

from .._const import READ_U32
from ..enums import Result

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = (
    "MessageHeader",
    "ProtobufMessageHeader",
    "GCMessageHeader",
)


# lifted from base.py to avoid import issues
@dataclass(eq=False, repr=False, slots=True)
class CMsgProtoBufHeader(betterproto.Message):
    steam_id: int = betterproto.fixed64_field(1)
    session_id: int = betterproto.int32_field(2)
    routing_app_id: int = betterproto.uint32_field(3)
    job_id_source: int = betterproto.fixed64_field(10)
    job_id_target: int = betterproto.fixed64_field(11)
    job_name_target: str = betterproto.string_field(12)
    seq_num: int = betterproto.int32_field(24)
    eresult: int = betterproto.int32_field(13)
    error_message: str = betterproto.string_field(14)
    auth_account_flags: int = betterproto.uint32_field(16)
    token_source: int = betterproto.uint32_field(22)
    admin_spoofing_user: bool = betterproto.bool_field(23)
    transport_error: int = betterproto.int32_field(17)
    message_id: int = betterproto.uint64_field(18)
    publisher_group_id: int = betterproto.uint32_field(19)
    sys_id: int = betterproto.uint32_field(20)
    trace_tag: int = betterproto.uint64_field(21)
    webapi_key_id: int = betterproto.uint32_field(25)
    is_from_external_source: bool = betterproto.bool_field(26)
    forward_to_sys_id: list[int] = betterproto.uint32_field(27)
    cm_sys_id: int = betterproto.uint32_field(28)
    wg_token: str = betterproto.string_field(30)
    launcher_type: int = betterproto.uint32_field(31)
    realm: int = betterproto.uint32_field(32)
    ip: int = betterproto.uint32_field(15, group="ip_addr")
    ip_v6: bytes = betterproto.bytes_field(29, group="ip_addr")


class MessageHeader:
    __slots__ = (
        "job_name_target",
        "header_size",
        "header_version",
        "job_id_target",
        "job_id_source",
        "header_canary",
        "steam_id",
        "session_id",
    )

    STRUCT: Final = struct.Struct("<BHqqBqi")
    eresult: Final = Result.Invalid
    length: Final = STRUCT.size

    def __init__(self):
        self.header_size = 36
        self.header_version = 2
        self.job_name_target = None
        self.job_id_target = 0
        self.job_id_source = 0
        self.header_canary = 239
        self.steam_id = -1
        self.session_id = -1

    def __repr__(self) -> str:
        attrs = (
            "header_size",
            "header_version",
            "job_id_target",
            "job_id_source",
            "header_canary",
            "steam_id",
            "session_id",
        )
        return f"<{self.__class__.__name__} {' '.join(f'{attr}={getattr(self, attr)!r}' for attr in attrs)}>"

    def parse(self, data: bytes) -> Self:
        (
            self.header_size,
            self.header_version,
            self.job_id_target,
            self.job_id_source,
            self.header_canary,
            self.steam_id,
            self.session_id,
        ) = self.STRUCT.unpack_from(data)
        return self

    def __bytes__(self) -> bytes:
        return self.STRUCT.pack(
            self.header_size,
            self.header_version,
            self.job_id_target,
            self.job_id_source,
            self.header_canary,
            self.steam_id,
            self.session_id,
        )


@dataclass(eq=False, repr=False, slots=True)
class ProtobufMessageHeader(CMsgProtoBufHeader):
    length: int = 0
    STRUCT: Final = struct.Struct("<I")

    def parse(self, data: bytes) -> Self:
        self.length = READ_U32(data) + 4
        return betterproto.Message.parse(self, data[4 : self.length])  # type: ignore

    def __bytes__(self) -> bytes:
        proto_data = betterproto.Message.__bytes__(self)
        return self.STRUCT.pack(len(proto_data)) + proto_data


del ProtobufMessageHeader.__dataclass_fields__["length"]  # hack to get betterproto to ignore this
del ProtobufMessageHeader.__dataclass_fields__["STRUCT"]


class GCMessageHeader:
    __slots__ = ("header_version", "job_id_target", "job_id_source")

    STRUCT: Final = struct.Struct("<Hqq")
    PACK: Final = ()
    steam_id: Final = -1
    session_id: Final = -1
    eresult: Final = Result.Invalid
    length: Final = STRUCT.size
    job_name_target: Final = None

    def __init__(self):
        self.header_version = 1
        self.job_id_target = -1
        self.job_id_source = 0

    def __repr__(self) -> str:
        attrs = (
            "header_version",
            "job_id_target",
            "job_id_source",
        )
        return f"<{self.__class__.__name__} {' '.join(f'{attr}={getattr(self, attr)!r}' for attr in attrs)}>"

    # special cases
    def __bytes__(self) -> bytes:
        return self.STRUCT.pack(self.header_version, self.job_id_target, self.job_id_source)

    def parse(self, data: bytes) -> Self:
        (
            self.header_version,
            self.job_id_target,
            self.job_id_source,
        ) = self.STRUCT.unpack_from(data)
        return self
