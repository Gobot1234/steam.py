# -*- coding: utf-8 -*-

"""
steam.py
~~~~~~~~~~~~~~~~~~~
A basic wrapper for the Steam API and Web UI.

:copyright: (c) 2020
:license: MIT, see LICENSE for more details.
"""

__title__ = 'steam'
__author__ = 'Gobot1234'
__license__ = 'MIT'
__version__ = '0.0.7a'

from logging import NullHandler

from . import guard
from .client import Client
from .enums import *
from .errors import *
from .market import *
from .trade import *
from .user import *

logging.getLogger(__name__).addHandler(NullHandler())
