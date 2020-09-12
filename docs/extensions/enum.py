# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is to make Sphinx think that our Enums are enum.Enum subclasses which makes
# documenting them a whole lot nicer

import inspect as _inspect
from typing import Any

from sphinx.util import inspect

from steam import Enum


def isenumclass(x: Any) -> bool:
    """Check if the object is subclass of enum."""
    return _inspect.isclass(x) and issubclass(x, Enum)


def isenumattribute(x: Any) -> bool:
    """Check if the object is attribute of enum."""
    return isinstance(x, Enum)


inspect.isenumclass = isenumclass
inspect.isenumattribute = isenumattribute
