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

from typing import TYPE_CHECKING, Union

from .models import Permissions

if TYPE_CHECKING:
    from .clan import Clan
    from .group import Group
    from .protobufs.steammessages_chat import CChatRoleActions as RoleProto
    from .state import ConnectionState

__all__ = ("Role",)


class Role:
    __slots__ = ("id", "clan", "group", "permissions", "_state")

    def __init__(self, state: "ConnectionState", group: Union["Clan", "Group"], proto: "RoleProto"):
        self._state = state
        self.id = int(proto.role_id)
        if group.__class__.__name__ == "Clan":
            self.clan = group
            self.group = None
        else:
            self.group = group
            self.clan = None
        self.permissions = Permissions(proto)

    async def edit(self, *, name: str):
        await self._state.edit_role(self.id, (self.clan or self.group).id, name=name)
