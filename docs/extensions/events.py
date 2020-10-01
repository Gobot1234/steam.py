# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is for events that don't exist at runtime as they are wrapped in a
# TYPE_CHECKING block to be able to be picked up by Sphinx.

import importlib

import steam
from steam.ext import commands

client = importlib.import_module("steam.client")
bot = importlib.import_module("steam.ext.commands.bot")

commands.utils.reload_module_with_TYPE_CHECKING(client)
commands.utils.reload_module_with_TYPE_CHECKING(bot)


def setup(_) -> None:
    steam.client = client
    steam.Client = client.Client
    commands.bot = bot
    commands.Bot = bot.Bot
