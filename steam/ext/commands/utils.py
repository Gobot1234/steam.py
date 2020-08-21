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

from typing import Deque, Dict, Generator, Generic, Optional, TypeVar, Union, overload

__all__ = ("CaseInsensitiveDict",)


_T = TypeVar("_T")
_VT = TypeVar("_VT")


class CaseInsensitiveDict(Dict[str, _VT], Generic[_VT]):
    """A dictionary where keys are case insensitive."""

    def __init__(self, **kwargs: _VT):
        super().__init__(**{k.lower(): v for k, v in kwargs.items()})

    def __repr__(self) -> str:
        return f"CaseInsensitiveDict({', '.join(f'{k}={v!r}' for k, v in self.items())})"

    def __contains__(self, k: str) -> bool:
        return super().__contains__(k.lower())

    def __delitem__(self, k: str) -> None:
        super().__delitem__(k.lower())

    def __getitem__(self, k: str) -> _VT:
        return super().__getitem__(k.lower())

    def __setitem__(self, k: str, v: _VT) -> None:
        super().__setitem__(k.lower(), v)

    @overload
    def get(self, k: str) -> Optional[_VT]:
        ...

    @overload
    def get(self, k: str, default: Optional[_T] = None) -> Optional[Union[_VT, _T]]:
        ...

    def get(self, k, default=None):
        return super().get(k.lower(), default)

    def pop(self, k: str) -> _VT:
        return super().pop(k.lower())


_WHITE_SPACE = tuple(" ")
_QUOTES = tuple('"')


def _end_of_quote_finder(instream: str, location: int) -> int:
    end_of_quote_index = instream.find('"', location)
    if end_of_quote_index == -1:
        raise ValueError(f"No closing quotation found")
    if instream[end_of_quote_index - 1] == "\\":  # quote is escaped carry on searching
        return _end_of_quote_finder(instream, end_of_quote_index + 1)
    return end_of_quote_index


class Shlex:
    """A simple lexical analyser.
    This should be a more pythonic version of :class:`shlex.shlex` in posix mode.
    """

    __slots__ = ("instream", "position", "_undo_pushback")

    def __init__(self, instream: str):
        self.instream = instream.replace("‘", '"').replace("’", '"').replace("“", '"').replace("”", '"')
        self.position = 0
        self._undo_pushback: Deque[int] = Deque()

    def read(self) -> str:
        token = []
        for char in self.instream[self.position :]:
            self.position += 1
            if char in _WHITE_SPACE:
                break
            if char in _QUOTES:
                before = self.position
                if self.instream[before - 2] != "\\":  # quote is escaped carry on searching
                    end_of_quote = _end_of_quote_finder(self.instream, before)
                    token = f'"{self.instream[before : end_of_quote]}"'
                    self.position = end_of_quote + 1
                    break
                token.pop()

            token.append(char)

        token = "".join(token)
        if token:
            self._undo_pushback.append(len(token))
        if token[-1:] == '"' and token[:1] == '"':
            token = token[1:-1]
        return token

    def undo(self) -> None:
        self.position -= self._undo_pushback.pop()

    def __repr__(self):
        attrs = (
            "instream",
            "position",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Shlex {' '.join(resolved)}>"

    def __iter__(self) -> Generator[str, None, None]:
        token = self.read()
        while token:
            yield token
            token = self.read()
