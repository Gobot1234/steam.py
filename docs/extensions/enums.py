import inspect
from typing import Any

import sphinx.util.inspect as _inspect

from ...steam import Enum


# we can monkey patch in the enum checks to get them to doc properly


def _isenumclass(x: Any) -> bool:
    """Check if the object is subclass of enum."""
    return inspect.isclass(x) and issubclass(x, Enum)


def _isenumattribute(x: Any) -> bool:
    """Check if the object is attribute of enum."""
    return isinstance(x, Enum)


_inspect.isenumclass = _isenumclass
_inspect.isenumattribute = _isenumattribute
