"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import TypeVar

from .abc import Message, PartialUser
from .chat import ChatMessage, PartialMember
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


UserMessageAuthorT = TypeVar(
    "UserMessageAuthorT", bound=PartialUser, default="PartialUser | User | ClientUser", covariant=True
)


class UserMessage(Message[UserMessageAuthorT]):
    """Represents a message from a user."""

    channel: DMChannel
    mentions: None

    def __init__(
        self, proto: friend_messages.IncomingMessageNotification, channel: DMChannel, author: UserMessageAuthorT
    ):
        super().__init__(channel, proto)
        self.created_at = DateTime.from_timestamp(proto.rtime32_server_timestamp)
        self.author = author

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


GroupMessageAuthorT = TypeVar(
    "GroupMessageAuthorT", bound="PartialMember", default="PartialMember | GroupMember", covariant=True
)


class GroupMessage(ChatMessage[GroupMessageAuthorT]):
    """Represents a message in a group."""

    author: GroupMember
    channel: GroupChannel
    group: Group
    clan: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: GroupChannel, author: GroupMessageAuthorT):
        super().__init__(proto, channel, author)


ClanMessageAuthorT = TypeVar(
    "ClanMessageAuthorT", bound="PartialMember", default="PartialMember | ClanMember", covariant=True
)


class ClanMessage(ChatMessage[ClanMessageAuthorT]):
    """Represents a message in a clan."""

    author: ClanMember
    channel: ClanChannel
    clan: Clan
    group: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ClanChannel, author: ClanMessageAuthorT):
        super().__init__(proto, channel, author)
