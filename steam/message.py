"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import TypeVar

from .abc import BaseUser, Message
from .chat import ChatMessage, PartialMember
from .reaction import Emoticon, MessageReaction, Sticker
from .utils import DateTime

if TYPE_CHECKING:
    from .channel import ClanChannel, GroupChannel, UserChannel
    from .clan import Clan, ClanMember
    from .friend import Friend
    from .group import Group, GroupMember
    from .protobufs import chat, friend_messages
    from .user import ClientUser, User


__all__ = (
    "UserMessage",
    "GroupMessage",
    "ClanMessage",
)


UserMessageAuthorT = TypeVar("UserMessageAuthorT", bound=BaseUser, default="User | Friend | ClientUser", covariant=True)


class UserMessage(Message[UserMessageAuthorT]):
    """Represents a message from a user."""

    __slots__ = ()

    channel: UserChannel
    mentions: None

    def __init__(
        self, proto: friend_messages.IncomingMessageNotification, channel: UserChannel, author: UserMessageAuthorT
    ):
        super().__init__(channel, proto)
        self.created_at = DateTime.from_timestamp(proto.rtime32_server_timestamp)
        self.author = author

    async def _react(self, emoticon: Emoticon | Sticker, add: bool) -> None:
        await self._state.react_to_user_message(
            self.author.id64,
            int(self.created_at.timestamp()),
            self.ordinal,
            str(emoticon) if isinstance(emoticon, Emoticon) else emoticon.name,
            reaction_type=emoticon._TYPE,
            is_add=True,
        )
        reaction = MessageReaction(
            self._state,
            self,
            emoticon if isinstance(emoticon, Emoticon) else None,
            emoticon if isinstance(emoticon, Sticker) else None,
            self._state.user,
            DateTime.now(),
            self.ordinal,
        )
        if add:
            self.reactions.append(reaction)
        else:
            self.reactions.remove(reaction)
        self._state.dispatch(f"reaction_{'add' if add else 'remove'}", reaction)

    async def add_emoticon(self, emoticon: Emoticon) -> None:
        await self._react(emoticon, True)

    async def remove_emoticon(self, emoticon: Emoticon):
        await self._react(emoticon, False)

    async def add_sticker(self, sticker: Sticker):
        await self._react(sticker, True)

    async def remove_sticker(self, sticker: Sticker):
        await self._react(sticker, False)

    async def ack(self) -> None:
        await self._state.ack_user_message(self.channel.participant.id64, int(self.created_at.timestamp()))


GroupMessageAuthorT = TypeVar(
    "GroupMessageAuthorT", bound="PartialMember", default="PartialMember | GroupMember", covariant=True
)


class GroupMessage(ChatMessage[GroupMessageAuthorT, "GroupMember"]):
    """Represents a message in a group."""

    __slots__ = ()

    channel: GroupChannel
    group: Group
    clan: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: GroupChannel, author: GroupMessageAuthorT):
        super().__init__(proto, channel, author)


ClanMessageAuthorT = TypeVar(
    "ClanMessageAuthorT", bound="PartialMember", default="PartialMember | ClanMember", covariant=True
)


class ClanMessage(ChatMessage[ClanMessageAuthorT, "ClanMember"]):
    """Represents a message in a clan."""

    __slots__ = ()

    channel: ClanChannel
    clan: Clan
    group: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ClanChannel, author: ClanMessageAuthorT):
        super().__init__(proto, channel, author)
