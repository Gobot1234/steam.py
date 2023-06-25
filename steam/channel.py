"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Coroutine
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .abc import Channel
from .chat import Chat, GroupChannelProtos
from .message import ClanMessage, GroupMessage, UserMessage

if TYPE_CHECKING:
    from .clan import Clan
    from .friend import Friend
    from .group import Group
    from .media import Media
    from .state import ConnectionState
    from .user import User

__all__ = (
    "UserChannel",
    "GroupChannel",
    "ClanChannel",
)


class UserChannel(Channel[UserMessage]):
    """Represents the channel a DM is sent in."""

    __slots__ = ("participant", "last_message")
    clan: None
    group: None

    def __init__(self, state: ConnectionState, participant: User | Friend):
        super().__init__(state)
        self.participant = participant
        """The recipient of any messages sent."""
        self.clan = None
        self.group = None
        self.last_message: UserMessage | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} participant={self.participant!r}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, UserChannel) and self.participant == other.participant

    def __hash__(self) -> int:
        return hash(self.participant)

    def _message_func(self, content: str) -> Coroutine[Any, Any, UserMessage]:
        return self.participant._message_func(content)

    def _media_func(self, media: Media) -> Coroutine[Any, Any, None]:
        return self.participant._media_func(media)

    def typing(self) -> AbstractAsyncContextManager[None]:
        """Send a typing indicator continuously to the channel while in the context manager.

        Note
        ----
        This only works in DMs.

        Usage:

        .. code:: python

            async with channel.typing():
                ...  # do your expensive operations
        """

        return self.participant.typing()

    async def trigger_typing(self) -> None:
        """Send a typing indicator to the channel once.

        Note
        ----
        This only works in DMs.
        """
        await self.participant.trigger_typing()

    def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[UserMessage, None]:
        return self.participant.history(limit=limit, before=before, after=after)


class GroupChannel(Chat[GroupMessage]):
    """Represents a group channel."""

    __slots__ = ()

    clan: None

    def __init__(self, state: ConnectionState, group: Group, proto: GroupChannelProtos):
        super().__init__(state, group, proto)
        self.group: Group = group


class ClanChannel(Chat[ClanMessage]):
    """Represents a clan channel."""

    __slots__ = ()

    group: None

    def __init__(self, state: ConnectionState, clan: Clan, proto: GroupChannelProtos):
        super().__init__(state, clan, proto)
        self.clan: Clan = clan
