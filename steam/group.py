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

from typing import TYPE_CHECKING

from . import utils
from .abc import SteamID
from .channel import GroupChannel
from .enums import Type
from .role import Role

if TYPE_CHECKING:
    from .protobufs import chat
    from .state import ConnectionState
    from .user import User


__all__ = ("Group",)


class Group(SteamID):
    """Represents a Steam group.

    Attributes
    ----------
    name
        The name of the group, could be ``None``.
    owner
        The owner of the group.
    members
        A list of the group's members.
    active_member_count
        The group's active member count.
    roles
        A list of the group's roles.
    default_role
        The group's default role.
    default_channel
        The group's default channel.
    """

    __slots__ = (
        "owner",
        "name",
        "members",
        "roles",
        "active_member_count",
        "default_role",
        "default_channel",
        "_channels",
        "_top_members_id64s",
        "_state",
    )

    owner: User | SteamID
    members: list[User]
    name: str | None
    active_member_count: int
    roles: list[Role]
    default_role: Role | None
    _channels: dict[int, GroupChannel]
    _top_members_id64s: list[int]

    # TODO
    # Group.ban
    # Group.kick
    # Group.create_channel

    def __init__(self, state: ConnectionState, id: int):
        super().__init__(id, type=Type.Chat)
        self._state = state

    @classmethod
    async def _from_proto(
        cls, state: ConnectionState, proto: chat.GetChatRoomGroupSummaryResponse | chat.GroupHeaderState
    ) -> Group:
        self = cls(state, proto.chat_group_id)
        self.owner = await self._state._maybe_user(utils.make_id64(proto.accountid_owner))
        self._top_members_id64s = proto.top_members
        self.name = proto.chat_group_name or None

        self.active_member_count = proto.active_member_count
        self.roles = []
        for role in await self._state.fetch_group_roles(self.id):
            for permissions in proto.role_actions:
                if permissions.role_id == role.role_id:
                    self.roles.append(Role(self._state, self, role, permissions))

        self.default_role = utils.get(self.roles, id=proto.default_role_id)
        self._channels = {
            channel.chat_id: GroupChannel(state=self._state, group=self, proto=channel) for channel in proto.chat_rooms
        }
        self.default_channel = self._channels.get(proto.default_chat_id)
        return self

    def __repr__(self) -> str:
        attrs = ("name", "id", "owner")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Group {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name or ""

    def _update(self, proto: chat.ChatRoomGroupRoomsChangeNotification) -> None:
        for channel in proto.chat_rooms:
            try:
                new_channel = self._channels[channel.chat_id]
            except KeyError:
                new_channel = GroupChannel(state=self._state, group=self, proto=channel)
                self._channels[new_channel.id] = new_channel
            else:
                new_channel._update(channel)
        self.default_channel = self._channels[int(proto.default_chat_id)]

    @property
    def channels(self) -> list[GroupChannel]:
        """A list of the group's channels."""
        return list(self._channels.values())

    @property
    def top_members(self) -> list[User | None]:
        """A list of the group's top members according to Steam."""
        return [self._state.get_user(id64) for id64 in self._top_members_id64s]

    async def leave(self) -> None:
        """Leaves the group."""
        await self._state.leave_chat(self.id)

    async def invite(self, user: User) -> None:
        """Invites a :class:`~steam.User` to the group.

        Parameters
        -----------
        user
            The user to invite to the group.
        """
        await self._state.invite_user_to_group(user.id64, self.id)
