# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 Gobot1234

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import asyncio
from typing import TYPE_CHECKING

from .abc import BaseChannel

if TYPE_CHECKING:
    from .group import Group
    from .image import Image
    from .trade import TradeOffer
    from .state import ConnectionState
    from .user import User
    from .protobufs.steammessages_chat import CChatRoom_IncomingChatMessage_Notification \
        as GroupMessageNotification


__all__ = (
    'DMChannel',
    'GroupChannel',
)


class DMChannel(BaseChannel):
    __slots__ = ('participant', '_state')

    def __init__(self, state: 'ConnectionState', participant: 'User'):
        self._state = state
        self.participant = participant

    def __repr__(self):
        return f"<DMChannel participant={self.participant!r}>"

    async def send(self, content: str = None, *,
                   trade: 'TradeOffer' = None,
                   image: 'Image' = None) -> None:
        await self.participant.send(content=content, trade=trade, image=image)

    def typing(self):
        return TypingContextManager(self.participant)

    async def trigger_typing(self):
        await self._state.send_user_typing(self.participant)


# this is basically straight from d.py


def _typing_done_callback(fut):
    # just retrieve any exception and call it a day
    try:
        fut.exception()
    except (asyncio.CancelledError, Exception):
        pass


class TypingContextManager:
    __slots__ = ('participant', '_task', '_state')

    def __init__(self, participant: 'User'):
        self._state = participant._state
        self.participant = participant

    async def send_typing(self):
        while 1:
            await self._state.send_user_typing(self.participant)
            await asyncio.sleep(5)

    def __enter__(self):
        self._task = self._state.loop.create_task(self.send_typing())
        self._task.add_done_callback(_typing_done_callback)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._task.cancel()

    async def __aenter__(self):
        self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.__exit__(exc_type, exc_val, exc_tb)


class GroupChannel(BaseChannel):
    def __init__(self, state: 'ConnectionState',
                 group: 'Group',
                 notification: 'GroupMessageNotification'):
        self._state = state
        self.group = group
        self.id = int(notification.chat_id)
        self.name = notification.chat_name or None

    def __repr__(self):
        attrs = (
            'name', 'id', 'group'
        )
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in attrs]
        return f"<GroupChannel {' '.join(resolved)}>"

    def _get_message_endpoint(self):
        return (self.id, self.group.id), self._state.send_group_message

    def _get_image_endpoint(self):
        return (self.id, self.group.id), self._state.http.send_group_image
