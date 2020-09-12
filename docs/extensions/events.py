# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is for events that don't exist at runtime as they are wrapped in a
# TYPE_CHECKING block to be able to be picked up by Sphinx.

import importlib
from typing import Any

from sphinx.util import inspect

import steam
from steam.ext import commands

client = importlib.import_module("steam.client")
bot = importlib.import_module("steam.ext.commands.bot")

commands.utils.reload_module_with_TYPE_CHECKING(client)
commands.utils.reload_module_with_TYPE_CHECKING(bot)

OLD_SAFE_GETATTR = inspect.safe_getattr


def safe_getattr(obj: Any, name: str, *defargs: Any) -> Any:
    """A getattr() that turns all exceptions into AttributeErrors."""
    if obj is steam.Client:
        return OLD_SAFE_GETATTR(client.Client, name, *defargs)
    elif obj is commands.Bot:
        return OLD_SAFE_GETATTR(bot.Bot, name, *defargs)
    return OLD_SAFE_GETATTR(obj, name, *defargs)


inspect.safe_getattr = safe_getattr
