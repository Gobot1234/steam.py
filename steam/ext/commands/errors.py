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

from typing import TYPE_CHECKING

from ...errors import SteamException

if TYPE_CHECKING:
    from inspect import Parameter

__all__ = (
    'CommandError',
    'BadArgument',
    'CheckFailure',
    'CommandNotFound',
    'MissingRequiredArgument',
)


class CommandError(SteamException):
    """Base Exception for errors raised by commands.

    Subclass of :exc:`SteamException`."""


class CommandNotFound(CommandError):
    """Exception raised when a command is not found.

    Subclass of :exc:`CommandError`."""


class BadArgument(CommandError):
    """Exception raised when a bad argument is passed to a command.

    Subclass of :exc:`CommandError`.

    Attributes
    ----------
    param: :class:`inspect.Parameter`
        The parameter that failed to convert.
    argument: :class:`str`
        The user inputted argument that failed to convert.
    """

    def __init__(self, param: 'Parameter', argument: str):
        self.param = param
        self.argument = argument
        super().__init__(f'{argument} failed to convert to type {param.annotation or str}')


class MissingRequiredArgument(CommandError):
    """Exception raised when a required argument is not passed to a command.

    Subclass of :exc:`CommandError`.

    Attributes
    ----------
    param: :class:`inspect.Parameter`
        The argument that is missing.
    """

    def __init__(self, param: 'Parameter'):
        self.param = param
        super().__init__(f'{param.name} is a required argument that is missing.')


class CheckFailure(CommandError):
    """Exception raised when a check fails.

    Subclass of :exc:`CommandError`."""
