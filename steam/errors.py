# -*- coding: utf-8 -*-

"""
MIT License

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

from bs4 import BeautifulSoup

from .enums import EResult


class SteamException(Exception):
    """Base exception class for steam.py"""
    pass


class ClientException(SteamException):
    """Exception that's thrown when something isn't possible
    but is handled by the client.
    Subclass of :exc:`SteamException`
    """
    pass


class HTTPException(SteamException):
    """Exception that's thrown for any web API error.
    Subclass of :exc:`SteamException`

    Attributes
    ------------
    response: :class:`aiohttp.ClientResponse`
        The response of the failed HTTP request.
    message: :class:`str`
        The message associated with the error.
        Could be an empty string if the message is html.
    status: :class:`int`
        The status code of the HTTP request.
    EResult: :class:`~steam.EResult`
        The associated EResult for the HTTP request.
        This is likely to be :attr:`~steam.EResult.Invalid`
    code: :class:`int`
        The Steam specific error code for the failure.
    """

    def __init__(self, response, data):
        self.response = response
        self.status = response.status
        self.EResult = EResult(int(response.headers.get('X-eresult', 0)))

        if isinstance(data, dict):
            name, message = list(data.values())
            code_regex = re.compile(r'[^\s]([0-9]+)')
            code = re.findall(code_regex, message)
            if code:
                self.code = int(code[0])  # would like to EResult however steam trades don't use the same system
                self.message = re.sub(code_regex, '', message)
            else:
                self.code = 0
                self.message = message
        else:
            if bool(BeautifulSoup(data, 'html.parser').find()):
                self.message = ''
            else:
                self.message = data
                self.code = 0

        self.message = self.message.replace('  ', ' ')
        super().__init__(f'{response.status} {response.reason} (error code: {self.code} EResult: {self.EResult})'
                         f'{f": {self.message}" if self.message else ""}')


class Forbidden(HTTPException):
    """Exception that's thrown when status code 403 occurs.
    Subclass of :exc:`HTTPException`
    """
    pass


class NotFound(HTTPException):
    """Exception that's thrown when status code 404 occurs.
    Subclass of :exc:`HTTPException`
    """
    pass


class LoginError(SteamException):
    """Exception that's thrown when a login fails.
    Subclass of :exc:`SteamException`
    """
    pass


class InvalidCredentials(LoginError):
    """Exception that's thrown when credentials are incorrect.
    Subclass of :exc:`LoginError`
    """
    pass


class SteamAuthenticatorError(LoginError):
    """Exception that's thrown when steam cannot authenticate your details.
    Subclass of :exc:`LoginError`
    """
    pass


class ConfirmationError(SteamAuthenticatorError):
    """Exception that's thrown when a confirmation fails.
    Subclass of :exc:`SteamAuthenticatorError`
    """
    pass
