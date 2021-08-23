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

from __future__ import annotations

from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any

from ...abc import Channel, Message, Messageable

if TYPE_CHECKING:
    from datetime import datetime

    from ...clan import Clan
    from ...group import Group
    from ...image import Image
    from ...iterators import AsyncIterator
    from ...state import ConnectionState
    from ...user import User
    from .bot import Bot
    from .cog import Cog
    from .commands import Command
    from .utils import Shlex


__all__ = ("Context",)


class Context(Messageable["Message"]):
    """Represents the context of a command.

    Attributes
    ----------
    message
        The message the context was generated from.
    prefix
        The prefix of the message the context was generated from
    author
        The author of the message.
    channel
        The channel the message was sent in.
    clan
        The clan the message was sent in ``None`` if the message wasn't sent in a clan.
    group
        The group the message was sent in ``None`` if the message wasn't sent in a group.
    bot
        The bot instance.
    command
        The command the context is attached to.
    cog
        The cog the command is in.
    """

    def __init__(self, **attrs: Any):
        self.bot: Bot = attrs["bot"]
        self.message: Message = attrs["message"]
        self.lex: Shlex = attrs["lex"]
        self.prefix: str | None = attrs["prefix"]

        self.command: Command | None = attrs.get("command")
        self.cog: Cog | None = self.command.cog if self.command is not None else None
        self.invoked_with: str | None = attrs.get("invoked_with")

        self.author: User = self.message.author
        self.channel: Channel[Message] = self.message.channel
        self.clan: Clan | None = self.message.clan
        self.group: Group | None = self.message.group
        self._state: ConnectionState = self.message._state

        self.args: tuple[Any, ...] | None = None
        self.kwargs: dict[str, Any] | None = None
        self.command_failed: bool = False

    def _message_func(self, content: str) -> Coroutine[Any, Any, Message]:
        return self.channel._message_func(content)

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self.channel._image_func(image)

    async def invoke(self) -> None:
        """A shortcut method that invokes the current context using :meth:`~steam.ext.commands.Command.invoke`.

        Equivalent to

        .. code-block:: python3

            await ctx.command.invoke(ctx)
        """
        await self.command.invoke(self)

    def history(
        self,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncIterator[Message]:
        """A shortcut method that gets the current channel's history.

        Equivalent to

        .. code-block:: python3

            ctx.channel.history(**kwargs)
        """
        return self.channel.history(limit=limit, before=before, after=after)

    @property
    def valid(self) -> bool:
        """Whether or not the context could be invoked."""
        return self.prefix is not None and self.command is not None
