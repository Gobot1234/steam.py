"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from .abc import Message
from .chat import ChatMessage
from .id import ID
from .reaction import Emoticon, MessageReaction, Sticker
from .utils import DateTime

if TYPE_CHECKING:
    from .channel import ClanChannel, DMChannel, GroupChannel
    from .clan import Clan, ClanMember
    from .group import Group, GroupMember
    from .protobufs import chat, friend_messages
    from .user import ClientUser, User


__all__ = (
    "UserMessage",
    "GroupMessage",
    "ClanMessage",
)

Authors: TypeAlias = "User | ClientUser | ID"


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
            reaction_type=emoticon._TYPE,
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
            reaction_type=emoticon._TYPE,
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
            reaction_type=sticker._TYPE,
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
            reaction_type=sticker._TYPE,
            is_add=False,
        )
        self._state.dispatch(
            "reaction_remove",
            MessageReaction(self._state, self, None, sticker, self._state.user, DateTime.now(), self.ordinal),
        )


class GroupMessage(ChatMessage):
    """Represents a message in a group."""

    author: GroupMember
    channel: GroupChannel
    group: Group
    clan: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: GroupChannel, author: Authors):
        super().__init__(proto, channel, author)


class ClanMessage(ChatMessage):
    """Represents a message in a clan."""

    author: ClanMember
    channel: ClanChannel
    clan: Clan
    group: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ClanChannel, author: Authors):
        super().__init__(proto, channel, author)
