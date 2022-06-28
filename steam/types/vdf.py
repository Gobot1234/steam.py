"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from multidict import MultiDict
from typing_extensions import Never, TypeAlias, TypedDict

# VDF related types
try:
    import orvdf
except ModuleNotFoundError:
    VDFDict: TypeAlias = "MultiDict[str | VDFDict]"
    BinaryVDFDict: TypeAlias = "MultiDict[str | int | float | BinaryVDFDict]"
else:
    VDFDict: TypeAlias = "MultiDict[str | bool | None | VDFDict]"
    BinaryVDFDict: TypeAlias = "MultiDict[str | int | float | bool | None | BinaryVDFDict]"


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
        pass

else:

    class TypedVDFDict(MultiDict[Any]):
        def __init_subclass__(cls, **kwargs: Any) -> None:
            pass
