"""
Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020 James. See LICENSE
"""

from __future__ import annotations

import builtins
import sys
from collections.abc import Callable
from functools import partial
from typing import Any, cast

from multidict import MultiDict
from typing_extensions import Final, final
from yarl import URL as _URL

from .types.vdf import BinaryVDFDict, VDFDict

DOCS_BUILDING: bool = getattr(builtins, "__sphinx__", False)
TASK_HAS_NAME = sys.version_info >= (3, 8)


try:
    import orjson

    JSON_LOADS: Final = orjson.loads
    from functools import partial

    def dumps(
        obj: Any,
        *,
        __func: Callable[[Any], bytes] = orjson.dumps,
        __decoder: Callable[[bytes], str] = bytes.decode,
    ) -> str:
        return __decoder(__func(obj))

    JSON_DUMPS: Final = dumps
except ImportError:
    import json

    JSON_LOADS: Final = json.loads

    def dumps(
        obj: Any,
        *,
        __func: Callable[..., str] = json.dumps,
    ) -> str:
        return __func(obj, separators=(",", ":"), ensure_ascii=True)

    JSON_DUMPS: Final = dumps


try:
    import orvdf
except ImportError:
    import vdf

    VDF_LOADS: Final[Callable[[str], VDFDict]] = partial(
        vdf.loads,  # type: ignore
        mapper=MultiDict,
    )
    VDF_BINARY_LOADS: Final = cast(
        Callable[[bytes], BinaryVDFDict],
        partial(
            vdf.binary_loads,  # type: ignore
            mapper=MultiDict,  # type: ignore
        ),
    )
else:
    VDF_LOADS: Final[Callable[[str], VDFDict]] = orvdf.loads
    VDF_BINARY_LOADS: Final[Callable[[bytes], BinaryVDFDict]] = orvdf.binary_loads


try:
    import lxml
except ImportError:
    HTML_PARSER: Final = "html.parser"
else:
    HTML_PARSER: Final = "lxml-xml"


@final
class URL:
    API: Final = _URL("https://api.steampowered.com")
    COMMUNITY: Final = _URL("https://steamcommunity.com")
    STORE: Final = _URL("https://store.steampowered.com")
