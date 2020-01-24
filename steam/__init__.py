# -*- coding: utf-8 -*-

__title__ = 'steam'
__author__ = 'Gobot1234'
__license__ = 'MIT'
__version__ = '0.0.1a'


from .client import Client
from .errors import *
from .market import *
from .utils import *


try:
    from logging import NullHandler
except ImportError:
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass

logging.getLogger(__name__).addHandler(NullHandler())
