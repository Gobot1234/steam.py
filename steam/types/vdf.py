"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeVar

from multidict import MultiDict

if TYPE_CHECKING:
    from typing import TypeAlias

    from typing_extensions import Never, TypedDict

# VDF related types
VDFDict: TypeAlias = MultiDict["str | VDFDict"]  # str | bool | None | VDFDict for orvdf
BinaryVDFDict: TypeAlias = MultiDict[
    "str | int | float | BinaryVDFDict"
]  # str | int | float | bool | None | BinaryVDFDict for orvdf


T = TypeVar("T")
VDFInt: TypeAlias = str
VDFBool: TypeAlias = Literal["0", "1"]


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
