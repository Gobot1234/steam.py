# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is for events that don't exist at runtime as they are wrapped in a
# TYPE_CHECKING block to be able to be picked up by Sphinx.

import importlib

from steam.ext.commands import utils

client = importlib.import_module("steam.client")
bot = importlib.import_module("steam.ext.commands.bot")

utils.reload_module_with_TYPE_CHECKING(client)
utils.reload_module_with_TYPE_CHECKING(bot)
