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

    async def edit(self, *, name: str) -> None:
        await self._state.edit_role(self.id, (self.clan or self.group).id, name=name)  # type: ignore


class RolePermissions:
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
