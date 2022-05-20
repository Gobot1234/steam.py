"""Licensed under The MIT License (MIT) - Copyright (c) 2020 James. See LICENSE"""

from collections.abc import Coroutine
from typing import Any, Generic, TypeAlias, TypedDict, TypeVar

from yarl import URL

T = TypeVar("T")


class ResponseDict(TypedDict, Generic[T]):
    response: T


Coro: TypeAlias = "Coroutine[Any, Any, T]"
ResponseType: TypeAlias = "Coro[ResponseDict[T]]"
StrOrURL: TypeAlias = URL | str
