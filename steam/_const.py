"""Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020 James. See LICENSE
"""

import builtins
import sys
from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any, TypeVar

from multidict import MultiDict
from typing_extensions import Final, Never, TypeAlias, TypedDict, final
from yarl import URL as _URL

DOCS_BUILDING: bool = getattr(builtins, "__sphinx__", False)
TASK_HAS_NAME = sys.version_info >= (3, 8)


@final
class URL:
    API: Final = _URL("https://api.steampowered.com")
    COMMUNITY: Final = _URL("https://steamcommunity.com")
    STORE: Final = _URL("https://store.steampowered.com")
