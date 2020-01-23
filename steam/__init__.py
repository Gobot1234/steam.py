# -*- coding: utf-8 -*-

import logging

__title__ = 'steam'
__author__ = 'Gobot1234'
__license__ = 'MIT'
__version__ = '0.0.1a'


from .utils import *
from .errors import *
from .client import Client


try:
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.getLogger(__name__).addHandler(NullHandler())
