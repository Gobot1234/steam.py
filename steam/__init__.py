"""
steam.py
~~~~~~~~~

A basic wrapper for the Steam API and its Community Managers.
"""

from . import abc as abc, guard as guard, utils as utils
from .__metadata__ import *
from .abc import *
from .badge import *
from .channel import *
from .clan import *
from .client import *
from .comment import *
from .enums import *
from .errors import *
from .event import *
from .game import *
from .game_server import *
from .group import *
from .image import *
from .invite import *
from .message import *
from .models import *
from .profile import *
from .role import *
from .trade import *
from .user import *

__import__("logging").getLogger(__name__).addHandler(__import__("logging").NullHandler())  # don't leak scope
__import__("warnings").filterwarnings("always", ".*", module=rf"{__name__}(.\w+)+", append=False)

__getattr__ = enums.__getattr__  # shim for old enum names
