"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from bs4 import BeautifulSoup

from ._const import HTML_PARSER
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
    "ConfirmationError",
    "AuthenticatorError",
    "InvalidCredentials",
    "WSException",
    "WSForbidden",
    "WSNotFound",
    "InvalidID",
)

CODE_FINDER = re.compile(r"\S(\d+)\S")


class SteamException(Exception):
    """Base exception class for steam.py."""


class HTTPException(SteamException):
    """Exception that's thrown for any web API error.

    Subclass of :exc:`SteamException`.
    """

    def __init__(self, response: ClientResponse, data: dict[str, Any] | Any | None):
        self.response = response
        """The response of the failed HTTP request."""
        self.status = response.status
        """The status code of the HTTP request."""
        self.code = Result.Invalid
        """The Steam specific error code for the failure."""

        if data:
            if isinstance(data, dict):
                message = data.get("message")
                if message is None and (
                    truthy_str_values := [  # ignore {'success': False} as the message
                        value for value in data.values() if value and isinstance(value, str)
                    ]
                ):
                    message = str(truthy_str_values[0])
                message = message or ""
                code = data.get("eresult")
            else:
                text = BeautifulSoup(data, HTML_PARSER).get_text("\n")
                message = text or ""
                code = None
        else:
            message = ""
            code = None

        if "X-Error_Message" in response.headers:
            message = response.headers["X-Error_Message"]

        self.message = message.replace("  ", " ").strip()
        """The message associated with the error. Could be an empty string if no message can parsed."""

        if code := (
            (code if code is not None else False)  # first the code
            or response.headers.get("X-EResult")  # then the headers
            or CODE_FINDER.findall(self.message)  # finally the message
        ):
            if isinstance(code, list):
                message = CODE_FINDER.sub("", message)
                code = code[0]
            self.code = Result.try_value(int(code))

        super().__init__(
            (
                f"{response.status} {response.reason}"  # type: ignore  # another aiohttp types bug fixed upstream
                f"(error code: {self.code}){f': {self.message}' if self.message else ''}"
            )
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
    """

    def __init__(self, msg: Msgs):
        self.msg = msg
        """The received protobuf."""
        self.code = msg.result
        """The Steam specific error code for the failure."""
        self.message: str | None = getattr(msg.header, "error_message", None)
        """The message that Steam sent back with the request, could be ``None``."""
        super().__init__(
            f"The request {msg.header.job_name_target or msg.MSG} failed. (error code: {self.code!r}){f': {self.message}' if self.message else ''}"
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


class AuthenticatorError(SteamException):
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


class InvalidID(SteamException):
    """Exception that's thrown when a Steam ID cannot be valid.

    Subclass of :exc:`SteamException`.
    """

    def __init__(self, id: Any, type: Any, universe: Any, instance: Any, msg: str | None = None):
        self.id = id
        """The invalid id."""
        self.type = type
        self.universe = universe
        self.instance = instance
        super().__init__(f"{id!r} cannot be converted to any valid Steam ID{f' as {msg}' if msg is not None else ''}")
