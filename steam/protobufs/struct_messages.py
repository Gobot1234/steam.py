"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import Any

from typing_extensions import Self

from ..utils import StructIO
from .emsg import EMsg
from .protobufs import PROTOBUFS


class StructMessageMeta(type):
    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> Self:
        attrs["__slots__"] = slots = tuple(attrs.get("__annotations__", ()))
        exec(
            f"def __init__(self, {', '.join(f'{slot}=None' for slot in slots)}): "
            f"{' '.join(f'self.{slot} = {slot};' for slot in slots) or 'pass'}\n",
            {},
            attrs,
        )

        cls = super().__new__(mcs, name, bases, attrs)
        if cls.__module__ == __name__ and name != "StructMessage":
            PROTOBUFS[EMsg[name]] = cls  # type: ignore

        return cls


class StructMessage(metaclass=StructMessageMeta):
    def from_dict(self, dict: dict[str, Any]) -> Self:
        self.__init__(**dict)
        return self

    def to_dict(self, *_) -> dict[str, Any]:
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
                if annotation == "int":
                    io.write_u64(getattr(self, key))
                elif annotation == "bool":
                    io.write_u8(getattr(self, key))

            return io.buffer

    def parse(self, data: bytes) -> Self:
        raise NotImplementedError


class ClientGetFriendsWhoPlayGame(StructMessage):
    app_id: int


class ClientGetFriendsWhoPlayGameResponse(StructMessage):
    eresult: int
    app_id: int
    friends: list[int]

    def parse(self, data: bytes) -> Self:
        with StructIO(data) as io:
            self.eresult = io.read_u32()
            self.app_id = io.read_u64()
            self.friends = [io.read_u64() for _ in range(io.read_u32())]

        return self
