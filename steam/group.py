"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal

from .channel import GroupChannel
from .chat import ChatGroup, Member, PartialMember
from .enums import Type

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .protobufs import chat
    from .state import ConnectionState
    from .types.id import ID32, ChatGroupID
    from .user import User


__all__ = ("Group", "GroupMember")


class GroupMember(Member[None, "Group"]):
    def __init__(self, state: ConnectionState, group: Group, user: User, proto: chat.Member):
        super().__init__(state, group, user, proto)
        self.group = group


class Group(ChatGroup[GroupMember, GroupChannel, Literal[Type.Chat]]):
    """Represents a Steam group."""

    __slots__ = ()

    def __init__(self, state: ConnectionState, id: ChatGroupID):
        super().__init__(state, id, type=Type.Chat)
        self._id = self.id

    async def chunk(self) -> Sequence[GroupMember]:
        if self.chunked:
            return self.members

        self._members = dict.fromkeys(self._partial_members)  # type: ignore
        for id, member in self._partial_members.items():
            user = self._state.get_user(id)
            while user is None:
                await asyncio.sleep(0)  # same as in clan.py, let receive() populate the cache
                user = self._state.get_user(id)
            member = GroupMember(self._state, self, user, member)
            self._members[member.id] = member
        return await super().chunk()

    def _get_partial_member(self, id: ID32, /) -> PartialMember:
        return PartialMember(self._state, group=self, member=self._partial_members[id])

    # TODO is this possible
    # async def join(self) -> None:
    #     ...
