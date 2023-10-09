"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypeVar

from typing_extensions import TypedDict
from yarl import URL

if TYPE_CHECKING:
    from collections.abc import Coroutine

T = TypeVar("T")


class ResponseDict(TypedDict, Generic[T]):
    response: T


Coro: TypeAlias = "Coroutine[Any, Any, T]"
ResponseType: TypeAlias = "Coro[ResponseDict[T]]"
StrOrURL: TypeAlias = URL | str
IPAdress: TypeAlias = IPv4Address


class CMList(TypedDict):
    success: bool
    serverlist: list[CM]


class CM(TypedDict):
    endpoint: str
    load: float
    wtd_load: float


class EResultSuccess(TypedDict):
    success: int


class AddWalletCode(EResultSuccess):
    amount: int
    detail: int
