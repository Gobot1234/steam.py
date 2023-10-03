"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import Self, TypeVar

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


class UserMessage(Message[UserMessageAuthorT, "UserChannel"]):
    """Represents a message from a user."""

    __slots__ = ()

    mentions: None

    def __init__(
        self, proto: friend_messages.IncomingMessageNotification, channel: UserChannel, author: UserMessageAuthorT
    ):
        super().__init__(channel, proto)
        self.created_at = DateTime.from_timestamp(proto.rtime32_server_timestamp)
        self.author = author

    async def _react(self, emoticon: Emoticon | Sticker, add: bool) -> None:
        await self._state.react_to_user_message(
            self.channel.participant.id64,
            int(self.created_at.timestamp()),
            self.ordinal,
            str(emoticon) if isinstance(emoticon, Emoticon) else emoticon.name,
            reaction_type=emoticon._TYPE,
            is_add=add,
        )
        reaction = MessageReaction(
            self._state,
            self,
            emoticon if isinstance(emoticon, Emoticon) else None,  # type: ignore
            emoticon if isinstance(emoticon, Sticker) else None,  # type: ignore
            self._state.user,
            DateTime.now(),
            self.ordinal,
        )
        if add:
            self.reactions.append(reaction)
        else:
            self.reactions.remove(reaction)
        self._state.dispatch(f"reaction_{'add' if add else 'remove'}", reaction)

    @classmethod
    def _from_history(cls, channel: UserChannel, proto: friend_messages.GetRecentMessagesResponseFriendMessage) -> Self:
        self = cls.__new__(cls)  # skip __init__
        super().__init__(self, channel, proto)
        self.created_at = DateTime.from_timestamp(proto.timestamp)
        return self

    async def ack(self) -> None:
        await self._state.ack_user_message(self.channel.participant.id64, int(self.created_at.timestamp()))


GroupMessageAuthorT = TypeVar(
    "GroupMessageAuthorT", bound="PartialMember", default="PartialMember | GroupMember", covariant=True
)


class GroupMessage(ChatMessage[GroupMessageAuthorT, "GroupMember", "GroupChannel"]):
    """Represents a message in a group."""

    __slots__ = ()

    group: Group
    clan: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: GroupChannel, author: GroupMessageAuthorT):
        super().__init__(proto, channel, author)


ClanMessageAuthorT = TypeVar(
    "ClanMessageAuthorT", bound="PartialMember", default="PartialMember | ClanMember", covariant=True
)


class ClanMessage(ChatMessage[ClanMessageAuthorT, "ClanMember", "ClanChannel"]):
    """Represents a message in a clan."""

    __slots__ = ()

    clan: Clan
    group: None

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ClanChannel, author: ClanMessageAuthorT):
        super().__init__(proto, channel, author)
