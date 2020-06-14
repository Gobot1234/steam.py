# -*- coding: utf-8 -*-

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

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .channel import DMChannel, GroupChannel
    from .abc import BaseUser
    from .protobufs.steammessages_friendmessages import CFriendMessages_IncomingMessage_Notification \
        as UserMessageNotification
    from .protobufs.steammessages_chat import CChatRoom_IncomingChatMessage_Notification \
        as GroupMessageNotification


__all__ = (
    'UserMessage',
    'GroupMessage',
)


class UserMessage:
    """Represents a message from a User."""

    __slots__ = ('author', 'channel', 'content', 'created_at', '_state')

    def __init__(self, proto: 'UserMessageNotification', channel: 'DMChannel'):
        self._state = channel._state
        self.author = channel.participant
        self.channel = channel
        self.content = proto.message
        self.created_at = datetime.utcfromtimestamp(proto.rtime32_server_timestamp)

    def __repr__(self):
        attrs = (
            'author', 'channel'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f"<UserMessage {' '.join(resolved)}>"


class GroupMessage:

    __slots__ = ('author', 'channel', 'content', 'created_at', '_state')

    def __init__(self, proto: 'GroupMessageNotification', channel: 'GroupChannel', author: 'BaseUser'):
        self._state = channel._state
        self.author = author
        self.channel = channel
        self.content = proto.message
        self.created_at = datetime.utcfromtimestamp(proto.timestamp)

    def __repr__(self):
        attrs = (
            'author', 'channel'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f"<GroupMessage {' '.join(resolved)}>"
