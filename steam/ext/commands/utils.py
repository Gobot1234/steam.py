# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from collections import deque
from io import StringIO
from shlex import shlex
from typing import Dict, Generic, Optional, TypeVar, Union, overload

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
