"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import TypeVar

from ..._const import _HasChatGroupMixin
from ...abc import Message, Messageable, PartialUser

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine
    from datetime import datetime
    from inspect import Parameter

    from ...chat import Member, PartialMember
    from ...friend import Friend
    from ...media import Media
    from ...user import ClientUser, User
    from .bot import Bot
    from .commands import Command
    from .utils import Shlex


__all__ = ("Context",)

BotT = TypeVar("BotT", bound="Bot", default="Bot", covariant=True)


class Context(Generic[BotT], Messageable["Message"], _HasChatGroupMixin):
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

    def __init__(
        self,
        bot: BotT,
        message: Message[User | ClientUser | Friend | Member | PartialMember],
        lex: Shlex,
        prefix: str | None,
        command: Command | None = None,
        invoked_with: str | None = None,
    ):
        self.bot = bot
        self.message = message
        self.lex = lex
        self.prefix = prefix

        self.command = command
        self.cog = self.command.cog if self.command is not None else None
        self.invoked_with = invoked_with

        self.author = self.message.author
        self.channel = self.message.channel
        self.clan = self.message.clan
        self.group = self.message.group
        self._state = self.message._state

        self.args: tuple[Any, ...] | None = None
        self.kwargs: dict[str, Any] | None = None
        self.command_failed: bool = False
        self.current_param: Parameter | None = None

    def _send_message(self, content: str) -> Coroutine[Any, Any, Message]:
        return self.channel._send_message(content)

    def _send_media(self, media: Media) -> Coroutine[Any, Any, None]:
        return self.channel._send_media(media)

    async def invoke(self) -> None:
        """A shortcut method that invokes the current context using :meth:`~steam.ext.commands.Command.invoke`.

        Equivalent to

        .. code:: python

            await ctx.command.invoke(ctx)
        """
        if self.command is None:
            return
        await self.command.invoke(self)

    def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[Message[PartialUser], None]:
        """A shortcut method that gets the current channel's history.

        Equivalent to

        .. code:: python

            ctx.channel.history(**kwargs)
        """
        return self.channel.history(limit=limit, before=before, after=after)

    @property
    def valid(self) -> bool:
        """Whether or not the context could be invoked."""
        return self.prefix is not None and self.command is not None
