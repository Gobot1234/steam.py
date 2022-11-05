"""
The shared base classes for chat group interactions.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeAlias, TypeVar, cast

from typing_extensions import Self

from . import utils
from ._const import MISSING, UNIX_EPOCH
from .abc import Channel, Message
from .app import PartialApp
from .enums import ChatMemberRank, Type
from .errors import WSException
from .id import ID
from .models import Avatar
from .protobufs import chat
from .reaction import Emoticon, MessageReaction, PartialMessageReaction, Sticker
from .role import Role
from .types.id import ID32, ID64, ChatGroupID, ChatID, Intable
from .user import User, WrapsUser
from .utils import DateTime

if TYPE_CHECKING:
    from .channel import ClanChannel, GroupChannel
    from .clan import Clan
    from .group import Group
    from .image import Image
    from .message import ClanMessage, GroupMessage
    from .state import ConnectionState


ChatT = TypeVar("ChatT", bound="Chat[Any]", covariant=True)
MemberT = TypeVar("MemberT", bound="Member", covariant=True)


class _PartialMemberProto(Protocol):
    _state: ConnectionState
    rank: ChatMemberRank
    _role_ids: tuple[int, ...]
    kick_expires_at: datetime
    clan: Clan | None
    group: Group | None


class PartialMember(ID, _PartialMemberProto):
    __slots__ = (
        "clan",
        "group",
        "rank",
        "kick_expires_at",
        "_role_ids",
        "_state",
    )

    clan: Clan | None
    group: Group | None

    def __init__(self, state: ConnectionState, chat_group: ChatGroup[Any, Any], member: chat.Member) -> None:
        super().__init__(member.accountid, type=Type.Individual)
        self.clan = None
        self.group = None
        self._state = state
        self._update(member)

    def _update(self: _PartialMemberProto, member: chat.Member) -> None:
        self.rank = ChatMemberRank.try_value(member.rank)
        self._role_ids = tuple(member.role_ids)
        self.kick_expires_at = DateTime.from_timestamp(member.time_kick_expire)

    @property
    def roles(self: _PartialMemberProto) -> list[Role]:
        """The member's roles."""
        chat_group = self.group or self.clan
        assert chat_group is not None
        return [chat_group._roles[role_id] for role_id in self._role_ids]


class Member(WrapsUser):
    """Represents a member of a chat group."""

    __slots__ = (
        "clan",
        "group",
        "rank",
        "kick_expires_at",
        "_role_ids",
    )

    rank: ChatMemberRank
    kick_expires_at: datetime
    _role_ids: tuple[int, ...]

    def __init__(
        self, state: ConnectionState, chat_group: ChatGroup[Any, Any], user: User, member: chat.Member
    ) -> None:
        super().__init__(state, user)
        self.clan: Clan | None = None
        self.group: Group | None = None

        self._update(member)

    _update: Callable[[chat.Member], None] = PartialMember._update  # type: ignore
    roles = PartialMember.roles

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
    author: Member | PartialMember

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: Any, author: Member | PartialMember):
        super().__init__(channel, proto)
        self.author = author
        self.created_at = DateTime.from_timestamp(proto.timestamp)

    @property
    def _chat_group(self) -> Clan | Group:
        return self.channel._chat_group

    async def fetch_reaction(self, emoticon: Emoticon | Sticker) -> list[MessageReaction]:
        """Fetches the reactions to this message with a given emoticon."""
        reactors = await self._state.fetch_message_reactors(
            *self.channel._location,
            server_timestamp=int(self.created_at.timestamp()),
            ordinal=self.ordinal,
            reaction_name=str(emoticon) if isinstance(emoticon, Emoticon) else emoticon.name,
            reaction_type=emoticon._TYPE,
        )

        reaction = utils.find(
            lambda r: (r.emoticon or r.sticker).name == emoticon.name, self.partial_reactions  # type: ignore
        )
        assert reaction
        return [
            MessageReaction(
                self._state,
                self,
                reaction.emoticon,  # type: ignore
                reaction.sticker,  # type: ignore  # needs conditional types
                user=self._chat_group._members.get(reactor) or ID(reactor),
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
            reaction_type=emoticon._TYPE,
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
            reaction_type=emoticon._TYPE,
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
            reaction_type=sticker._TYPE,
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
            reaction_type=sticker._TYPE,
            is_add=False,
        )
        self._state.dispatch(
            "reaction_remove",
            MessageReaction(self._state, self, None, sticker, self._state.client.user, DateTime.now(), self.ordinal),
        )


ChatMessageT = TypeVar("ChatMessageT", bound="GroupMessage | ClanMessage", covariant=True)
GroupChannelProtos: TypeAlias = chat.IncomingChatMessageNotification | chat.State | chat.ChatRoomState


class Chat(Channel[ChatMessageT]):
    __slots__ = ("id", "name", "joined_at", "position", "last_message")

    def __init__(
        self, state: ConnectionState, group: ChatGroup[Any, Self], proto: GroupChannelProtos
    ):  # group is purposely unused
        super().__init__(state)
        self.id = ChatID(proto.chat_id)
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
        if isinstance(proto, chat.IncomingChatMessageNotification):
            steam_id = ID(proto.steamid_sender, type=Type.Individual)
            (message_cls,) = self._type_args
            self.last_message = message_cls(proto, self, self._chat_group.get_member(steam_id.id64) or steam_id)

    def __repr__(self) -> str:
        attrs = ("name", "id", "group" if self.group is not None else "clan", "position")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return self._location == other._location if isinstance(other, Chat) else NotImplemented

    @property
    def _location(self) -> tuple[ChatGroupID, ChatID]:
        chat_id = self._chat_group._id
        assert chat_id is not None
        return chat_id, self.id

    @property
    def _chat_group(self) -> Clan | Group:
        chat_group = self.clan or self.group
        assert chat_group is not None
        return chat_group

    @utils.classproperty
    def _type_args(cls: type[Chat]) -> tuple[type[ChatMessageT]]:  # type: ignore
        return cls.__orig_bases__[0].__args__  # type: ignore

    def _message_func(self, content: str) -> Coroutine[Any, Any, ChatMessageT]:
        return self._state.send_chat_message(*self._location, content)  # type: ignore

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_chat_image(*self._location, image)

    async def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[ChatMessageT, None]:
        after = after or UNIX_EPOCH
        before = before or DateTime.now()

        chat_group = self._chat_group
        after_timestamp = int(after.timestamp())
        before_timestamp = int(before.timestamp())
        last_message_timestamp = before_timestamp
        last_ordinal: int = getattr(self.last_message, "ordinal", 0)
        yielded = 0
        (message_cls,) = self._type_args

        while True:
            resp = await self._state.fetch_chat_group_history(
                *self._location, start=after_timestamp, last=last_message_timestamp, last_ordinal=last_ordinal
            )
            message = None
            messages: list[ChatMessageT] = []

            for message in resp.messages:
                new_message = message_cls.__new__(message_cls)
                Message.__init__(new_message, channel=self, proto=message)
                new_message.created_at = DateTime.from_timestamp(message.server_timestamp)
                if not after < new_message.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return

                new_message.author = ID(message.sender)
                emoticon_reactions = [
                    PartialMessageReaction(
                        self._state,
                        new_message,
                        Emoticon(self._state, r.reaction),
                        None,
                    )
                    for r in message.reactions
                    if r.reaction_type == 1
                ]
                sticker_reactions = [
                    PartialMessageReaction(
                        self._state,
                        new_message,
                        None,
                        Sticker(self._state, r.reaction),
                    )
                    for r in message.reactions
                    if r.reaction_type == 2
                ]
                new_message.partial_reactions = emoticon_reactions + sticker_reactions

                messages.append(new_message)
                yielded += 1

            if message is None:
                return

            last_message_timestamp = message.server_timestamp
            last_ordinal = message.ordinal

            for message_, author in zip(messages, chat_group._maybe_members(m.author.id for m in messages)):
                message_.author = author
                yield message_

            if not resp.more_available:
                return

    # async def edit(self, *, name: str) -> None:
    #     await self._state.edit_channel(*self._location, name)


class ChatGroup(ID, Generic[MemberT, ChatT]):
    """Base class for :class:`steam.Clan` and :class:`steam.Group`."""

    __slots__ = (
        "name",
        "_id",
        "app",
        "tagline",
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
        "_avatar_sha",
    )
    name: str
    _id: ChatGroupID
    app: PartialApp | None
    tagline: str
    avatar_url: str
    active_member_count: int
    chunked: bool
    _avatar_sha: bytes
    _state: ConnectionState

    _members: dict[ID32, MemberT]
    _owner_id: ID32
    _top_members: list[ID32]
    _partial_members: dict[ID32, chat.Member]  # deleted after _members is populated (if chunked)

    _channels: dict[int, ChatT]
    _default_channel_id: int

    _roles: dict[int, Role]
    _default_role_id: int

    def __init__(self, state: ConnectionState, id: Intable, type: Type = MISSING):
        super().__init__(id, type=type)
        self._state = state
        self.chunked = False
        self.app: PartialApp | None = None
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
        id: ChatGroupID | None = None,
        maybe_chunk: bool = True,
    ) -> Self:
        self = cls(state, id if id is not None else proto.chat_group_id)
        self.name = proto.chat_group_name
        self._id = ChatGroupID(proto.chat_group_id)
        self.active_member_count = proto.active_member_count
        self._owner_id = ID32(proto.accountid_owner)
        self._top_members = [ID32(id) for id in proto.top_members]
        self.tagline = proto.chat_group_tagline
        self.app = PartialApp(state, id=proto.appid) if proto.appid else self.app
        self._avatar_sha = proto.chat_group_avatar_sha

        self._default_role_id = proto.default_role_id
        self._update_channels(proto.chat_rooms, default_channel_id=proto.default_chat_id)

        if maybe_chunk:
            try:
                group_state = await self._state.set_chat_group_active(self._id)
            except WSException:
                pass
            else:
                self._partial_members = {ID32(member.accountid): member for member in group_state.members}
                self._roles = {
                    role.role_id: Role(self._state, self, role, permissions)  # type: ignore
                    for role in group_state.header_state.roles
                    for permissions in group_state.header_state.role_actions
                    if permissions.role_id == role.role_id
                }
                member_cls, _ = self._type_args
                self._members = {
                    self._state.user.id: member_cls(
                        self._state, self, self._state.user, self._partial_members[self._state.user.id]  # type: ignore
                    )
                }

            if self._state.auto_chunk_chat_groups:
                await self.chunk()

        return self

    @utils.classproperty
    def _type_args(cls: type[Self]) -> tuple[type[MemberT], type[ChatT]]:  # type: ignore
        return cls.__orig_bases__[0].__args__  # type: ignore

    async def _add_member(self, member: chat.Member) -> MemberT:
        member_cls, _ = self._type_args
        id32 = ID32(member.accountid)
        user = await self._state._maybe_user(id32)
        assert isinstance(user, User)
        new_member = member_cls(self._state, self, user, member)
        if self.chunked:
            self._members[id32] = new_member
        else:
            self._partial_members[id32] = member
        return new_member

    def _remove_member(self, member: chat.Member) -> MemberT | None:
        id32 = ID32(member.accountid)
        if self.chunked:
            return self._members.pop(id32, None)
        else:
            self._partial_members.pop(id32, None)

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
        self._owner_id = ID32(proto.accountid_owner)
        self.app = PartialApp(self._state, id=proto.appid)
        self.tagline = proto.tagline
        self._avatar_sha = proto.avatar_sha
        self._default_role_id = proto.default_role_id or self._default_role_id
        for role in proto.roles:
            for role_action in proto.role_actions:
                if role.role_id == role_action.role_id:
                    self._roles[role.role_id] = Role(self._state, self, role, role_action)  # type: ignore

    def __repr__(self) -> str:
        attrs = ("name", "id", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr, MISSING)!r}" for attr in attrs]
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

    def _maybe_members(self, ids: Iterable[ID32]) -> list[MemberT | PartialMember]:
        if self.chunked:
            return [self._members[id] for id in ids if id in self._members]
        else:
            return [
                PartialMember(self._state, self, self._partial_members[id]) for id in ids if id in self._partial_members
            ]

    @property
    def owner(self):
        return self._members.get(self._owner_id) or ID(self._owner_id)

    @property
    def top_members(self) -> Sequence[MemberT | ID]:
        """A list of the chat group's top members."""
        return [(self._members.get(id) or ID(id)) for id in self._top_members]

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

    @property
    def avatar(self) -> Avatar:
        """The chat group's avatar."""
        return Avatar(self._state, self._avatar_sha)

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
        msg: chat.SearchMembersResponse = await self._state.ws.send_um_and_wait(
            chat.SearchMembersRequest(
                chat_group_id=self._id,
                search_text=name,
            )
        )

        if self.chunked:
            return [self._members[ID32(user.accountid)] for user in msg.matching_members]

        member_cls, _ = self._type_args
        users = [User(self._state, user.persona) for user in msg.matching_members]
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
    # async def mute(self, member: ID) -> None:  # chat.MuteUserRequest
    #     ...
    #
    # async def kick(self, member: ID) -> None:  # chat.KickUserRequest
    #     ...
    #
    # async def ban(self, member: ID) -> None:  # chat.SetUserBanStateRequest
    #     ...
    #
    # async def bans(self) -> list[Ban]:  # chat.GetBanListRequest
    #     ...
    #
    # async def unban(self, user: ID) -> None:  # chat.SetUserBanStateRequest
    #     ...
