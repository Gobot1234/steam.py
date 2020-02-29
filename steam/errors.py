class SteamException(Exception):
    """Base exception class for steam.py"""
    pass


class ClientException(SteamException):
    """Exception that's thrown when something isn't possible
    but is handled by the client.
    Subclass of :exc:`SteamException`
    """


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
    """Exception that's thrown when a 429 is received.
    Subclass of :exc:`HTTPException`
    """
    pass


class LoginError(HTTPException):
    """Exception that's thrown when a login fails.
    Subclass of :exc:`HTTPException`
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
