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

from bs4 import BeautifulSoup

from .enums import EResult

__all__ = (
    'SteamException',
    'NotFound',
    'Forbidden',
    'LoginError',
    'NoCMsFound',
    'HTTPException',
    'ClientException',
    'ConfirmationError',
    'AuthenticatorError',
    'InvalidCredentials',
)

CODE_FINDER = re.compile(r'[^\s]([0-9]+)[^\s]')


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
    code: Union[:class:`~steam.EResult`, :class:`int`]
        The Steam specific error code for the failure.
        It will attempt to find a matching a :class:`~steam.EResult` for the value.
    """

    def __init__(self, response, data):
        self.response = response
        self.status = response.status
        self.code = 0
        self.message = ''

        if data:
            if isinstance(data, dict):
                message = data.get('message') or str(list(data.values())[0])
                code = data.get('result') or CODE_FINDER.findall(message)
                if code:
                    self.code = EResult.try_value(int(code[0]))
                    self.message = CODE_FINDER.sub('', message)
            else:
                text = BeautifulSoup(data, 'html.parser').get_text('\n')
                self.message = text if text else ''

        self.message = self.message.replace('  ', ' ')
        super().__init__(f'{response.status} {response.reason} (error code: {self.code})'
                         f'{f" Message: {self.message}" if self.message else ""}')


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


class LoginError(ClientException):
    """Exception that's thrown when a login fails.
    Subclass of :exc:`ClientException`
    """
    pass


class InvalidCredentials(LoginError):
    """Exception that's thrown when credentials are incorrect.
    Subclass of :exc:`LoginError`
    """
    pass


class AuthenticatorError(ClientException):
    """Exception that's thrown when Steam cannot authenticate your details.
    Subclass of :exc:`LoginError`
    """
    pass


class ConfirmationError(AuthenticatorError):
    """Exception that's thrown when a confirmation fails.
    Subclass of :exc:`AuthenticatorError`
    """
    pass


class NoCMsFound(LoginError):
    """Exception that's thrown when no CMs can be found to connect to.
    Subclass of :exc:`LoginError`
    """
    pass
