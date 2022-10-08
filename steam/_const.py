"""
Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import builtins
import struct
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import TYPE_CHECKING, Any, Final, Literal, cast, final

from multidict import MultiDict
from yarl import URL as _URL

from .types.vdf import BinaryVDFDict, VDFDict

if TYPE_CHECKING:
    from .state import ConnectionState

DOCS_BUILDING: bool = getattr(builtins, "__sphinx__", False)


try:
    import orjson
except ModuleNotFoundError:
    import json

    JSON_LOADS: Final = json.loads

    def dumps(
        obj: Any,
        __func: Callable[..., str] = json.dumps,
        /,
    ) -> str:
        return __func(obj, separators=(",", ":"), ensure_ascii=True)

    JSON_DUMPS: Final = cast(Callable[[Any], str], dumps)
else:
    JSON_LOADS: Final[Callable[[str | bytes], Any]] = orjson.loads

    def dumps(
        obj: Any,
        __func: Callable[[Any], bytes] = orjson.dumps,
        __decoder: Callable[[bytes], str] = bytes.decode,
        /,
    ) -> str:
        return __decoder(__func(obj))

    JSON_DUMPS: Final = cast(Callable[[Any], str], dumps)


try:
    import orvdf
except ModuleNotFoundError:
    import vdf

    def loads(
        s: str,
        __func: Callable[..., Any] = vdf.parse,
        __mapper: type[MultiDict[Any]] = MultiDict,
        __string_io: type[StringIO] = StringIO,
        /,
    ) -> VDFDict:
        return __func(__string_io(s), mapper=__mapper)

    def binary_loads(
        s: bytes,
        __func: Callable[..., Any] = vdf.binary_load,
        __mapper: type[MultiDict[Any]] = MultiDict,
        __bytes_io: type[BytesIO] = BytesIO,
        /,
    ) -> BinaryVDFDict:
        return __func(__bytes_io(s), mapper=__mapper)

    VDF_LOADS: Final = cast(Callable[[str], VDFDict], loads)
    VDF_BINARY_LOADS: Final = cast(Callable[[bytes], BinaryVDFDict], binary_loads)

else:
    VDF_LOADS: Final[Callable[[str], VDFDict]] = orvdf.loads
    VDF_BINARY_LOADS: Final[Callable[[bytes], BinaryVDFDict]] = orvdf.binary_loads


try:
    import lxml
except ModuleNotFoundError:
    HTML_PARSER: Final = "html.parser"
else:
    HTML_PARSER: Final = "lxml-xml"


UNIX_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
STEAM_EPOCH = datetime(2003, 1, 1, tzinfo=timezone.utc)


def READ_U32(s: bytes, unpacker: Callable[[bytes], tuple[int]] = struct.Struct("<I").unpack_from, /) -> int:
    (u32,) = unpacker(s)
    return u32


_PROTOBUF_MASK = 0x80000000
# inlined as these are some of the most called functions in the library
IS_PROTO: Final[Callable[[int], bool]] = _PROTOBUF_MASK.__and__  # type: ignore  # this is boolean like for a bit of extra speed
SET_PROTO_BIT: Final = _PROTOBUF_MASK.__or__
CLEAR_PROTO_BIT: Final = (~_PROTOBUF_MASK).__and__

STATE = ContextVar["ConnectionState"]("APP_STATE")


@final
class MissingSentinel(Any if TYPE_CHECKING else object):
    __slots__ = ()

    def __eq__(self, other: Any) -> Literal[False]:
        return False

    def __bool__(self) -> Literal[False]:
        return False

    def __hash__(self) -> Literal[0]:
        return 0

    def __repr__(self) -> Literal["..."]:
        return "..."


MISSING: Final = MissingSentinel()


@final
class URL:
    API: Final = _URL("https://api.steampowered.com")
    COMMUNITY: Final = _URL("https://steamcommunity.com")
    STORE: Final = _URL("https://store.steampowered.com")
    HELP: Final = _URL("https://help.steampowered.com")
    LOGIN: Final = _URL("https://login.steampowered.com")


# default CMs if Steam API is down
DEFAULT_CMS: Final = (
    "ext1-ams1.steamserver.net:27019",
    "ext1-ams1.steamserver.net:27023",
    "ext1-ams1.steamserver.net:27025",
    "ext1-ams1.steamserver.net:27030",
    "ext1-ams1.steamserver.net:27033",
    "ext1-lhr1.steamserver.net:27019",
    "ext1-lhr1.steamserver.net:27020",
    "ext1-lhr1.steamserver.net:27021",
    "ext1-lhr1.steamserver.net:27022",
    "ext1-lhr1.steamserver.net:27023",
    "ext1-lhr1.steamserver.net:27024",
    "ext1-lhr1.steamserver.net:27025",
    "ext1-lhr1.steamserver.net:27028",
    "ext1-lhr1.steamserver.net:27029",
    "ext1-lhr1.steamserver.net:27030",
    "ext1-lhr1.steamserver.net:27031",
    "ext1-lhr1.steamserver.net:27032",
    "ext1-lhr1.steamserver.net:27033",
    "ext1-lhr1.steamserver.net:27034",
    "ext1-lhr1.steamserver.net:27035",
    "ext1-lhr1.steamserver.net:27036",
    "ext1-lhr1.steamserver.net:27037",
    "ext1-lhr1.steamserver.net:27038",
    "ext1-lhr1.steamserver.net:443",
    "ext2-lhr1.steamserver.net:27019",
    "ext2-lhr1.steamserver.net:27020",
    "ext2-lhr1.steamserver.net:27021",
    "ext2-lhr1.steamserver.net:27022",
    "ext2-lhr1.steamserver.net:27023",
    "ext2-lhr1.steamserver.net:27024",
    "ext2-lhr1.steamserver.net:27025",
    "ext2-lhr1.steamserver.net:27028",
    "ext2-lhr1.steamserver.net:27029",
    "ext2-lhr1.steamserver.net:27030",
    "ext2-lhr1.steamserver.net:27031",
    "ext2-lhr1.steamserver.net:27032",
    "ext2-lhr1.steamserver.net:27033",
    "ext2-lhr1.steamserver.net:27034",
    "ext2-lhr1.steamserver.net:27035",
    "ext2-lhr1.steamserver.net:27036",
    "ext2-lhr1.steamserver.net:27037",
    "ext2-lhr1.steamserver.net:27038",
    "ext2-lhr1.steamserver.net:443",
    "ext3-lhr1.steamserver.net:27019",
    "ext3-lhr1.steamserver.net:27021",
    "ext3-lhr1.steamserver.net:27022",
    "ext3-lhr1.steamserver.net:27023",
    "ext3-lhr1.steamserver.net:27024",
    "ext3-lhr1.steamserver.net:27025",
    "ext3-lhr1.steamserver.net:27028",
    "ext3-lhr1.steamserver.net:27029",
    "ext3-lhr1.steamserver.net:27030",
    "ext3-lhr1.steamserver.net:27031",
    "ext3-lhr1.steamserver.net:27032",
    "ext3-lhr1.steamserver.net:27033",
    "ext3-lhr1.steamserver.net:27034",
    "ext3-lhr1.steamserver.net:27035",
    "ext3-lhr1.steamserver.net:27036",
    "ext3-lhr1.steamserver.net:27037",
    "ext3-lhr1.steamserver.net:27038",
    "ext3-lhr1.steamserver.net:443",
    "ext4-lhr1.steamserver.net:27019",
    "ext4-lhr1.steamserver.net:27020",
    "ext4-lhr1.steamserver.net:27021",
    "ext4-lhr1.steamserver.net:27022",
    "ext4-lhr1.steamserver.net:27023",
    "ext4-lhr1.steamserver.net:27024",
    "ext4-lhr1.steamserver.net:27025",
    "ext4-lhr1.steamserver.net:27028",
    "ext4-lhr1.steamserver.net:27029",
    "ext4-lhr1.steamserver.net:27030",
    "ext4-lhr1.steamserver.net:27031",
    "ext4-lhr1.steamserver.net:27032",
    "ext4-lhr1.steamserver.net:27033",
    "ext4-lhr1.steamserver.net:27034",
    "ext4-lhr1.steamserver.net:27035",
    "ext4-lhr1.steamserver.net:27036",
    "ext4-lhr1.steamserver.net:27037",
    "ext4-lhr1.steamserver.net:27038",
    "ext4-lhr1.steamserver.net:443",
)
