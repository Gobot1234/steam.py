class SteamException(Exception):
    """Base exception class for steam.py"""
    pass


class HTTPException(SteamException):
    """Exception that's thrown for any web API error.
    Subclass of :exc:`SteamException`
    """
    pass


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


class TooManyRequests(HTTPException):
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
    """Exception that's thrown when steam guard loading fails.
    Subclass of :exc:`LoginError`
    """
    pass
