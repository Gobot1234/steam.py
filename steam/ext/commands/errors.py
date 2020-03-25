from ...errors import SteamException

__all__ = ('CommandError', 'CommandNotFound', 'MissingRequiredArgument', 'BadArgument', 'CheckFailure')


class CommandError(SteamException):
    """Base Exception for errors raised by commands."""
    pass


class CommandNotFound(CommandError):
    """Exception raised when a command is not found."""
    pass


class CheckFailure(CommandError):
    """Exception raised when a check fails."""
    pass


class MissingRequiredArgument(CommandError):
    """Exception raised when a required argument is not passed to a command.

    Attributes
    ----------
    param: :class:`inspect.Parameter`
        The argument that is missing.
    """

    def __init__(self, param):
        self.param = param
        super().__init__(f'{param.name} is a required argument that is missing.')


class BadArgument(CommandError):
    """Exception raised when a bad argument is passed to a command."""
    pass
