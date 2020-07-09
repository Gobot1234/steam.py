# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ...abc import Message, Messageable

if TYPE_CHECKING:
    from shlex import shlex as Shlex

    from ...image import Image
    from .bot import Bot
    from .command import Command


__all__ = ("Context",)


class Context(Messageable):
    """Represents the context of a message.

    Attributes
    ----------
    message: :class:`~steam.Message`
        The message the context was generated from.
    prefix: :class:`str`
        The prefix of the message the context was generated from
    author: :class:`~steam.abc.BaseUser`
        The author of the message.
    channel: :class:`~steam.abc.BaseChannel`
        The channel the message was sent in.
    clan: Optional[:class:`~steam.Clan`]
        The clan the message was sent in ``None`` if the
        message wasn't sent in a clan.
    group: Optional[:class:`~steam.Group`]
        The group the message was sent in ``None`` if the
        message wasn't sent in a group.
    bot: :class:`~steam.ext.commands.Bot`
        The bot instance.
    command: Optional[:class:`~steam.ext.commands.Command`]
        The command the context is attached to.
    cog: Optional[:class:`~steam.ext.commands.Cog`]
        The cog the command is in.
    """

    def __init__(
        self, bot: "Bot", message: Message, prefix: str, command: "Command" = None, shlex: "Shlex" = None, **attrs
    ):
        self.bot = bot
        self.message = message
        self.command = command
        self.shlex = shlex
        self.prefix = prefix
        self.author = message.author
        self.channel = message.channel
        self.clan = message.clan
        self.group = message.group
        self.invoked_with: Optional[str] = attrs.get("invoked_with")

        self._state = message._state

        if command is not None:
            self.cog = command.cog
        self.args: Optional[List] = None
        self.kwargs: Optional[Dict[str, Any]] = None

    async def send(self, content: str = None, *, image: "Image" = None):
        return await self.channel.send(content=content, image=image)
