"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING

from .channel import GroupChannel
from .chat import ChatGroup, Member
from .enums import Type

if TYPE_CHECKING:
    from .protobufs import chat
    from .state import ConnectionState
    from .types.id import ChatGroupID
    from .user import User


__all__ = ("Group", "GroupMember")


class GroupMember(Member):
    group: Group
    clan: None

    def __init__(self, state: ConnectionState, group: Group, user: User, proto: chat.Member):
        super().__init__(state, group, user, proto)
        self.group = group


class Group(ChatGroup[GroupMember, GroupChannel]):
    """Represents a Steam group."""

    __slots__ = ()

    def __init__(self, state: ConnectionState, id: ChatGroupID):
        super().__init__(id, type=Type.Chat)
        self._state = state
        self._id = id

    async def chunk(self) -> Sequence[GroupMember]:
        self._members = dict.fromkeys(self._partial_members)  # type: ignore
        for id, member in self._partial_members.items():
            user = self._state.get_user(id)
            while user is None:
                await asyncio.sleep(0)  # same as in clan.py, let receive() populate the cache
                user = self._state.get_user(id)
            member = GroupMember(self._state, self, user, member)
            self._members[member.id] = member
        return await super().chunk()

    # TODO is this possible
    # async def join(self) -> None:
    #     ...
