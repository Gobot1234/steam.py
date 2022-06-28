"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import utils
from .channel import GroupChannel
from .chat import ChatGroup, Member
from .enums import Type

if TYPE_CHECKING:
    from .protobufs import chat
    from .state import ConnectionState
    from .types.id import ID64, ChatGroupID
    from .user import User


__all__ = ("Group", "GroupMember")


class GroupMember(Member):
    group: Group
    clan: None

    def __init__(self, state: ConnectionState, user: User, group: Group, proto: chat.Member):
        super().__init__(state, user, proto)
        self.group = group


class Group(ChatGroup[GroupMember, GroupChannel]):
    """Represents a Steam group.

    Attributes
    ----------
    name
        The name of the group.
    owner
        The owner of the group.
    active_member_count
        The group's active member count.
    """

    __slots__ = (
        "active_member_count",
        "_top_members",
        "_id",
    )

    active_member_count: int
    _top_members: list[ID64]

    def __init__(self, state: ConnectionState, id: ChatGroupID):
        super().__init__(id, type=Type.Chat)
        self._state = state
        self._id = id

    @classmethod
    async def _from_proto(cls, state: ConnectionState, proto: chat.GetChatRoomGroupSummaryResponse) -> Group:
        self = cls(state, proto.chat_group_id)
        owner = self._state.get_user(utils.make_id64(proto.accountid_owner))
        assert owner
        self.owner = owner
        self._top_members = proto.top_members
        self.name = proto.chat_group_name

        self.active_member_count = proto.active_member_count

        await self._populate_roles(proto.role_actions)
        self._default_role_id = proto.default_role_id

        self._update_channels(proto.chat_rooms, default_channel_id=proto.default_chat_id)
        return self

    @property
    def top_members(self) -> list[GroupMember]:
        """A list of the chat's top members according to Steam."""
        return [self._members[id64] for id64 in self._top_members]

    # TODO is this possible
    # async def join(self) -> None:
    #     ...
