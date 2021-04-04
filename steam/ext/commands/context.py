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

from typing import TYPE_CHECKING, Any, Optional

from ...abc import Channel, Message, Messageable, _EndPointReturnType

if TYPE_CHECKING:
    from datetime import datetime

    from ...clan import Clan
    from ...group import Group
    from ...iterators import AsyncIterator
    from ...state import ConnectionState
    from ...user import User
    from .bot import Bot
    from .cog import Cog
    from .commands import Command
    from .utils import Shlex


__all__ = ("Context",)


class Context(Messageable):
    """Represents the context of a command.

    Attributes
    ----------
    message: :class:`~steam.Message`
        The message the context was generated from.
    prefix: :class:`str`
        The prefix of the message the context was generated from
    author: :class:`~steam.User`
        The author of the message.
    channel: :class:`~steam.Channel`
        The channel the message was sent in.
    clan: Optional[:class:`~steam.Clan`]
        The clan the message was sent in ``None`` if the message wasn't sent in a clan.
    group: Optional[:class:`~steam.Group`]
        The group the message was sent in ``None`` if the message wasn't sent in a group.
    bot: :class:`~steam.ext.commands.Bot`
        The bot instance.
    command: Optional[:class:`~steam.ext.commands.Command`]
        The command the context is attached to.
    cog: Optional[:class:`~steam.ext.commands.Cog`]
        The cog the command is in.
    """

    def __init__(self, **attrs: Any):
        self.bot: Bot = attrs["bot"]
        self.message: Message = attrs["message"]
        self.prefix: str = attrs["prefix"]

        self.command: Optional[Command] = attrs.get("command")
        self.cog: Optional[Cog] = self.command.cog if self.command is not None else None
        self.lex: Optional[Shlex] = attrs.get("lex")
        self.invoked_with: Optional[str] = attrs.get("invoked_with")

        self.author: User = self.message.author
        self.channel: Channel = self.message.channel
        self.clan: Clan = self.message.clan
        self.group: Group = self.message.group
        self._state: ConnectionState = self.message._state

        self.args: Optional[tuple[Any, ...]] = None
        self.kwargs: Optional[dict[str, Any]] = None
        self.command_failed: bool = False

    def _get_message_endpoint(self) -> _EndPointReturnType:
        return self.channel._get_message_endpoint()

    def _get_image_endpoint(self) -> _EndPointReturnType:
        return self.channel._get_image_endpoint()

    async def invoke(self) -> None:
        """|coro|
        A shortcut method that invokes the current context using :meth:`~steam.ext.commands.Command.invoke`.

        Equivalent to::

            await ctx.command.invoke(ctx)
        """
        await self.command.invoke(self)

    def history(
        self,
        limit: Optional[int] = 100,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> AsyncIterator[Message]:
        """|coro|
        A shortcut method that gets the current channel's history.

        Equivalent to::

            return ctx.channel.history(**kwargs)
        """
        return self.channel.history(limit=limit, before=before, after=after)

    @property
    def valid(self) -> bool:
        """:class:`bool`: Whether or not the context could be invoked."""
        return self.prefix is not None and self.command is not None
