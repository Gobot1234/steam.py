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

import re
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from .enums import Result

if TYPE_CHECKING:
    from aiohttp import ClientResponse

    from .gateway import Msgs


__all__ = (
    "SteamException",
    "NotFound",
    "Forbidden",
    "LoginError",
    "NoCMsFound",
    "HTTPException",
    "ClientException",
    "ConfirmationError",
    "AuthenticatorError",
    "InvalidCredentials",
    "WSException",
    "WSForbidden",
    "WSNotFound",
    "InvalidSteamID",
)

CODE_FINDER = re.compile(r"\S(\d+)\S")


class SteamException(Exception):
    """Base exception class for steam.py."""


class ClientException(SteamException):
    """Exception that's thrown when something in the client fails.

    Subclass of :exc:`SteamException`.
    """


class HTTPException(SteamException):
    """Exception that's thrown for any web API error.

    Subclass of :exc:`SteamException`.

    Attributes
    ------------
    response
        The response of the failed HTTP request.
    message
        The message associated with the error.
        Could be an empty string if no message can parsed.
    status
        The status code of the HTTP request.
    code
        The Steam specific error code for the failure.
    """

    def __init__(self, response: ClientResponse, data: Any | None):
        self.response = response
        self.status = response.status
        self.code = Result.Invalid

        if data:
            if isinstance(data, dict):
                message = data.get("message")
                if message is None:
                    truthy_str_values = [  # ignore {'success': False} as the message
                        value for value in data.values() if value and isinstance(value, str)
                    ]
                    if truthy_str_values:
                        message = str(truthy_str_values[0])
                self.message = message or ""
                code = (
                    data.get("eresult")  # try the data if possible
                    or response.headers.get("X-EResult")  # then the headers
                    or CODE_FINDER.findall(message)  # finally the message
                )
                if code:
                    if isinstance(code, list):
                        self.message = CODE_FINDER.sub("", message)
                        code = code[0]
                    self.code = Result.try_value(int(code))
            else:
                text = BeautifulSoup(data, "html.parser").get_text("\n")
                self.message = text or ""
        else:
            self.message = ""

        self.message = self.message.replace("  ", " ").strip()
        super().__init__(
            f"{response.status} {response.reason} (error code: {self.code})"
            f"{f': {self.message}' if self.message else ''}"
        )


class Forbidden(HTTPException):
    """Exception that's thrown when status code 403 occurs.

    Subclass of :exc:`HTTPException`.
    """


class NotFound(HTTPException):
    """Exception that's thrown when status code 404 occurs.

    Subclass of :exc:`HTTPException`.
    """


class WSException(SteamException):
    """Exception that's thrown for any websocket error. Similar to :exc:`HTTPException`.

    Subclass of :exc:`SteamException`.

    Attributes
    ------------
    msg
        The received protobuf.
    message
        The message that Steam sent back with the request, could be ``None``.
    code
        The Steam specific error code for the failure.
    """

    def __init__(self, msg: Msgs):
        self.msg = msg
        self.code = msg.result
        self.message: str | None = getattr(msg.header.body, "error_message", None)
        super().__init__(
            f"The request {msg.header.body.job_name_target or msg.msg} failed. (error code: {self.code!r})"
            f"{f': {self.message}' if self.message else ''}"
        )


class WSForbidden(WSException):
    """Exception that's thrown when the websocket returns an :class:`.Result` that means we do not have permission
    to perform an action. Similar to :exc:`Forbidden`.

    Subclass of :exc:`WSException`.
    """


class WSNotFound(WSException):
    """Exception that's thrown when the websocket returns an :class:`.Result` that means the object wasn't found.
    Similar to :exc:`NotFound`.

    Subclass of :exc:`WSException`.
    """


class LoginError(SteamException):
    """Exception that's thrown when a login fails.

    Subclass of :exc:`SteamException`.
    """


class InvalidCredentials(LoginError):
    """Exception that's thrown when credentials are incorrect.

    Subclass of :exc:`LoginError`.
    """


class AuthenticatorError(ClientException):
    """Exception that's thrown when Steam cannot authenticate your details.

    Subclass of :exc:`LoginError`.
    """


class ConfirmationError(AuthenticatorError):
    """Exception that's thrown when a confirmation fails.

    Subclass of :exc:`AuthenticatorError`.
    """


class NoCMsFound(LoginError):
    """Exception that's thrown when no CMs can be found to connect to.

    Subclass of :exc:`LoginError`.
    """


class InvalidSteamID(SteamException):
    """Exception that's thrown when a SteamID cannot be valid.

    Subclass of :exc:`SteamException`.

    Attributes
    ----------
    id
        The invalid id.
    """

    def __init__(self, id: Any, msg: str | None = None):
        self.id = id
        super().__init__(f"{id!r} cannot be converted to any valid SteamID{f' as {msg}' if msg is not None else ''}")
