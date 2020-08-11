from collections import deque
from io import StringIO
from shlex import shlex
from typing import (
    Dict,
    Generic,
    Optional,
    TypeVar,
    Union,
    overload,
)

__all__ = ("CaseInsensitiveDict",)


T = TypeVar("T")
VT = TypeVar("VT")


class CaseInsensitiveDict(Dict[str, VT], Generic[VT]):
    def __init__(self, **kwargs: VT):
        super().__init__(**{k.lower(): v for k, v in kwargs.items()})

    def __repr__(self) -> str:
        return f"CaseInsensitiveDict({', '.join(f'{k}={v!r}' for k, v in self.items())})"

    def __contains__(self, key: str) -> bool:
        return super().__contains__(key.lower())

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key.lower())

    def __getitem__(self, key: str) -> VT:
        return super().__getitem__(key.lower())

    def __setitem__(self, key: str, value: VT) -> None:
        super().__setitem__(key.lower(), value)

    @overload
    def get(self, k: str) -> Optional[VT]:
        ...

    @overload
    def get(self, k: str, default: Optional[T] = None) -> Optional[Union[VT, T]]:
        ...

    def get(self, k, default=None):
        return super().get(k.lower(), default)

    def pop(self, k: str) -> VT:
        return super().pop(k.lower())


class Shlex(shlex):
    def __init__(self, instream: str):
        super().__init__(instream, posix=True)
        self._undo_pushback = deque()
        self.whitespace_split = True
        self.commenters = ""
        self.quotes = '"'
        self.whitespace = " "

    def get_token(self) -> Optional[str]:
        token = super().get_token()
        self._undo_pushback.append(token)
        return token

    def undo(self) -> None:
        token = self._undo_pushback.pop()
        self.instream = StringIO(f"{token} {self.instream.read()}")

    def __repr__(self):
        self.instream.seek(0)
        read = self.instream.read()
        self.instream.seek(0)
        return f"Shlex({read!r})"
