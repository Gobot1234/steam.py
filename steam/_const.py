"""
Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import builtins
import sys
from collections.abc import Callable
from io import StringIO
from typing import Any

from multidict import MultiDict
from typing_extensions import Final, final
from yarl import URL as _URL

from .types.vdf import BinaryVDFDict, VDFDict

DOCS_BUILDING: bool = getattr(builtins, "__sphinx__", False)
TASK_HAS_NAME = sys.version_info >= (3, 8)


try:
    import orjson
except ModuleNotFoundError:
    import json

    JSON_LOADS: Final = json.loads

    def dumps(
        obj: Any,
        *,
        __func: Callable[..., str] = json.dumps,
    ) -> str:
        return __func(obj, separators=(",", ":"), ensure_ascii=True)

    JSON_DUMPS: Final = dumps
else:
    JSON_LOADS: Final[Callable[[str | bytes], Any]] = orjson.loads

    def dumps(
        obj: Any,
        *,
        __func: Callable[[Any], bytes] = orjson.dumps,
        __decoder: Callable[[bytes], str] = bytes.decode,
    ) -> str:
        return __decoder(__func(obj))

    JSON_DUMPS: Final = dumps


try:
    import orvdf
except ModuleNotFoundError:
    import vdf

    def loads(
        s: str,
        *,
        __func: Callable[..., Any] = vdf.parse,
        __mapper: type[MultiDict[Any]] = MultiDict,
        __string_io: type[StringIO] = StringIO,
    ) -> VDFDict:
        return __func(__string_io(s), mapper=__mapper)

    def binary_loads(
        s: bytes, *, __func: Callable[..., Any] = vdf.binary_loads, __mapper: type[MultiDict[Any]] = MultiDict
    ) -> BinaryVDFDict:
        return __func(s, mapper=__mapper)

    VDF_LOADS: Final = loads
    VDF_BINARY_LOADS: Final = binary_loads

else:
    VDF_LOADS: Final[Callable[[str], VDFDict]] = orvdf.loads
    VDF_BINARY_LOADS: Final[Callable[[bytes], BinaryVDFDict]] = orvdf.binary_loads


try:
    import lxml
except ModuleNotFoundError:
    HTML_PARSER: Final = "html.parser"
else:
    HTML_PARSER: Final = "lxml-xml"


@final
class URL:
    API: Final = _URL("https://api.steampowered.com")
    COMMUNITY: Final = _URL("https://steamcommunity.com")
    STORE: Final = _URL("https://store.steampowered.com")


# default CMs if Steam API is down
DEFAULT_CMS: Final = (
    "ext1-ams1.steamserver.net:27019",
    "ext1-ams1.steamserver.net:27021",
    "ext1-ams1.steamserver.net:27022",
    "ext1-ams1.steamserver.net:27023",
    "ext1-ams1.steamserver.net:27025",
    "ext1-ams1.steamserver.net:27028",
    "ext1-ams1.steamserver.net:27029",
    "ext1-ams1.steamserver.net:27031",
    "ext1-ams1.steamserver.net:27032",
    "ext1-ams1.steamserver.net:27035",
    "ext1-ams1.steamserver.net:443",
    "ext1-fra1.steamserver.net:27019",
    "ext1-fra1.steamserver.net:27021",
    "ext1-fra1.steamserver.net:27022",
    "ext1-fra1.steamserver.net:27024",
    "ext1-fra1.steamserver.net:27025",
    "ext1-fra1.steamserver.net:27028",
    "ext1-fra1.steamserver.net:27030",
    "ext1-fra1.steamserver.net:27031",
    "ext1-fra1.steamserver.net:27033",
    "ext1-fra1.steamserver.net:27037",
    "ext1-fra1.steamserver.net:27038",
    "ext1-fra1.steamserver.net:443",
    "ext1-lhr1.steamserver.net:27030",
    "ext1-lhr1.steamserver.net:27038",
    "ext1-lhr1.steamserver.net:443",
    "ext1-par1.steamserver.net:27019",
    "ext1-par1.steamserver.net:27021",
    "ext1-par1.steamserver.net:27022",
    "ext1-par1.steamserver.net:27023",
    "ext1-par1.steamserver.net:27028",
    "ext1-par1.steamserver.net:27032",
    "ext1-par1.steamserver.net:27037",
    "ext1-par1.steamserver.net:443",
    "ext2-ams1.steamserver.net:27020",
    "ext2-ams1.steamserver.net:27022",
    "ext2-ams1.steamserver.net:27025",
    "ext2-ams1.steamserver.net:27029",
    "ext2-ams1.steamserver.net:27032",
    "ext2-ams1.steamserver.net:27033",
    "ext2-ams1.steamserver.net:27034",
    "ext2-ams1.steamserver.net:27037",
    "ext2-ams1.steamserver.net:443",
    "ext2-fra1.steamserver.net:27021",
    "ext2-fra1.steamserver.net:27033",
    "ext2-fra1.steamserver.net:27035",
    "ext2-lhr1.steamserver.net:27019",
    "ext2-lhr1.steamserver.net:27020",
    "ext2-lhr1.steamserver.net:27021",
    "ext2-lhr1.steamserver.net:27022",
    "ext2-lhr1.steamserver.net:27024",
    "ext2-lhr1.steamserver.net:443",
    "ext2-par1.steamserver.net:27019",
    "ext2-par1.steamserver.net:27021",
    "ext2-par1.steamserver.net:27023",
    "ext2-par1.steamserver.net:27024",
    "ext2-par1.steamserver.net:27028",
    "ext2-par1.steamserver.net:27029",
    "ext2-par1.steamserver.net:27030",
    "ext2-par1.steamserver.net:27031",
    "ext2-par1.steamserver.net:27033",
    "ext2-par1.steamserver.net:27034",
    "ext2-par1.steamserver.net:27035",
    "ext2-par1.steamserver.net:27036",
    "ext2-par1.steamserver.net:27037",
    "ext2-par1.steamserver.net:443",
    "ext3-lhr1.steamserver.net:27019",
    "ext3-lhr1.steamserver.net:27021",
    "ext3-lhr1.steamserver.net:27023",
    "ext3-lhr1.steamserver.net:27024",
    "ext3-lhr1.steamserver.net:27029",
    "ext3-lhr1.steamserver.net:27030",
    "ext3-lhr1.steamserver.net:27033",
    "ext3-lhr1.steamserver.net:27037",
    "ext3-lhr1.steamserver.net:443",
    "ext4-lhr1.steamserver.net:27021",
    "ext4-lhr1.steamserver.net:27023",
    "ext4-lhr1.steamserver.net:27028",
    "ext4-lhr1.steamserver.net:27038",
    "ext4-lhr1.steamserver.net:443",
)
