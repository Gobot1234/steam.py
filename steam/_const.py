"""
Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020 James. See LICENSE
"""

from __future__ import annotations

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


# VDF related types
try:
    import orvdf
except ImportError:
    import vdf

    VDFDict: TypeAlias = "MultiDict[str | VDFDict]"
    BinaryVDFDict: TypeAlias = "MultiDict[str | int | float | BinaryVDFDict]"
    VDF_LOADS: Callable[[str], VDFDict] = partial(vdf.loads, mapper=MultiDict)
    VDF_BINARY_LOADS: Callable[[bytes], BinaryVDFDict] = partial(vdf.binary_loads, mapper=MultiDict)
else:
    VDFDict: TypeAlias = "MultiDict[str | bool | None | VDFDict]"
    BinaryVDFDict: TypeAlias = "MultiDict[str | int | float | bool | None | BinaryVDFDict]"
    VDF_LOADS: Callable[[str], VDFDict] = orvdf.loads
    VDF_BINARY_LOADS: Callable[[bytes], BinaryVDFDict] = orvdf.binary_loads

T = TypeVar("T")
VDFInt: TypeAlias = str


class VDFList(MultiDict[T]):
    # lists don't strictly exist in the VDF "spec" however Valve uses {"0": T, "1": T, ..., "n": T}
    # to represent them, so prevent people doing daft things like use .keys() and iterating over it
    # for now using __getitem__ is fine, but I might remove this at some point

    def keys(self) -> Never:
        ...

    def __iter__(self) -> Never:
        ...


if TYPE_CHECKING:

    class TypedVDFDict(MultiDict[Any], TypedDict):  # type: ignore  # this obviously doesn't work at runtime
        ...

else:

    class TypedVDFDict(MultiDict[Any]):
        def __init_subclass__(cls, **kwargs: Any) -> None:
            pass


@final
class URL:
    API: Final = _URL("https://api.steampowered.com")
    COMMUNITY: Final = _URL("https://steamcommunity.com")
    STORE: Final = _URL("https://store.steampowered.com")
