# -*- coding: utf-8 -*-

"""
steam.py
~~~~~~~~~~~~~
A basic wrapper for the Steam API and its Community Managers.

:copyright: (c) 2020 James.
:license: MIT, see LICENSE for more details.
"""

__title__ = "steam"
__author__ = "Gobot1234"
__license__ = "MIT"
__version__ = "0.4.0"

import logging
from typing import NamedTuple

from . import abc, guard, utils
from .abc import *
from .badge import *
from .channel import *
from .clan import *
from .client import *
from .comment import *
from .enums import *
from .errors import *
from .game import *
from .group import *
from .image import *
from .invite import *
from .message import *
from .models import *
from .role import *
from .trade import *
from .user import *


class VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: str


version_info = VersionInfo(major=0, minor=4, micro=0, releaselevel="full")

logging.getLogger(__name__).addHandler(logging.NullHandler())

# not for export
del logging, NamedTuple, VersionInfo
