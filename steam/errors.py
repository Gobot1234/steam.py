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

import re
from typing import TYPE_CHECKING, Any, Optional

from bs4 import BeautifulSoup

from .enums import EResult

if TYPE_CHECKING:
    from aiohttp import ClientResponse

    from .protobufs import MsgProto


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
    """Exception that's thrown when something isn't possible
    but is handled by the client.

    Subclass of :exc:`SteamException`.
    """


class HTTPException(SteamException):
    """Exception that's thrown for any web API error.

    Subclass of :exc:`SteamException`.

    Attributes
    ------------
    response: :class:`aiohttp.ClientResponse`
        The response of the failed HTTP request.
    message: :class:`str`
        The message associated with the error.
        Could be an empty string if no message can parsed.
    status: :class:`int`
        The status code of the HTTP request.
    code: Union[:class:`.EResult`, :class:`int`]
        The Steam specific error code for the failure.
        It will attempt to find a matching a :class:`.EResult` for the value.
    """

    def __init__(self, response: "ClientResponse", data: Optional[Any]):
        self.response = response
        self.status = response.status
        self.code = 0
        self.message = ""

        if data:
            if isinstance(data, dict):
                if len(data) != 1 and data.get("success", False):  # ignore {'success': False} as the message
                    message = data.get("message") or str(list(data.values())[0])
                    code = data.get("result") or CODE_FINDER.findall(message)
                    if code:
                        self.code = EResult.try_value(int(code[0]))
                    self.message = CODE_FINDER.sub("", message)
            else:
                text = BeautifulSoup(data, "html.parser").get_text("\n")
                self.message = text if text else ""

        self.message = self.message.replace("  ", " ")
        super().__init__(
            f"{response.status} {response.reason} (error code: {self.code})"
            f'{f": {self.message}" if self.message else ""}'
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
    """Exception that's thrown for any web API error.

    Subclass of :exc:`SteamException`.

    Attributes
    ------------
    msg: Union[:class:`~steam.protobufs.MsgProto`, :class:`~steam.protobufs.Msg`]
        The received protobuf.
    code: Union[:class:`~steam.EResult`, :class:`int`]
        The Steam specific error code for the failure.
        It will attempt to find a matching a :class:`~steam.EResult` for the value.
    """

    def __init__(self, msg: "MsgProto"):
        self.msg = msg
        self.code = EResult.try_value(msg.header.eresult)
        super().__init__(f"The request {msg.header.job_name_target} failed. (error code: {repr(self.code)})")


class WSForbidden(WSException):
    """Exception that's thrown when the websocket returns
    an :class:`.EResult` that means we do not have permission
    to perform an action.
    Similar to :exc:`Forbidden`.

    Subclass of :exc:`WSException`.
    """


class WSNotFound(WSException):
    """Exception that's thrown when the websocket returns
    an :class:`.EResult` that means the object wasn't found.
    Similar to :exc:`NotFound`.

    Subclass of :exc:`WSException`.
    """


class LoginError(ClientException):
    """Exception that's thrown when a login fails.

    Subclass of :exc:`ClientException`.
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
    """

    def __init__(self, id: Any, msg: Optional[str] = None):
        self.id = id
        super().__init__(
            f"{id!r} cannot be converted to any valid SteamID {f'as {msg}' if msg is not None else ''}".strip()
        )
