import inspect as _inspect
from typing import Any

from sphinx.util import inspect as inspect

from steam import Enum

# we can monkey patch in the enum checks to get them to be documented properly


def _isenumclass(x: Any) -> bool:
    """Check if the object is subclass of enum."""
    return _inspect.isclass(x) and issubclass(x, Enum)


def _isenumattribute(x: Any) -> bool:
    """Check if the object is attribute of enum."""
    return isinstance(x, Enum)


inspect.isenumclass = _isenumclass
inspect.isenumattribute = _isenumattribute


def setup(_):  # stop sphinx complaining when docs are built
    pass
