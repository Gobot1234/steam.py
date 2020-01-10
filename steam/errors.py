class SteamException(Exception):
    """Base exception class for steam.py"""
    pass


class HTTPException(SteamException):
    """Exception that's thrown for any web API error.
    Subclass of :exc:`SteamException`
    """
    pass


class Forbidden(HTTPException):
    """Exception that's thrown for when status code 403 occurs.
    Subclass of :exc:`HTTPException`
    """
    pass


class NotFound(HTTPException):
    """Exception that's thrown for when status code 404 occurs.
    Subclass of :exc:`HTTPException`
    """
    pass


class LoginError(SteamException):
    pass


class InvalidCredentials(LoginError):
    pass


class SteamAuthenticatorError(LoginError):
    pass
