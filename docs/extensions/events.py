# -*- coding: utf-8 -*-

# If you are wondering why this is done, it is for events that don't exist at runtime as they are wrapped in a
# TYPE_CHECKING block to be able to be picked up by Sphinx.

import importlib
import typing

import steam
from steam.ext import commands

typing.TYPE_CHECKING = True
importlib.reload(steam.client)
importlib.reload(commands.bot)
typing.TYPE_CHECKING = False


def setup(_):
    steam.Client = steam.client.Client
    commands.Bot = commands.bot.Bot
