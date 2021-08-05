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

from typing import TYPE_CHECKING

from ...errors import SteamException

if TYPE_CHECKING:
    from inspect import Parameter

    from .commands import Command


__all__ = (
    "CommandError",
    "BadArgument",
    "MissingRequiredArgument",
    "DuplicateKeywordArgument",
    "UnmatchedKeyValuePair",
    "CheckFailure",
    "NotOwner",
    "CommandNotFound",
    "CommandDisabled",
    "CommandOnCooldown",
)


class CommandError(SteamException):
    """Base Exception for errors raised by commands.

    Subclass of :exc:`SteamException`.
    """


class CommandNotFound(CommandError):
    """Exception raised when a command is not found.

    Subclass of :exc:`CommandError`.
    """


class BadArgument(CommandError):
    """Exception raised when a bad argument is passed to a command.

    Subclass of :exc:`CommandError`.
    """


class MissingRequiredArgument(BadArgument):
    """Exception raised when a required argument is not passed to a command.

    Subclass of :exc:`BadArgument`.

    Attributes
    ----------
    param
        The argument that is missing.
    """

    def __init__(self, param: Parameter):
        self.param = param
        super().__init__(f"{param.name!r} is a required argument that is missing.")


class DuplicateKeywordArgument(BadArgument):
    """Exception raised when a keyword argument passed would shadow another.

    Subclass of :exc:`BadArgument`.

    Attributes
    ----------
    name
        The argument that would shadow another.
    """

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"{name!r} shadows another argument.")


class UnmatchedKeyValuePair(BadArgument):
    """Exception raised when an incorrect number of key value pairs are passed to a command to be unpacked.

    Subclass of :exc:`BadArgument`.
    """


class CheckFailure(CommandError):
    """Base Exception raised when a check fails.

    Subclass of :exc:`CommandError`.
    """


class CommandDisabled(CheckFailure):
    """Exception raised when a command is disabled and is attempted to be ran.

    Subclass of :exc:`CheckFailure`.

    Attributes
    -----------
    command
        The command that has been disabled.
    """

    def __init__(self, command: Command):
        self.command = command
        super().__init__(f"{command.name} is currently disabled")


class NotOwner(CheckFailure):
    """Exception raised the user does not own the bot.

    Subclass of :exc:`CheckFailure`.
    """

    def __init__(self):
        super().__init__("You do not own this bot")


class DMChannelOnly(CheckFailure):
    """Exception raised the user does not own the bot.

    Subclass of :exc:`CheckFailure`.
    """

    def __init__(self):
        super().__init__("This command can only be used in DMs")


class CommandOnCooldown(CommandError):
    """Exception raised when a command is still on cooldown.

    Subclass of :exc:`CommandError`.

    Attributes
    ----------
    retry_after
        The time in seconds at which that the next command can successfully be executed.
    """

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Command is on cooldown for {retry_after:.2} more seconds")


class MissingClosingQuotation(CommandError):
    def __init__(self, position: int):
        self.position = position
        super().__init__(f"No closing quotation found after the character at position {position}")
