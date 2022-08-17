"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ._const import MISSING, UNIX_EPOCH
from .abc import Channel
from .chat import Chat, GroupChannelProtos
from .message import ClanMessage, GroupMessage, Message, UserMessage
from .reaction import Emoticon, MessageReaction, Sticker
from .utils import DateTime

if TYPE_CHECKING:
    from .clan import Clan
    from .group import Group
    from .image import Image
    from .protobufs import friend_messages
    from .state import ConnectionState
    from .user import User

__all__ = (
    "DMChannel",
    "GroupChannel",
    "ClanChannel",
)


class DMChannel(Channel[UserMessage]):  # TODO cache these to add last_message.
    """Represents the channel a DM is sent in.

    Attributes
    ----------
    participant
        The recipient of any messages sent.
    """

    __slots__ = ("participant",)
    clan: None
    group: None

    def __init__(self, state: ConnectionState, participant: User):
        super().__init__(state)
        self.participant = participant
        self.clan = None
        self.group = None

    def __repr__(self) -> str:
        return f"<DMChannel participant={self.participant!r}>"

    def __eq__(self, other: object) -> bool:
        return self.participant == other.participant if isinstance(other, DMChannel) else NotImplemented

    def _message_func(self, content: str) -> Coroutine[Any, Any, UserMessage]:
        return self.participant._message_func(content)

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self.participant._image_func(image)

    @asynccontextmanager
    async def typing(self) -> AsyncGenerator[None, None]:
        """Send a typing indicator continuously to the channel while in the context manager.

        Note
        ----
        This only works in DMs.

        Usage:

        .. code-block:: python3

            async with channel.typing():
                ...  # do your expensive operations
        """

        async def inner() -> None:
            while True:
                await asyncio.sleep(10)
                await self.trigger_typing()

        await self.trigger_typing()
        task = self._state.loop.create_task(inner())
        yield
        task.cancel()

    async def trigger_typing(self) -> None:
        """Send a typing indicator to the channel once.

        Note
        ----
        This only works in DMs.
        """
        await self._state.send_user_typing(self.participant.id64)

    async def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime = MISSING,
        after: datetime = MISSING,
    ) -> AsyncGenerator[UserMessage, None]:
        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        after_timestamp = int(after.timestamp())
        before_timestamp = int(before.timestamp())
        yielded = 0

        last_message_timestamp = before_timestamp
        ordinal = 0

        while True:
            resp = await self._state.fetch_user_history(
                self.participant.id64, start=after_timestamp, last=last_message_timestamp, start_ordinal=ordinal
            )

            message: friend_messages.GetRecentMessagesResponseFriendMessage | None = None

            for message in resp.messages:
                new_message = UserMessage.__new__(UserMessage)
                new_message.created_at = DateTime.from_timestamp(message.timestamp)
                if not after < new_message.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return

                Message.__init__(new_message, channel=self, proto=message)
                new_message.author = self.participant if message.accountid == self.participant.id else self._state.user
                emoticon_reactions = [
                    MessageReaction(
                        self._state,
                        new_message,
                        Emoticon(self._state, r.reaction),
                        None,
                        self.participant if reactor == self.participant.id else self._state.user,
                    )
                    for r in message.reactions
                    if r.reaction_type == 1
                    for reactor in r.reactors
                ]
                sticker_reactions = [
                    MessageReaction(
                        self._state,
                        new_message,
                        None,
                        Sticker(self._state, r.reaction),
                        self.participant if reactor == self.participant.id else self._state.user,
                    )
                    for r in message.reactions
                    if r.reaction_type == 2
                    for reactor in r.reactors
                ]
                new_message.reactions = emoticon_reactions + sticker_reactions

                yield new_message
                yielded += 1

            if message is None:
                return

            last_message_timestamp = message.timestamp
            ordinal = message.ordinal

            if not resp.more_available:
                return


class GroupChannel(Chat[GroupMessage]):
    """Represents a group channel.

    Attributes
    ----------
    id
        The ID of the channel.
    name
        The name of the channel, this could be the same as the :attr:`~steam.Group.name` if it's the main channel.
    group
        The group to which messages are sent.
    joined_at
        The time the client joined the chat.
    position
        The position of the channel in the channel list.
    last_message
        The last message sent in the channel.
    """

    clan: None

    def __init__(self, state: ConnectionState, group: Group, proto: GroupChannelProtos):
        super().__init__(state, group, proto)
        self.group: Group = group

    def _message_func(self, content: str) -> Coroutine[Any, Any, GroupMessage]:
        return self._state.send_chat_message(*self._location, content)  # type: ignore

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_chat_image(*self._location, image)


class ClanChannel(Chat[ClanMessage]):
    """Represents a group channel.

    Attributes
    ----------
    id
        The ID of the channel.
    name
        The name of the channel, this could be the same as the :attr:`~steam.Clan.name` if it's the main channel.
    clan
        The clan to which messages are sent.
    joined_at
        The time the client joined the chat.
    position
        The position of the channel in the channel list.
    last_message
        The last message sent in the channel.
    """

    group: None

    def __init__(self, state: ConnectionState, clan: Clan, proto: GroupChannelProtos):
        super().__init__(state, clan, proto)
        self.clan: Clan = clan

    def _message_func(self, content: str) -> Coroutine[Any, Any, ClanMessage]:
        return self._state.send_chat_message(*self._location, content)  # type: ignore

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_chat_image(*self._location, image)
