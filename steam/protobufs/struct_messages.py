from __future__ import annotations

from typing import Any, TypeVar

from ..utils import StructIO
from .emsg import EMsg
from .protobufs import PROTOBUFS

M = TypeVar("M", bound="StructMessage")


class StructMessageMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> StructMessageMeta:
        attrs["__slots__"] = slots = tuple(attrs.get("__annotations__", ()))
        exec(
            f"def __init__(self, {', '.join(f'{slot}=None' for slot in slots)}): "
            f"{' '.join(f'self.{slot} = {slot};' for slot in slots) or 'pass'}\n",
            {},
            attrs,
        )

        cls = super().__new__(mcs, name, bases, attrs)
        if cls.__module__ == __name__ and name != "StructMessage":
            PROTOBUFS[EMsg[name]] = cls

        return cls


class StructMessage(metaclass=StructMessageMeta):
    def from_dict(self: M, dict: dict[str, Any]) -> M:
        self.__init__(**dict)
        return self

    def to_dict(self, *_) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.__annotations__}

    def __bytes__(self) -> bytes:
        buffer = StructIO()
        for key, annotation in self.__annotations__.items():
            if annotation == "int":
                buffer.write_u64(getattr(self, key))
            elif annotation == "bool":
                buffer.write_u8(getattr(self, key))

        return buffer.buffer

    def parse(self: M, data: bytes) -> M:
        raise NotImplementedError
