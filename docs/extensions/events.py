# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is for events that don't exist at runtime as they are wrapped in a
# TYPE_CHECKING block to be able to be picked up by Sphinx.

import importlib
import inspect

import steam
from steam.ext import commands

client = importlib.import_module("steam.client")
bot = importlib.import_module("steam.ext.commands.bot")

commands.utils.reload_module_with_TYPE_CHECKING(client)
commands.utils.reload_module_with_TYPE_CHECKING(bot)

OLD_GETATTR_STATIC = inspect.getattr_static


def getattr_static(obj, attr, default=inspect._sentinel):
    if obj is steam.Client:
        return OLD_GETATTR_STATIC(client.Client, attr, default)
    elif obj is commands.Bot:
        return OLD_GETATTR_STATIC(bot.Bot, attr, default)
    return OLD_GETATTR_STATIC(obj, attr, default)


inspect.getattr_static = getattr_static
