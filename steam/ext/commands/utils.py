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

from __future__ import annotations

from collections import deque
from typing import Dict, Generator, TypeVar, overload

from .errors import MissingClosingQuotation

_T = TypeVar("_T")
_VT = TypeVar("_VT")


class CaseInsensitiveDict(Dict[str, _VT]):
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
    def get(self, k: str) -> _VT | None:
        ...

    @overload
    def get(self, k: str, default: _T | None = None) -> _VT | _T | None:
        ...

    def get(self, k: str, default: _T | None = None) -> _VT | _T | None:
        return super().get(k.lower(), default)

    @overload
    def pop(self, k: str) -> _VT | None:
        ...

    @overload
    def pop(self, k: str, default: _T | None = None) -> _VT | _T | None:
        ...

    def pop(self, k: str, default: _T | None = None) -> _VT | _T | None:
        return super().pop(k.lower())


def _end_of_quote_finder(in_stream: str, location: int) -> int:
    end_of_quote_index = in_stream.find('"', location)
    if end_of_quote_index == -1:
        raise MissingClosingQuotation(location)
    if in_stream[end_of_quote_index - 1] == "\\":  # quote is escaped carry on searching
        return _end_of_quote_finder(in_stream, end_of_quote_index + 1)
    return end_of_quote_index


def remove_quotes(string: str) -> str:
    """
    >>> remove_quotes('"only a quote at the start')
    '"quoted only at the start'
    >>> remove_quotes('"quoted all the way"')
    'quoted all the way'
    """
    return string[1:-1] if (string[-1:], string[:1]) == ('"', '"') else string


class Shlex:
    """A simple lexical analyser.
    This should be a simpler and faster version of :class:`shlex.shlex` in posix mode.
    """

    __slots__ = ("in_stream", "position", "end", "_undo_pushback")

    def __init__(self, in_stream: str):
        self.in_stream = in_stream.replace("‘", '"').replace("’", '"').replace("“", '"').replace("”", '"').strip()
        self.position = 0
        self.end = len(self.in_stream)
        self._undo_pushback: deque[int] = deque()

    def read(self) -> str | None:
        if self.position >= self.end:
            return None

        while True:
            start = self.position
            characters = []

            for character in self.in_stream[self.position :]:
                self.position += 1
                if character.isspace():
                    break

                if character == '"':
                    before = self.position
                    if self.in_stream[before - 2] != "\\":  # quote is escaped carry on searching
                        end_of_quote = _end_of_quote_finder(self.in_stream, before)
                        self.position = end_of_quote + 2
                        self._undo_pushback.append(start)
                        return remove_quotes(self.in_stream[before:end_of_quote])

                    characters.pop()
                characters.append(character)

            ret = remove_quotes("".join(characters))
            if ret:
                self._undo_pushback.append(start)
                return ret

    def undo(self) -> None:
        try:
            self.position = self._undo_pushback.pop()
        except IndexError:
            pass

    @property
    def rest(self) -> str:
        return self.in_stream[self.position :]

    def __repr__(self) -> str:
        attrs = (
            "in_stream",
            "position",
            "end",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Shlex {' '.join(resolved)}>"

    def __iter__(self) -> Generator[str, None, None]:
        while True:
            token = self.read()
            if token is None:
                break
            yield token
