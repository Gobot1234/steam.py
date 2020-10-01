# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is to make Sphinx think that our Enums are enum.Enum subclasses which makes
# documenting them a whole lot easier

from typing import Any

from sphinx.util import inspect

from steam import Enum

OLD_IS_ENUM_CLASS = inspect.isenumclass
OLD_IS_ENUM_MEMBER = inspect.isenumattribute


def isenumclass(x: Any) -> bool:
    """Check if the object is subclass of Enum."""
    return isinstance(x, type) and issubclass(x, Enum) or OLD_IS_ENUM_CLASS(x)


def isenumattribute(x: Any) -> bool:
    """Check if the object is attribute of enum."""
    return isinstance(x, Enum) or OLD_IS_ENUM_MEMBER(x)


def setup(_) -> None:
    inspect.isenumclass = isenumclass
    inspect.isenumattribute = isenumattribute
