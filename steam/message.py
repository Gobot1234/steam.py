"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import TypeAlias

from .abc import Message, SteamID
from .chat import ChatMessage
from .reaction import Emoticon, MessageReaction, Sticker
from .utils import DateTime

if TYPE_CHECKING:
    from .channel import ClanChannel, DMChannel, GroupChannel
    from .clan import Clan
    from .group import Group
    from .protobufs import chat, friend_messages
    from .user import ClientUser, User


__all__ = (
    "UserMessage",
    "GroupMessage",
    "ClanMessage",
)

Authors: TypeAlias = "User | ClientUser | SteamID"


class UserMessage(Message):
    """Represents a message from a user."""

    channel: DMChannel
    mentions: None

    def __init__(self, proto: friend_messages.IncomingMessageNotification, channel: DMChannel):
        super().__init__(channel, proto)
        self.author = channel.participant
        self.created_at = DateTime.from_timestamp(proto.rtime32_server_timestamp)

    async def add_emoticon(self, emoticon: Emoticon) -> None:
        await self._state.react_to_user_message(
            self.author.id64,
            int(self.created_at.timestamp()),
            self.ordinal,
            emoticon.name,
            reaction_type=1,
            is_add=True,
        )
        self._state.dispatch(
            "reaction_add",
            MessageReaction(self._state, self, emoticon, None, self._state.user, DateTime.now(), self.ordinal),
        )

    async def remove_emoticon(self, emoticon: Emoticon):
        await self._state.react_to_user_message(
            self.author.id64,
            int(self.created_at.timestamp()),
            self.ordinal,
            emoticon.name,
            reaction_type=1,
            is_add=False,
        )
        self._state.dispatch(
            "reaction_remove",
            MessageReaction(self._state, self, emoticon, None, self._state.user, DateTime.now(), self.ordinal),
        )

    async def add_sticker(self, sticker: Sticker):
        await self._state.react_to_user_message(
            self.author.id64,
            int(self.created_at.timestamp()),
            self.ordinal,
            sticker.name,
            reaction_type=2,
            is_add=True,
        )
        self._state.dispatch(
            "reaction_add",
            MessageReaction(self._state, self, None, sticker, self._state.user, DateTime.now(), self.ordinal),
        )

    async def remove_sticker(self, sticker: Sticker):
        await self._state.react_to_user_message(
            self.author.id64,
            int(self.created_at.timestamp()),
            self.ordinal,
            sticker.name,
            reaction_type=2,
            is_add=False,
        )
        self._state.dispatch(
            "reaction_remove",
            MessageReaction(self._state, self, None, sticker, self._state.user, DateTime.now(), self.ordinal),
        )


class GroupMessage(ChatMessage):
    """Represents a message in a group."""

    channel: GroupChannel
    group: Group
    clan: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: GroupChannel, author: Authors):
        super().__init__(proto, channel, author)


class ClanMessage(ChatMessage):
    """Represents a message in a clan."""

    channel: ClanChannel
    clan: Clan
    group: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ClanChannel, author: Authors):
        super().__init__(proto, channel, author)
