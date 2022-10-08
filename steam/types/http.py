"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from collections.abc import Coroutine
from ipaddress import IPv4Address
from typing import Any, Generic, TypeVar

from typing_extensions import TypeAlias, TypedDict
from yarl import URL

T = TypeVar("T")


class ResponseDict(TypedDict, Generic[T]):
    response: T


Coro: TypeAlias = "Coroutine[Any, Any, T]"
ResponseType: TypeAlias = "Coro[ResponseDict[T]]"
StrOrURL: TypeAlias = URL | str
IPAdress: TypeAlias = IPv4Address
