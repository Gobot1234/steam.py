"""
The shared base classes for chat group interactions.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import Coroutine, Sequence
from datetime import datetime
from random import randint
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from typing_extensions import Self, TypeAlias

from . import utils
from .abc import Channel, Message, SteamID
from .enums import ChatMemberRank, Type
from .errors import WSException
from .game import StatefulGame
from .iterators import ChatHistoryIterator
from .protobufs import MsgProto, chat
from .reaction import Emoticon, MessageReaction, Sticker
from .role import Role
from .user import User, WrapsUser
from .utils import DateTime

if TYPE_CHECKING:
    from .channel import ClanChannel, GroupChannel
    from .clan import Clan
    from .group import Group
    from .image import Image
    from .message import Authors, ClanMessage, GroupMessage
    from .state import ConnectionState
    from .types.id import ID32, ID64, ChannelID, ChatGroupID


ChatT = TypeVar("ChatT", bound="Chat[Any]", covariant=True)
MemberT = TypeVar("MemberT", bound="Member", covariant=True)


class Member(WrapsUser):
    """Represents a member of a chat group."""

    __slots__ = (
        "clan",
        "group",
        "rank",
        "kick_expires_at",
        "_role_ids",
    )
    clan: Clan | None
    group: Group | None

    def __init__(
        self, state: ConnectionState, chat_group: ChatGroup[Any, Any], user: User, member: chat.Member
    ) -> None:
        super().__init__(state, user)
        self.clan = None
        self.group = None
        self._update(member)

    def _update(self, member: chat.Member) -> None:
        self.rank = ChatMemberRank.try_value(member.rank)
        self._role_ids = tuple(member.role_ids)
        self.kick_expires_at = DateTime.from_timestamp(member.time_kick_expire)

    @property
    def roles(self) -> list[Role]:
        """The member's roles."""
        chat_group = self.group or self.clan
        assert chat_group is not None
        return [chat_group._roles[role_id] for role_id in self._role_ids]

    # async def add_role(self, role: Role):
    #     """Add a role to the member."""

    # async def ban(self, *, reason: str | None = None) -> None:
    #     """Bans the member from the chat group."""
    #     group = self.group or self.clan
    #     assert group is not None
    #     await group.ban(self, reason=reason)


class ChatMessage(Message):
    channel: GroupChannel | ClanChannel
    mentions: chat.Mentions
    author: Member | SteamID

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: Any, author: Authors):
        super().__init__(channel, proto)
        self.author = author
        self.created_at = DateTime.from_timestamp(proto.timestamp)

    async def fetch_reaction(self, emoticon: Emoticon | Sticker) -> list[MessageReaction]:
        """Fetches the reactions to this message with a given emoticon."""
        chat_group = self.clan or self.group
        assert chat_group is not None
        is_emoticon = isinstance(emoticon, Emoticon)
        reactors = await self._state.fetch_message_reactors(
            *self.channel._location,
            server_timestamp=int(self.created_at.timestamp()),
            ordinal=self.ordinal,
            reaction_name=str(emoticon) if is_emoticon else emoticon.name,
            reaction_type=1 if is_emoticon else 2,
        )

        reaction = utils.find(
            lambda r: (r.emoticon or r.sticker).name == emoticon.name, self.partial_reactions  # type: ignore
        )
        assert reaction
        return [
            MessageReaction(
                self._state,
                self,
                reaction.emoticon,
                reaction.sticker,
                user=chat_group._members.get(reactor) or SteamID(reactor),
            )
            for reactor in reactors
        ]

    async def fetch_reactions(self) -> list[MessageReaction]:
        """Fetches all this message's reactions.

        Warning
        -------
        This does nothing for messages that aren't fetched by :meth:`GroupChannel.history`/:meth:`ClanChannel.history`.
        """
        return [
            r
            for rs in await asyncio.gather(
                *(
                    self.fetch_reaction(reaction.emoticon or reaction.sticker)  # type: ignore
                    for reaction in self.partial_reactions
                )
            )
            for r in rs
        ]

    async def add_emoticon(self, emoticon: Emoticon) -> None:
        await self._state.react_to_chat_message(
            *self.channel._location,
            int(self.created_at.timestamp()),
            self.ordinal,
            str(emoticon),
            reaction_type=1,
            is_add=True,
        )
        self._state.dispatch(
            "reaction_add",
            MessageReaction(self._state, self, emoticon, None, self._state.user, DateTime.now(), self.ordinal),
        )

    async def remove_emoticon(self, emoticon: Emoticon) -> None:
        await self._state.react_to_chat_message(
            *self.channel._location,
            int(self.created_at.timestamp()),
            self.ordinal,
            str(emoticon),
            reaction_type=1,
            is_add=False,
        )
        self._state.dispatch(
            "reaction_remove",
            MessageReaction(self._state, self, emoticon, None, self._state.user, DateTime.now(), self.ordinal),
        )

    async def add_sticker(self, sticker: Sticker) -> None:
        await self._state.react_to_chat_message(
            *self.channel._location,
            int(self.created_at.timestamp()),
            self.ordinal,
            sticker.name,
            reaction_type=2,
            is_add=True,
        )
        self._state.dispatch(
            "reaction_add",
            MessageReaction(self._state, self, None, sticker, self._state.user, DateTime.now(), self.ordinal),
        )

    async def remove_sticker(self, sticker: Sticker) -> None:
        await self._state.react_to_chat_message(
            *self.channel._location,
            int(self.created_at.timestamp()),
            self.ordinal,
            sticker.name,
            reaction_type=2,
            is_add=False,
        )
        self._state.dispatch(
            "reaction_remove",
            MessageReaction(self._state, self, None, sticker, self._state.client.user, DateTime.now(), self.ordinal),
        )


ChatMessageT = TypeVar("ChatMessageT", bound="GroupMessage | ClanMessage", covariant=True)
GroupChannelProtos: TypeAlias = "chat.IncomingChatMessageNotification | chat.State | chat.ChatRoomState"


class Chat(Channel[ChatMessageT]):
    __slots__ = ("id", "name", "joined_at", "position", "last_message")

    def __init__(
        self, state: ConnectionState, group: ChatGroup[Any, Self], proto: GroupChannelProtos
    ):  # group is purposely unused
        super().__init__(state)
        self.id = int(proto.chat_id)
        self.name: str | None = None
        self.joined_at: datetime | None = None
        self.position: int | None = None
        self.last_message: ChatMessageT | None = None
        self._update(proto)

    def _update(self, proto: GroupChannelProtos) -> None:
        if isinstance(proto, (chat.State, chat.IncomingChatMessageNotification)):
            first, _, second = proto.chat_name.partition(" | ")
            self.name = second or first

        self.joined_at = (
            DateTime.from_timestamp(proto.time_joined) if isinstance(proto, chat.ChatRoomState) else self.joined_at
        )
        self.position = proto.sort_order if isinstance(proto, chat.State) else self.position
        (message_cls,) = self._type_args
        if isinstance(proto, chat.IncomingChatMessageNotification):
            steam_id = SteamID(proto.steamid_sender, type=Type.Individual)
            self.last_message = message_cls(proto, self, self._state.get_user(steam_id.id) or steam_id)  # type: ignore

    def __repr__(self) -> str:
        attrs = ("name", "id", "group" if self.group is not None else "clan", "position")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return self._location == other._location if isinstance(other, Chat) else NotImplemented

    @property
    def _location(self) -> tuple[ChatGroupID, ChannelID]:
        chat = self.clan or self.group
        assert chat is not None
        chat_id = chat._id
        assert chat_id is not None
        return chat_id, self.id

    @utils.classproperty
    def _type_args(cls: type[Chat]) -> tuple[type[ChatMessageT]]:  # type: ignore
        return cls.__orig_bases__[0].__args__  # type: ignore

    def _message_func(self, content: str) -> Coroutine[Any, Any, ChatMessageT]:
        return self._state.send_chat_message(*self._location, content)  # type: ignore

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_chat_image(*self._location, image)

    def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> ChatHistoryIterator[ChatMessageT, Self]:
        return ChatHistoryIterator(state=self._state, channel=self, limit=limit, before=before, after=after)

    # async def edit(self, *, name: str) -> None:
    #     await self._state.edit_channel(*self._location, name)


# class SteamIDMember(SteamID):  # TODO?
#     ...


class ChatGroup(SteamID, Generic[MemberT, ChatT]):
    """Base class for :class:`steam.Clan` and :class:`steam.Group`."""

    __slots__ = (
        "name",
        "_id",
        "game",
        "tagline",
        "avatar_url",
        "active_member_count",
        "chunked",
        "_state",
        "_members",
        "_partial_members",
        "_owner_id",
        "_top_members",
        "_channels",
        "_default_channel_id",
        "_roles",
        "_default_role_id",
    )
    name: str
    _id: ChatGroupID
    game: StatefulGame | None
    tagline: str
    avatar_url: str
    active_member_count: int
    chunked: bool
    _state: ConnectionState

    _members: dict[ID32, MemberT]
    _owner_id: ID32
    _top_members: list[ID32]
    _partial_members: dict[ID32, chat.Member]  # deleted after _members is populated (if chunked)

    _channels: dict[int, ChatT]
    _default_channel_id: int

    _roles: dict[int, Role]
    _default_role_id: int

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.chunked = False
        self.game: StatefulGame | None = None
        self._members = {}
        self._partial_members = {}
        self._channels: dict[int, ChatT] = {}
        self._roles: dict[int, Role] = {}

    @classmethod
    async def _from_proto(
        cls,
        state: ConnectionState,
        proto: chat.GetChatRoomGroupSummaryResponse,
        *,
        id: ID32 | ChatGroupID | None = None,
        maybe_chunk: bool = True,
    ) -> Self:
        self = cls(state, id if id is not None else proto.chat_group_id)
        self.name = proto.chat_group_name
        self._id = proto.chat_group_id
        self.active_member_count = proto.active_member_count
        self._owner_id = proto.accountid_owner
        self._top_members = proto.top_members
        self.tagline = proto.chat_group_tagline
        self.game = StatefulGame(state, id=proto.appid) if proto.appid else self.game

        self._default_role_id = proto.default_role_id
        self._update_channels(proto.chat_rooms, default_channel_id=proto.default_chat_id)

        if maybe_chunk:
            try:
                group_state = await self._state.set_chat_group_active(proto.chat_group_id)
            except WSException:
                pass
            else:
                self._partial_members = {member.accountid: member for member in group_state.members}
                self._roles = {
                    role.role_id: Role(self._state, self, role, permissions)  # type: ignore
                    for role in group_state.header_state.roles
                    for permissions in group_state.header_state.role_actions
                    if permissions.role_id == role.role_id
                }

            if self._state.auto_chunk_chat_groups:
                await self.chunk()

        return self

    @utils.classproperty
    def _type_args(cls: type[ChatGroup]) -> tuple[type[MemberT], type[ChatT]]:  # type: ignore
        return cls.__orig_bases__[0].__args__  # type: ignore

    async def _add_member(self, member: chat.Member) -> MemberT:
        member_cls, _ = self._type_args
        user = await self._state._maybe_user(member.accountid)
        assert isinstance(user, User)
        new_member = member_cls(self._state, self, user, member)
        if self.chunked:
            self._members[member.accountid] = new_member
        else:
            self._partial_members[member.accountid] = member
        return new_member

    def _remove_member(self, member: chat.Member) -> MemberT | None:
        if self.chunked:
            return self._members.pop(member.accountid, None)
        else:
            self._partial_members.pop(member.accountid, None)

    def _update_channels(
        self, channels: list[chat.State] | list[chat.ChatRoomState], *, default_channel_id: int | None = None
    ) -> None:
        _, channel_cls = self._type_args
        for channel in channels:
            try:
                new_channel = self._channels[channel.chat_id]
            except KeyError:
                new_channel = channel_cls(self._state, self, channel)
                self._channels[new_channel.id] = new_channel
            else:
                new_channel._update(channel)

        if default_channel_id is not None:
            self._default_channel_id = default_channel_id

    def _update_header_state(self, proto: chat.GroupHeaderState) -> None:
        self.name = proto.chat_name
        self._owner_id = proto.accountid_owner
        self.game = StatefulGame(self._state, id=proto.appid)
        self.tagline = proto.tagline
        self.avatar_url = utils._get_avatar_url(proto.avatar_sha)
        self._default_role_id = proto.default_role_id or self._default_role_id
        for role in proto.roles:
            for role_action in proto.role_actions:
                if role.role_id == role_action.role_id:
                    self._roles[role.role_id] = Role(self._state, self, role, role_action)  # type: ignore

    def __repr__(self) -> str:
        attrs = ("name", "id", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    @property
    def members(self) -> Sequence[MemberT]:
        """A list of the chat group's members."""
        return list(self._members.values())

    def get_member(self, id64: ID64) -> MemberT | None:
        """Get a member of the chat group by id.

        Parameters
        ----------
        id64
            The 64 bit ID of the member to get.
        """
        return self._members.get(id64 & 0xFFFFFFFF)  # TODO consider just passing ID32

    @property
    def owner(self):
        return self._members.get(self._owner_id) or SteamID(self._owner_id)

    @property
    def top_members(self) -> Sequence[MemberT | SteamID]:
        """A list of the chat group's top members."""
        return [(self._members.get(id) or SteamID(id)) for id in self._top_members]

    @property
    def me(self) -> MemberT:
        """The client user's account in this chat group."""
        return self._members[self._state.user.id]

    @property
    def channels(self) -> Sequence[ChatT]:
        """A list of the chat group's channels."""
        return list(self._channels.values())

    def get_channel(self, id: int) -> ChatT | None:
        """Get a channel from cache.

        Parameters
        ----------
        id
            The ID of the channel.
        """
        return self._channels.get(id)

    @property
    def default_channel(self) -> ChatT:
        """The group's default channel."""
        return self._channels[self._default_channel_id]

    @property
    def roles(self) -> Sequence[Role]:
        """A list of the group's roles."""
        return list(self._roles.values())

    def get_role(self, id: int) -> Role | None:
        """Get a role from cache.

        Parameters
        ----------
        id
            The ID of the role.
        """
        return self._roles.get(id)

    @property
    def default_role(self) -> Role:
        """The group's default role."""
        return self._roles[self._default_role_id]

    @abc.abstractmethod
    async def chunk(self) -> Sequence[MemberT]:
        """Get a list of all members in the group."""
        self.chunked = True
        del self._partial_members
        return self.members

    async def search(self, name: str) -> list[MemberT]:
        """Search for members in the chat group.

        Parameters
        ----------
        name
            The name of the member to search for.
        """
        msg: MsgProto[chat.SearchMembersResponse] = await self._state.ws.send_um_and_wait(
            "ChatRoom.SearchMembers",
            chat_group_id=self._id,
            search_text=name,
        )

        if self.chunked:
            return [self._members[user.accountid] for user in msg.body.matching_members]

        member_cls, _ = self._type_args
        users = [
            User(self._state, self._state.patch_user_from_ws({}, user.persona)) for user in msg.body.matching_members
        ]
        return [member_cls(self._state, self, user, self._partial_members[user.id]) for user in users]

    async def invite(self, user: User) -> None:
        """Invites a :class:`~steam.User` to the chat group.

        Parameters
        -----------
        user
            The user to invite to the chat group.
        """
        await self._state.invite_user_to_chat_group(user.id64, self._id)

    async def join(self, *, invite_code: str | None = None) -> None:
        """Joins the chat group.

        Parameters
        ----------
        invite_code
            The invite code to use to join the chat group.
        """
        await self._state.join_chat_group(self._id, invite_code)
        if self._state.auto_chunk_chat_groups:
            await self.chunk()

    async def leave(self) -> None:
        """Leaves the chat group."""
        await self._state.leave_chat_group(self._id)

    # TODO
    # async def edit(self, *, name: str | None = None, tagline: str | None = None, avatar: bytes | SupportsRead) -> None:
    #     """Edits the chat group."""
    #     await self._state.edit_chat_group(self._id, name, tagline, avatar)
    #
    # async def create_role(self) -> Role:  # chat.CreateRoleRequest
    #     ...
    #
    # async def create_channel(self) -> ChannelT:  # chat.CreateChatRoomRequest
    #     ...
    #
    # async def create_invite(self) -> InviteLink:  # chat.CreateInviteLinkRequest
    #     ...
    #
    # async def fetch_invite(self, code: str) -> InviteLink:  # chat.GetChatInviteLinkResponse
    #     ...
    #
    # async def invites(self) -> list[InviteLink]:  # chat.GetChatInvitesResponse
    #     ...
    #
    # add Member.x equivalent for these 3
    # async def mute(self, member: SteamID) -> None:  # chat.MuteUserRequest
    #     ...
    #
    # async def kick(self, member: SteamID) -> None:  # chat.KickUserRequest
    #     ...
    #
    # async def ban(self, member: SteamID) -> None:  # chat.SetUserBanStateRequest
    #     ...
    #
    # async def bans(self) -> list[Ban]:  # chat.GetBanListRequest
    #     ...
    #
    # async def unban(self, user: SteamID) -> None:  # chat.SetUserBanStateRequest
    #     ...
