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

from datetime import datetime
from typing import TYPE_CHECKING, Any

from typing_extensions import TypeAlias

from .abc import Message, SteamID

if TYPE_CHECKING:
    from .channel import ClanChannel, DMChannel, GroupChannel
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

    def __init__(self, proto: friend_messages.IncomingMessageNotification, channel: DMChannel):
        super().__init__(channel, proto)
        self.author = channel.participant
        self.created_at = datetime.utcfromtimestamp(proto.rtime32_server_timestamp)


class _GroupMessage(Message):
    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: Any, author: Authors):
        super().__init__(channel, proto)
        self.author = author
        self.created_at = datetime.utcfromtimestamp(proto.timestamp)


class GroupMessage(_GroupMessage):
    """Represents a message in a group."""

    channel: GroupChannel

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: GroupChannel, author: Authors):
        super().__init__(proto, channel, author)


class ClanMessage(_GroupMessage):
    """Represents a message in a clan."""

    channel: ClanChannel

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ClanChannel, author: Authors):
        super().__init__(proto, channel, author)
