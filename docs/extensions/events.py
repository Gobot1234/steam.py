# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is for events that don't exist at runtime as they are wrapped in a
# TYPE_CHECKING block to be able to be picked up by Sphinx.

import importlib
import inspect as _inspect
from typing import Any

from sphinx.application import Sphinx
from sphinx.util import inspect
from sphinx.ext import autodoc

import steam
from steam.ext import commands

client = importlib.import_module("steam.client")
bot = importlib.import_module("steam.ext.commands.bot")

commands.utils.reload_module_with_TYPE_CHECKING(client)
commands.utils.reload_module_with_TYPE_CHECKING(bot)

OLD_AUTODOC_ATTRGETTER = autodoc.autodoc_attrgetter
OLD_GETATTR_STATIC = _inspect.getattr_static


def autodoc_attrgetter(app: Sphinx, obj: Any, name: str, *defargs: Any) -> Any:
    """Alternative getattr() for types"""
    if obj is steam.Client:
        return inspect.safe_getattr(client.Client, name, *defargs)
    elif obj is commands.Bot:
        return inspect.safe_getattr(bot.Bot, name, *defargs)
    return OLD_AUTODOC_ATTRGETTER


def getattr_static(obj, attr, default=_inspect._sentinel):
    if obj is steam.Client:
        return OLD_GETATTR_STATIC(client.Client, attr, default)
    elif obj is commands.Bot:
        return OLD_GETATTR_STATIC(client.Bot, attr, default)
    return OLD_GETATTR_STATIC(obj, attr, default)


autodoc.autodoc_attrgetter = autodoc_attrgetter
_inspect.getattr_static = getattr_static
