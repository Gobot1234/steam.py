"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import Any

from typing_extensions import Self

from ..utils import StructIO


class StructMessage:
    __slots__ = ()

    def from_dict(self, dict: dict[str, Any]) -> Self:
        self.__init__(**dict)
        return self

    def to_dict(self, *_: Any) -> dict[str, Any]:
        try:
            annotations = self.__annotations__
        except AttributeError:
            annotations = ()
        return {key: getattr(self, key) for key in annotations}

    def __bytes__(self) -> bytes:
        try:
            annotations = self.__annotations__
        except AttributeError:
            annotations = {}
        with StructIO() as io:
            for key, annotation in annotations.items():
                if isinstance(annotation, type):
                    raise RuntimeError("annotations shouldn't be types")
                if annotation == "int":
                    io.write_u64(getattr(self, key))
                elif annotation == "bool":
                    io.write_u8(getattr(self, key))
                else:
                    raise RuntimeError(f"Unknown field {annotation}")

            return io.buffer

    def parse(self, data: bytes) -> Self:
        raise NotImplementedError
