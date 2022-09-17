"""
Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import builtins
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import TYPE_CHECKING, Any, Final, Literal, cast, final

from multidict import MultiDict
from yarl import URL as _URL

from .types.vdf import BinaryVDFDict, VDFDict

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


# default CMs if Steam API is down
DEFAULT_CMS: Final = (
    "cm1-lhr1.cm.steampowered.com:27019",
    "cm1-lhr1.cm.steampowered.com:27020",
    "cm1-lhr1.cm.steampowered.com:27021",
    "cm1-lhr1.cm.steampowered.com:27022",
    "cm1-lhr1.cm.steampowered.com:27023",
    "cm1-lhr1.cm.steampowered.com:27024",
    "cm1-lhr1.cm.steampowered.com:27025",
    "cm1-lhr1.cm.steampowered.com:27028",
    "cm1-lhr1.cm.steampowered.com:27029",
    "cm1-lhr1.cm.steampowered.com:27030",
    "cm1-lhr1.cm.steampowered.com:27031",
    "cm1-lhr1.cm.steampowered.com:27032",
    "cm1-lhr1.cm.steampowered.com:27033",
    "cm1-lhr1.cm.steampowered.com:27034",
    "cm1-lhr1.cm.steampowered.com:27035",
    "cm1-lhr1.cm.steampowered.com:27036",
    "cm1-lhr1.cm.steampowered.com:27037",
    "cm1-lhr1.cm.steampowered.com:27038",
    "cm1-lhr1.cm.steampowered.com:443",
    "cm2-lhr1.cm.steampowered.com:27019",
    "cm2-lhr1.cm.steampowered.com:27020",
    "cm2-lhr1.cm.steampowered.com:27021",
    "cm2-lhr1.cm.steampowered.com:27022",
    "cm2-lhr1.cm.steampowered.com:27023",
    "cm2-lhr1.cm.steampowered.com:27024",
    "cm2-lhr1.cm.steampowered.com:27025",
    "cm2-lhr1.cm.steampowered.com:27028",
    "cm2-lhr1.cm.steampowered.com:27029",
    "cm2-lhr1.cm.steampowered.com:27030",
    "cm2-lhr1.cm.steampowered.com:27031",
    "cm2-lhr1.cm.steampowered.com:27032",
    "cm2-lhr1.cm.steampowered.com:27033",
    "cm2-lhr1.cm.steampowered.com:27034",
    "cm2-lhr1.cm.steampowered.com:27035",
    "cm2-lhr1.cm.steampowered.com:27036",
    "cm2-lhr1.cm.steampowered.com:27037",
    "cm2-lhr1.cm.steampowered.com:27038",
    "cm2-lhr1.cm.steampowered.com:443",
    "cm3-lhr1.cm.steampowered.com:27019",
    "cm3-lhr1.cm.steampowered.com:27020",
    "cm3-lhr1.cm.steampowered.com:27021",
    "cm3-lhr1.cm.steampowered.com:27022",
    "cm3-lhr1.cm.steampowered.com:27023",
    "cm3-lhr1.cm.steampowered.com:27024",
    "cm3-lhr1.cm.steampowered.com:27025",
    "cm3-lhr1.cm.steampowered.com:27028",
    "cm3-lhr1.cm.steampowered.com:27029",
    "cm3-lhr1.cm.steampowered.com:27030",
    "cm3-lhr1.cm.steampowered.com:27031",
    "cm3-lhr1.cm.steampowered.com:27032",
    "cm3-lhr1.cm.steampowered.com:27033",
    "cm3-lhr1.cm.steampowered.com:27034",
    "cm3-lhr1.cm.steampowered.com:27035",
    "cm3-lhr1.cm.steampowered.com:27036",
    "cm3-lhr1.cm.steampowered.com:27037",
    "cm3-lhr1.cm.steampowered.com:27038",
    "cm3-lhr1.cm.steampowered.com:443",
    "cm4-lhr1.cm.steampowered.com:27019",
    "cm4-lhr1.cm.steampowered.com:27020",
    "cm4-lhr1.cm.steampowered.com:27021",
    "cm4-lhr1.cm.steampowered.com:27022",
    "cm4-lhr1.cm.steampowered.com:27023",
    "cm4-lhr1.cm.steampowered.com:27024",
    "cm4-lhr1.cm.steampowered.com:27025",
    "cm4-lhr1.cm.steampowered.com:27028",
    "cm4-lhr1.cm.steampowered.com:27029",
    "cm4-lhr1.cm.steampowered.com:27030",
    "cm4-lhr1.cm.steampowered.com:27031",
    "cm4-lhr1.cm.steampowered.com:27032",
    "cm4-lhr1.cm.steampowered.com:27033",
    "cm4-lhr1.cm.steampowered.com:27034",
    "cm4-lhr1.cm.steampowered.com:27035",
    "cm4-lhr1.cm.steampowered.com:27036",
    "cm4-lhr1.cm.steampowered.com:27037",
    "cm4-lhr1.cm.steampowered.com:27038",
    "cm4-lhr1.cm.steampowered.com:443",
    "cm6-ams1.cm.steampowered.com:27023",
    "cm6-ams1.cm.steampowered.com:27025",
    "cm6-ams1.cm.steampowered.com:27032",
    "cm6-ams1.cm.steampowered.com:27033",
)
