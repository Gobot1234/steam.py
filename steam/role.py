"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, overload

from ._const import _HasChatGroupMixin
from .enums import Type
from .protobufs import chat
from .types.id import RoleID

if TYPE_CHECKING:
    from typing_extensions import Self

    from .chat import ChatGroup, Member
    from .clan import Clan
    from .group import Group
    from .state import ConnectionState

__all__ = (
    "Role",
    "RolePermissions",
)


class Role(_HasChatGroupMixin):
    """Represents a role in a chat group."""

    __slots__ = ("id", "name", "ordinal", "clan", "group", "permissions", "_state")
    group: Group | None
    """The group the role belongs to, if any."""
    clan: Clan | None
    """The clan the role belongs to, if any."""

    def __init__(self, state: ConnectionState, group: ChatGroup, role: chat.Role, permissions: chat.RoleActions):
        self._state = state
        self.id = RoleID(role.role_id)
        """The ID of the role."""
        self.name = role.name.removeprefix("#ChatRoomRole_")
        """The name of the role."""
        self.ordinal = role.ordinal
        """The ordinal of the role."""

        if group.type is Type.Clan:  # these are reasonably safe casts as ChatGroup is an abc
            self.clan = cast("Clan", group)
            self.group = None
        else:
            self.group = cast("Group", group)
            self.clan = None
        self.permissions = RolePermissions(permissions)
        """The permissions of the role."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id}>"

    @property
    def members(self) -> list[Member]:
        """The members that have this role."""
        return [m for m in self._chat_group.members if self in m.roles]

    async def edit(
        self, *, name: str | None = None, permissions: RolePermissions | None = None, ordinal: int | None = None
    ) -> None:
        """Edit this role.

        Parameters
        ----------
        name
            The new name of the role.
        permissions
            The new permissions of the role.
        ordinal
            The new ordinal (position) of the role.
        """
        await self._state.edit_role(self._chat_group._id, self.id, name=name, permissions=permissions, ordinal=ordinal)

    async def delete(self) -> None:
        """Delete this role."""
        await self._state.delete_role(self._chat_group._id, self.id)


class RolePermissions:
    """Represents the permissions of a role in a chat group."""

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
        """Whether the role can kick members."""
        self.ban_members = proto.can_ban
        """Whether the role can ban members."""
        self.invite = proto.can_invite
        """Whether the role can invite members."""
        self.manage_group = proto.can_change_tagline_avatar_name
        """Whether the role can manage the group."""
        self.send_messages = proto.can_chat
        """Whether the role can send messages."""
        self.read_message_history = proto.can_view_history
        """Whether the role can read message history."""
        self.change_group_roles = proto.can_change_group_roles
        """Whether the role can change group roles."""
        self.change_user_roles = proto.can_change_user_roles
        """Whether the role can change user roles."""
        self.mention_all = proto.can_mention_all
        """Whether the role can mention all."""
        self.set_watching_broadcast = proto.can_set_watching_broadcast
        """Whether the role can set watching broadcast."""

    def copy(self) -> Self:
        return self.__class__(self.to_proto())

    __copy__ = copy

    def to_proto(self) -> chat.RoleActions:
        return chat.RoleActions(
            can_kick=self.kick,
            can_ban=self.ban_members,
            can_invite=self.invite,
            can_change_tagline_avatar_name=self.manage_group,
            can_chat=self.send_messages,
            can_view_history=self.read_message_history,
            can_change_group_roles=self.change_group_roles,
            can_change_user_roles=self.change_user_roles,
            can_mention_all=self.mention_all,
            can_set_watching_broadcast=self.set_watching_broadcast,
        )

    @overload
    def replace(  # type: ignore
        self,
        *,
        kick: bool = ...,
        ban_members: bool = ...,
        invite: bool = ...,
        manage_group: bool = ...,
        send_messages: bool = ...,
        read_message_history: bool = ...,
        change_group_roles: bool = ...,
        change_user_roles: bool = ...,
        mention_all: bool = ...,
        set_watching_broadcast: bool = ...,
    ) -> Self:
        ...

    def replace(self, **kwargs: bool) -> Self:
        """Return a new RolePermissions with the specified changes."""
        new = self.copy()
        for name, value in kwargs.items():
            setattr(new, name, value)
        return new
