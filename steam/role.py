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

from typing import TYPE_CHECKING, Any

from typing_extensions import Self

if TYPE_CHECKING:
    from .clan import Clan
    from .group import Group
    from .protobufs import chat
    from .state import ConnectionState

__all__ = (
    "Role",
    "RolePermissions",
)


class Role:
    __slots__ = ("id", "name", "ordinal", "clan", "group", "permissions", "_state")

    def __init__(self, state: ConnectionState, group: Clan | Group, role: chat.Role, permissions: chat.RoleActions):
        self._state = state
        self.id = int(role.role_id)
        self.name = role.name
        self.ordinal = role.ordinal

        from .clan import Clan

        if isinstance(group, Clan):
            self.clan = group
            self.group = None
        else:
            self.group = group
            self.clan = None
        self.permissions = RolePermissions(permissions)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} name={self.id}>"

    # @property
    # def members(self) -> list[Member]:
    #     if self.clan:
    #         return self.clan.members
    #     assert self.group is not None
    #     return [m for m in self.group.members if self in m.roles]

    async def edit(self, *, name: str | None = None, permissions: RolePermissions | None = None) -> None:
        chat_group = self.group or self.clan
        assert chat_group is not None
        chat_group_id = chat_group._id
        assert chat_group_id is not None
        if name is not None:
            await self._state.edit_role_name(self.id, chat_group_id, name=name)
        if permissions is not None:
            await self._state.edit_role_permissions(self.id, chat_group_id, permissions=permissions)

    async def delete(self) -> None:
        chat_group = self.group or self.clan
        assert chat_group is not None
        chat_group_id = chat_group._id
        assert chat_group_id is not None
        await self._state.delete_role(self.id, chat_group_id)


class RolePermissions:
    __slots__ = (
        "kick",
        "ban_members",
        "invite",
        "manage_group",
        "send_messages",
        "read_message_history",
        "change_group_roles",
        "change_user_roles",
        "mention_all",
        "set_watching_broadcast",
    )

    def __init__(self, proto: chat.RoleActions):
        self.kick = proto.can_kick
        self.ban_members = proto.can_ban
        self.invite = proto.can_invite
        self.manage_group = proto.can_change_tagline_avatar_name
        self.send_messages = proto.can_chat
        self.read_message_history = proto.can_view_history
        self.change_group_roles = proto.can_change_group_roles
        self.change_user_roles = proto.can_change_user_roles
        self.mention_all = proto.can_mention_all
        self.set_watching_broadcast = proto.can_set_watching_broadcast

    def copy(self) -> Self:
        return self.__class__(chat.RoleActions(**self.to_dict()))

    __copy__ = copy

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_kick": self.kick,
            "can_ban": self.ban_members,
            "can_invite": self.invite,
            "can_change_tagline_avatar_name": self.manage_group,
            "can_chat": self.send_messages,
            "can_view_history": self.read_message_history,
            "can_change_group_roles": self.change_group_roles,
            "can_change_user_roles": self.change_user_roles,
            "can_mention_all": self.mention_all,
            "can_set_watching_broadcast": self.set_watching_broadcast,
        }
