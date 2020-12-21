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

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, Union

from .abc import Channel
from .iterators import DMChannelHistoryIterator, GroupChannelHistoryIterator

if TYPE_CHECKING:
    from .abc import _EndPointReturnType
    from .clan import Clan
    from .group import Group
    from .image import Image
    from .protobufs.steammessages_chat import (
        CChatRoomIncomingChatMessageNotification as GroupMessageNotification,
        CChatRoomState,
        CUserChatRoomState,
    )
    from .state import ConnectionState
    from .trade import TradeOffer
    from .user import User

__all__ = (
    "DMChannel",
    "GroupChannel",
    "ClanChannel",
)


class DMChannel(Channel):
    """Represents the channel a DM is sent in.

    Attributes
    ----------
    participant: :class:`~steam.User`
        The recipient of any messages sent.
    """

    __slots__ = ("participant",)

    def __init__(self, state: ConnectionState, participant: User):
        super().__init__(state)
        self.participant = participant
        self.clan = None
        self.group = None

    def __repr__(self) -> str:
        return f"<DMChannel participant={self.participant!r}>"

    def _get_message_endpoint(self) -> _EndPointReturnType:
        return self.participant._get_message_endpoint()

    def _get_image_endpoint(self) -> _EndPointReturnType:
        return self.participant._get_image_endpoint()

    async def send(
        self, content: Optional[str] = None, *, trade: Optional[TradeOffer] = None, image: Optional[Image] = None
    ) -> None:
        """|coro|
        Send a message, trade or image to an :class:`User`.

        Parameters
        ----------
        content: Optional[:class:`str`]
           The message to send to the user.
        trade: Optional[:class:`.TradeOffer`]
           The trade offer to send to the user.

           Note
           ----
           This will have its :attr:`~steam.TradeOffer.id` attribute updated after being sent.

        image: Optional[:class:`.Image`]
           The image to send to the user.

        Raises
        ------
        :exc:`~steam.HTTPException`
           Sending the message failed.
        :exc:`~steam.Forbidden`
           You do not have permission to send the message.
        """
        await self.participant.send(content=content, trade=trade, image=image)

    @asynccontextmanager
    async def typing(self) -> None:
        """Send a typing indicator continuously to the channel while in the context manager.

        Note
        ----
        This only works in DMs.

        Usage: ::

            async with ctx.channel.typing():
                # do your expensive operations
        """

        def suppress(task: asyncio.Task) -> None:
            try:
                task.exception()
            except (asyncio.CancelledError, Exception):
                pass

        async def inner() -> None:
            while True:
                await asyncio.sleep(5)
                await self._state.send_user_typing(self.participant.id64)

        await self._state.send_user_typing(self.participant.id64)
        task = self._state.loop.create_task(inner())
        task.add_done_callback(suppress)
        yield
        task.cancel()

    async def trigger_typing(self) -> None:
        """Send a typing indicator to the channel once.

        Note
        ----
        This only works in DMs.
        """
        await self._state.send_user_typing(self.participant.id64)

    def history(
        self,
        limit: Optional[int] = 100,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> DMChannelHistoryIterator:
        return DMChannelHistoryIterator(state=self._state, channel=self, limit=limit, before=before, after=after)


class _GroupChannel(Channel):
    __slots__ = ("id", "joined_at", "name")

    def __init__(self, state: ConnectionState, channel: Any):
        super().__init__(state)
        self.id = int(channel.chat_id)
        self.joined_at: Optional[datetime]
        if hasattr(channel, "chat_name"):
            split = channel.chat_name.split(" | ", 1)
            self.name = split[1] if len(split) != 1 else split[0]
        else:
            self.name = None
        self.joined_at = (
            datetime.utcfromtimestamp(int(channel.time_joined)) if hasattr(channel, "time_joined") else None
        )

    def __repr__(self) -> str:
        attrs = ("id", "group")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<GroupChannel {' '.join(resolved)}>"

    def _get_message_endpoint(self) -> _EndPointReturnType:
        return (self.id, self.group.id), self._state.send_group_message

    def _get_image_endpoint(self) -> _EndPointReturnType:
        return (self.id, self.group.id), self._state.http.send_group_image

    def history(
        self,
        limit: Optional[int] = 100,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> GroupChannelHistoryIterator:
        return GroupChannelHistoryIterator(state=self._state, channel=self, limit=limit, before=before, after=after)


class GroupChannel(_GroupChannel):
    """Represents a group channel.

    Attributes
    ----------
    id: :class:`int`
        The ID of the channel.
    name: Optional[:class:`str`]
        The name of the channel, this could be the same as the :attr:`~steam.Group.name` if it's the main channel.
    group: :class:`~steam.Group`
        The group to which messages are sent.
    joined_at: Optional[:class:`datetime.datetime`]
        The time the client joined the chat.
    """

    def __init__(self, state: ConnectionState, group: Group, channel: Union[GroupMessageNotification, CChatRoomState]):
        super().__init__(state, channel)
        self.group = group


class ClanChannel(_GroupChannel):  # they're basically the same thing
    """Represents a group channel.

    Attributes
    ----------
    id: :class:`int`
        The ID of the channel.
    name: Optional[:class:`str`]
        The name of the channel, this could be the same
        as the :attr:`~steam.Clan.name` if it's the main channel.
    clan: :class:`~steam.Clan`
        The clan to which messages are sent.
    joined_at: Optional[:class:`datetime.datetime`]
        The time the client joined the chat.
    """

    def __init__(
        self, state: ConnectionState, clan: Clan, channel: Union[GroupMessageNotification, CUserChatRoomState]
    ):
        super().__init__(state, channel)
        self.clan = clan

    def __repr__(self) -> str:
        attrs = ("id", "clan")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<ClanChannel {' '.join(resolved)}>"

    def _get_message_endpoint(self) -> _EndPointReturnType:
        return (self.id, self.clan.chat_id), self._state.send_group_message

    def _get_image_endpoint(self) -> _EndPointReturnType:
        return (self.id, self.clan.chat_id), self._state.http.send_group_image
