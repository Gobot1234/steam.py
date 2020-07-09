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

from typing import TYPE_CHECKING, List

from .channel import GroupChannel
from .models import Role

if TYPE_CHECKING:
    from .abc import BaseUser
    from .protobufs.steammessages_chat import CChatRoom_GetChatRoomGroupSummary_Response as GroupProto
    from .state import ConnectionState
    from .user import User


__all__ = ("Group",)


class Group:
    """Represents a Steam group.

    Attributes
    ----------
    id: :class:`int`
        The group's ID.
    name: Optional[:class:`str`]
        The name of the group, could be ``None``.
    owner: :class:`~steam.abc.BaseUser`
        The owner of the group.
    top_members: List[:class:`~steam.abc.BaseUser`]
        A list of the group's top members.
    active_member_count: :class:`int`
        The group's active member count.
    roles: List[:class:`~steam.Role`]
        A list of the group's roles.
    default_role: :class:`~steam.Role`
        The group's default role.
    default_channel: :class:`~steam.GroupChannel`
        The group's default channel.
    channels: List[:class:`~steam.GroupChannel`]
        A list of the group's channels.
    """

    __slots__ = (
        "owner",
        "top_members",
        "id",
        "name",
        "active_member_count",
        "roles",
        "default_role",
        "default_channel",
        "channels",
        "_state",
    )

    def __init__(self, state: "ConnectionState", proto: "GroupProto"):
        self._state = state
        self._from_proto(proto)

    async def __ainit__(self):
        self.owner = await self._state.client.fetch_user(self.owner)
        self.top_members: List["BaseUser"] = await self._state.client.fetch_users(self.top_members)

    def _from_proto(self, proto: "GroupProto"):
        self.id = int(proto.chat_group_id)
        self.owner = proto.accountid_owner
        self.name = proto.chat_group_name or None

        self.active_member_count = proto.active_member_count
        self.top_members = proto.top_members
        self.roles = []

        for role in proto.role_actions:
            self.roles.append(Role(role))

        default_role = [r for r in self.roles if r.id == int(proto.default_role_id)]
        if default_role:
            self.default_role = default_role[0]
        else:
            self.default_role = None
        self.default_channel = int(proto.default_chat_id)
        self.channels = []
        for channel in proto.chat_rooms:
            channel = GroupChannel(state=self._state, group=self, channel=channel)
            self.channels.append(channel)
        self.default_channel = [c for c in self.channels if c.id == int(proto.default_chat_id)][0]

    def __repr__(self):
        attrs = ("name", "id", "owner")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Group {' '.join(resolved)}>"

    def __str__(self):
        return self.name or ""

    async def leave(self) -> None:
        """|coro|
        Leaves the :class:`Group`.
        """

    async def invite(self, user: "User"):
        """|coro|
        Invites a :class:`~steam.User` to the :class:`Group`.

        Parameters
        -----------
        user: :class:`~steam.User`
            The user to invite to the group.
        """
