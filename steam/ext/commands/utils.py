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

import importlib
import typing
from collections import deque
from typing import (
    TYPE_CHECKING,
    Any,
    Deque,
    Dict,
    ForwardRef,
    Generator,
    Generic,
    Optional,
    TypeVar,
    Union,
    _GenericAlias,
    overload,
)

from typing_extensions import get_args, get_origin

from .converters import Greedy

if TYPE_CHECKING:
    from types import ModuleType


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


class MissingClosingQuotation(Exception):
    def __init__(self, position: int):
        self.position = position
        super().__init__(f"No closing quotation found after the character after position {position}")


def _end_of_quote_finder(instream: str, location: int) -> int:
    end_of_quote_index = instream.find('"', location)
    if end_of_quote_index == -1:
        raise MissingClosingQuotation(location)
    if instream[end_of_quote_index - 1] == "\\":  # quote is escaped carry on searching
        return _end_of_quote_finder(instream, end_of_quote_index + 1)
    return end_of_quote_index


class Shlex:
    """A simple lexical analyser.
    This should be a simpler and faster version of :class:`shlex.shlex` in posix mode.
    """

    __slots__ = ("in_stream", "position", "end", "_undo_pushback")

    def __init__(self, in_stream: str):
        self.in_stream = in_stream.replace("‘", '"').replace("’", '"').replace("“", '"').replace("”", '"').strip()
        self.position = 0
        self.end = len(self.in_stream)
        self._undo_pushback: Deque[int] = deque()

    def read(self) -> Optional[str]:
        if self.position >= self.end:
            return None
        token = []
        start = self.position
        for char in self.in_stream[self.position :]:
            self.position += 1
            if char in _WHITE_SPACE:
                break
            if char in _QUOTES:
                before = self.position
                if self.in_stream[before - 2] != "\\":  # quote is escaped carry on searching
                    end_of_quote = _end_of_quote_finder(self.in_stream, before)
                    token = f'"{self.in_stream[before: end_of_quote]}"'
                    self.position = end_of_quote + 1
                    break
                token.pop()

            token.append(char)

        token = "".join(token)
        self._undo_pushback.append(start)
        if token[-1:] == '"' and token[:1] == '"':
            token = token[1:-1]
        return token.strip()

    def undo(self) -> None:
        self.position = self._undo_pushback.pop()

    def __repr__(self) -> str:
        attrs = (
            "in_stream",
            "position",
            "end",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Shlex {' '.join(resolved)}>"

    def __iter__(self) -> Generator[str, None, None]:
        while 1:
            token = self.read()
            if token is None:
                break
            yield token


# various typing related functions


def reload_module_with_TYPE_CHECKING(module: "ModuleType") -> None:
    """Reload a module with typing.TYPE_CHECKING set to ``True``. Allowing you to avoid circular import issues due to
    the way :meth:`importlib.reload` works.

    Warnings
    --------
    This is very hacky and is only really for internal use.

    We attempt to fetch any imports in a TYPE_CHECKING block. If a user wants to have this behaviour avoided you can use
    something similar to ::

        if TYPE_CHECKING:
           from expensive_module import expensive_type
        else:
           expensive_type = str
    """
    if not (typing in module.__dict__.values() or not getattr(module, "TYPE_CHECKING", True)):
        return

    typing.TYPE_CHECKING = True
    importlib.reload(module)
    typing.TYPE_CHECKING = False


def _eval_type(type: Any, globals: Dict[str, Any]) -> Any:
    """Evaluate all forward reverences in the given type."""
    if isinstance(type, str):
        type = ForwardRef(type)
    if isinstance(type, ForwardRef):
        return type._evaluate(globals, {})
    if isinstance(type, _GenericAlias):
        args = tuple(_eval_type(arg, globals) for arg in get_args(type))
        return get_origin(type)[args]
    return type


def update_annotations(annotations: Dict[str, Any], globals: Dict[str, Any]) -> Dict[str, Any]:
    """A helper function loosely based off of typing's implementation of :meth:`typing.get_type_hints`.

    Main purpose of this is for evaluating postponed annotations (type hints in quotes) for more info see :pep:`563`
    """
    for key, annotation in annotations.items():
        annotation = _eval_type(annotation, globals)
        if get_origin(annotation) is Greedy:
            annotation.converter = annotation.__args__[0]  # update the old converter
            Greedy[annotation.converter]  # check if the evaluated type is valid

        annotations[key] = annotation
    return annotations
