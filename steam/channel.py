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
from collections.abc import Coroutine, Generator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from typing_extensions import TypeAlias

from .abc import Channel, M_co, Message, SteamID
from .iterators import DMChannelHistoryIterator, GroupChannelHistoryIterator
from .protobufs.chat import ChatRoomState, IncomingChatMessageNotification, State

if TYPE_CHECKING:
    from _typeshed import Self

    from .clan import Clan
    from .group import Group
    from .image import Image
    from .message import ClanMessage, GroupMessage, UserMessage
    from .state import ConnectionState
    from .user import User

__all__ = (
    "DMChannel",
    "GroupChannel",
    "ClanChannel",
)


class DMChannel(Channel["UserMessage"]):  # TODO cache these to add last_message.
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

    def _message_func(self, content: str) -> Coroutine[Any, Any, UserMessage]:
        return self.participant._message_func(content)

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self.participant._image_func(image)

    @asynccontextmanager
    async def typing(self) -> Generator[None, None, None]:
        """Send a typing indicator continuously to the channel while in the context manager.

        Note
        ----
        This only works in DMs.

        Usage:

        .. code-block:: python3

            async with ctx.channel.typing():
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

    def history(
        self,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> DMChannelHistoryIterator:
        return DMChannelHistoryIterator(state=self._state, channel=self, limit=limit, before=before, after=after)


GroupChannelProtos: TypeAlias = "IncomingChatMessageNotification | State | ChatRoomState"


class _GroupChannel(Channel[M_co]):
    __slots__ = ("id", "name", "joined_at", "position", "last_message")

    def __init__(self, state: ConnectionState, proto: GroupChannelProtos):
        super().__init__(state)
        self.id = int(proto.chat_id)
        self.name: str | None = None
        self.joined_at: datetime | None = None
        self.position: int | None = None
        self.last_message: M_co | None = None
        self._update(proto)

    def _update(self, proto: GroupChannelProtos):
        if hasattr(proto, "chat_name"):
            first, _, second = proto.chat_name.partition(" | ")
            name = second or first
        else:
            name = self.name
        self.name = name
        self.joined_at = (
            datetime.utcfromtimestamp(int(proto.time_joined)) if hasattr(proto, "time_joined") else self.joined_at
        )
        self.position = getattr(proto, "sort_order", None) or self.position
        from .message import ClanMessage, GroupMessage

        if isinstance(proto, IncomingChatMessageNotification):
            steam_id = SteamID(proto.steamid_sender)
            last_message = (ClanMessage if isinstance(self, ClanChannel) else GroupMessage)(
                proto, self, self._state.get_user(steam_id.id64) or steam_id  # type: ignore
            )
        elif isinstance(proto, State):
            steam_id = SteamID(proto.accountid_last_message)
            cls = ClanMessage if isinstance(self, ClanChannel) else GroupMessage
            last_message = cls.__new__(cls)
            last_message.author = self._state.get_user(steam_id.id64) or steam_id
            last_message.channel = self  # type: ignore
            last_message.created_at = datetime.utcfromtimestamp(proto.time_last_message)
            proto.message = proto.last_message
            proto.ordinal = NotImplemented
            Message.__init__(last_message, self, proto)
        else:
            last_message = self.last_message
        self.last_message = last_message  # type: ignore

    def __repr__(self) -> str:
        cls = self.__class__
        attrs = ("name", "id", "group" if self.group is not None else "clan", "position")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{cls.__name__} {' '.join(resolved)}>"

    def history(
        self: Self,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> GroupChannelHistoryIterator[M_co, Self]:
        return GroupChannelHistoryIterator(state=self._state, channel=self, limit=limit, before=before, after=after)


class GroupChannel(_GroupChannel["GroupMessage"]):
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
        super().__init__(state, proto)
        self.group: Group = group

    def _message_func(self, content: str) -> Coroutine[Any, Any, GroupMessage]:
        return self._state.send_group_message(self.id, self.group.id, content)  # type: ignore

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_group_image(self.id, self.group.id, image)


class ClanChannel(_GroupChannel["ClanMessage"]):  # they're basically the same thing
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
        super().__init__(state, proto)
        self.clan: Clan = clan

    def _message_func(self, content: str) -> Coroutine[Any, Any, ClanMessage]:
        return self._state.send_group_message(self.id, self.clan.chat_id, content)  # type: ignore

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_group_image(self.id, self.clan.chat_id, image)  # type: ignore
