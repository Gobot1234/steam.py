"""
The shared base classes for chat group interactions.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import abc
import asyncio
import logging
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeAlias, cast, overload, runtime_checkable

from typing_extensions import Self, TypeVar, get_original_bases

from . import utils
from ._const import UNIX_EPOCH, _HasChatGroupMixin
from .abc import Channel, ClanT, GroupT, Message, PartialUser
from .app import PartialApp
from .enums import ChatMemberJoinState, ChatMemberRank, Type
from .errors import WSException
from .id import _ID64_TO_ID32, ID
from .models import Avatar
from .protobufs import chat
from .reaction import Emoticon, MessageReaction, PartialMessageReaction, Sticker
from .role import Role
from .types.id import ID32, ChatGroupID, ChatID, Intable, RoleID
from .types.user import IndividualID
from .user import ClientUser, User, WrapsUser
from .utils import DateTime, cached_slot_property

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable, Sequence
    from datetime import datetime

    from .clan import Clan
    from .group import Group
    from .invite import ChatGroupInvite
    from .media import Media
    from .message import ClanMessage, GroupMessage
    from .state import ConnectionState


ChatT = TypeVar("ChatT", bound="Chat", default="Chat", covariant=True)
MemberT = TypeVar("MemberT", bound="Member", default="Member", covariant=True)
log = logging.getLogger(__name__)


@runtime_checkable
class _PartialMemberProto(
    _HasChatGroupMixin,
    Protocol,
    IndividualID if TYPE_CHECKING else object,  # type: ignore   # needs intersection types
):
    __slots__ = SLOTS = (
        "clan",
        "group",
        "rank",
        "join_state",
        "kick_expires_at",
        "_role_ids",
        "_state",
    )
    if not TYPE_CHECKING:
        __slots__ = ()

    _state: ConnectionState
    rank: ChatMemberRank
    join_state: ChatMemberJoinState
    _role_ids: tuple[RoleID, ...]
    kick_expires_at: datetime
    clan: Clan | None
    group: Group | None

    def _update(self, member: chat.Member, /) -> None:
        self.rank = ChatMemberRank.try_value(member.rank)
        self.join_state = ChatMemberJoinState.try_value(member.state)
        self._role_ids = cast("tuple[RoleID, ...]", tuple(member.role_ids))
        self.kick_expires_at = DateTime.from_timestamp(member.time_kick_expire)

    @property
    def roles(self) -> list[Role]:
        """The member's roles."""
        chat_group = self._chat_group
        return [chat_group._roles[role_id] for role_id in self._role_ids]

    @property
    def top_role(self) -> Role | None:
        """The member's top role."""
        return min(self.roles, key=attrgetter("ordinal"), default=None)

    async def add_role(self, role: Role, /) -> None:
        """Add a role to the member."""
        raise NotImplementedError
        chat_group = self._chat_group
        await chat_group.add_role(self, role)

    async def remove_role(self, role: Role, /) -> None:
        raise NotImplementedError
        chat_group = self._chat_group
        await chat_group.remove_role(self, role)

    async def mute(self, expires_at: datetime) -> None:
        """Mutes the member from the chat group."""
        chat_group = self._chat_group
        await chat_group.mute(self, expires_at)

    async def kick(self, expires_at: datetime) -> None:
        """Kicks the member from the chat group."""
        chat_group = self._chat_group
        await chat_group.kick(self, expires_at)

    async def ban(self) -> None:
        """Bans the member from the chat group."""
        chat_group = self._chat_group
        await chat_group.ban(self)


class PartialMember(PartialUser, _PartialMemberProto):  # type: ignore
    __slots__ = _PartialMemberProto.SLOTS

    clan: Clan | None
    group: Group | None

    @overload
    def __init__(self, state: ConnectionState, *, clan: Clan, member: chat.Member) -> None:
        ...

    @overload
    def __init__(self, state: ConnectionState, *, group: Group, member: chat.Member) -> None:
        ...

    def __init__(
        self, state: ConnectionState, *, clan: Clan | None = None, group: Group | None = None, member: chat.Member
    ) -> None:
        super().__init__(state, member.accountid)
        self.clan = clan
        self.group = group
        self._state = state
        self._update(member)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id!r} {f'clan={self.clan!r}' if self.clan else f'group={self.group!r}'} rank={self.rank!r}>"

    def copy(self) -> Self:
        return self.__class__(
            self._state,
            self.clan,
            self.group,
            chat.Member(
                self.id,
                self.join_state,  # type: ignore
                self.rank,  # type: ignore
                int(self.kick_expires_at.timestamp()),
                list(self._role_ids),
            ),
        )


if TYPE_CHECKING:

    class _BaseMember(WrapsUser, PartialMember, _PartialMemberProto):  # type: ignore
        pass

else:
    _BaseMember = WrapsUser


@PartialMember.register
class Member(_BaseMember, _HasChatGroupMixin, Generic[ClanT, GroupT]):
    """Represents a member of a chat group."""

    __slots__ = tuple(slot for slot in _BaseMember.__slots__ if slot not in {"_state"})

    def __init__(
        self, state: ConnectionState, chat_group: ChatGroup[Any, Any], user: User | ClientUser, member: chat.Member
    ) -> None:
        super().__init__(state, user)
        self.clan = cast(ClanT, None)
        self.group = cast(GroupT, None)

        self._update(member)

    _update: Callable[[chat.Member], None] = PartialMember._update  # type: ignore

    if not TYPE_CHECKING:
        roles = PartialMember.roles

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id!r} {f'clan={self.clan!r}' if self.clan else f'group={self.group!r}'} rank={self.rank!r}>"

    def copy(self) -> Self:
        return self.__class__(
            self._state,
            self._chat_group,
            self._user,
            chat.Member(
                self.id,
                chat.EChatRoomJoinState.Joined,
                self.rank,  # type: ignore
                int(self.kick_expires_at.timestamp()),
                list(self._role_ids),
            ),
        )


AuthorT = TypeVar("AuthorT", bound="PartialMember", default="PartialMember | Member", covariant=True)


class ChatMessage(Message[AuthorT, ChatT], Generic[AuthorT, MemberT, ChatT]):
    channel: ChatT
    author: AuthorT

    def __init__(self, proto: chat.IncomingChatMessageNotification, channel: ChatT, author: AuthorT) -> None:
        super().__init__(channel, proto)
        self.author = author
        self.created_at = DateTime.from_timestamp(proto.timestamp)
        self._mentions_ids = cast(tuple[ID32, ...], tuple(proto.mentions.ids))
        self.mentions_all = proto.mentions.mention_all
        self.mentions_here = proto.mentions.mention_here

    @classmethod
    def _from_history(
        cls, channel: ChatT, proto: chat.GetMessageHistoryResponseChatMessage  # type: ignore  # this is a constructor covariance is fine
    ) -> Self:
        self = cls.__new__(cls)  # skip __init__
        super().__init__(self, channel, proto)
        # if you want a fun time try and figure out the issues in calling these methods
        self.created_at = DateTime.from_timestamp(proto.server_timestamp)
        return self

    @property
    def _chat_group(self) -> Clan | Group:
        return self.channel._chat_group

    @property
    def mentions(self) -> list[MemberT | PartialMember]:
        """The members mentioned in the message."""
        return self._chat_group._maybe_members(self._mentions_ids)

    async def delete(self) -> None:
        """Deletes the message."""
        await self._state.delete_chat_messages(
            *self.channel._location, (int(self.created_at.timestamp()), self.ordinal)
        )

    async def fetch_reaction(self, emoticon: Emoticon | Sticker, /) -> list[MessageReaction]:
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
                user=self._chat_group._maybe_member(reactor),
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

    async def _react(self, emoticon: Sticker | Emoticon, add: bool) -> None:
        await self._state.react_to_chat_message(
            *self.channel._location,
            int(self.created_at.timestamp()),
            self.ordinal,
            str(emoticon) if isinstance(emoticon, Emoticon) else emoticon.name,
            reaction_type=emoticon._TYPE,
            is_add=add,
        )
        reaction = MessageReaction(
            self._state,
            self,
            emoticon if isinstance(emoticon, Emoticon) else None,  # type: ignore
            emoticon if isinstance(emoticon, Sticker) else None,  # type: ignore
            self._state.user,
            DateTime.now(),
            self.ordinal,
        )

        if add:
            self.reactions.append(reaction)
        else:
            try:
                self.reactions.remove(reaction)
            except ValueError:
                log.debug("Reaction removed for a reaction that wasn't added")
        self._state.dispatch(f"reaction_{'add' if add else 'remove'}", reaction)

    async def ack(self) -> None:
        await self._state.ack_chat_message(*self.channel._location, int(self.created_at.timestamp()))


ChatMessageT = TypeVar(
    "ChatMessageT", bound="GroupMessage | ClanMessage", default="GroupMessage | ClanMessage", covariant=True
)

GroupChannelProtos: TypeAlias = chat.IncomingChatMessageNotification | chat.State | chat.ChatRoomState


class Chat(Channel[ChatMessageT, ClanT, GroupT], _HasChatGroupMixin):
    __slots__ = ("id", "name", "joined_at", "position", "last_message", "_cs_location")

    def __init__(
        self, state: ConnectionState, chat_group: ChatGroup[Any, Self], proto: GroupChannelProtos
    ):  # chat_group is purposely unused for type checking purposes with chat_cls
        super().__init__(state)
        self.id = ChatID(proto.chat_id)
        """The ID of the channel."""
        self.name: str | None = None
        """
        The name of the channel, this could be the same as the :attr:`~steam.Clan.name`/:attr:`~steam.Group.name`,
        if it's the main channel.
        """
        self.joined_at: datetime | None = None
        """The time the client joined the chat."""
        self.position: int | None = None
        """The position of the channel in the channel list."""
        self.last_message: ChatMessageT | None = None
        """The last message sent in the channel."""
        self._update(proto)

    def _update(self, proto: GroupChannelProtos, /) -> None:
        if isinstance(proto, (chat.State, chat.IncomingChatMessageNotification)):
            first, _, second = proto.chat_name.partition(" | ")
            self.name = second or first

        self.joined_at = (
            DateTime.from_timestamp(proto.time_joined) if isinstance(proto, chat.ChatRoomState) else self.joined_at
        )
        self.position = proto.sort_order if isinstance(proto, chat.State) else self.position

    def __repr__(self) -> str:
        attrs = ("name", "id", "group" if self.group is not None else "clan", "position")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Chat) and self._location == other._location

    def __hash__(self) -> int:
        return hash(self._location)

    @cached_slot_property("_cs_location")
    def _location(self) -> tuple[ChatGroupID, ChatID]:
        chat_id = self._chat_group._id
        assert chat_id is not None
        return chat_id, self.id

    @utils.classproperty
    def _type_args(cls: type[Self]) -> tuple[type[ChatMessageT], type[ClanT], type[GroupT]]:  # type: ignore
        return get_original_bases(cls)[0].__args__

    def _send_message(self, content: str) -> Coroutine[Any, Any, ChatMessageT]:
        return self._state.send_chat_message(*self._location, content)  # type: ignore

    def _send_media(self, media: Media) -> Coroutine[Any, Any, None]:
        return self._state.http.send_chat_media(*self._location, media)

    async def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[ChatMessageT, None]:
        after = after or UNIX_EPOCH
        before = before or DateTime.now()

        after_timestamp = int(after.timestamp())
        before_timestamp = int(before.timestamp())
        last_message_timestamp = before_timestamp
        last_ordinal: int = getattr(self.last_message, "ordinal", 0)
        yielded = 0
        message_cls, *_ = self._type_args

        while True:
            resp = await self._state.fetch_chat_history(
                *self._location, start=after_timestamp, last=last_message_timestamp, last_ordinal=last_ordinal
            )
            message = None
            messages: list[ChatMessageT] = []

            for message in resp.messages:
                new_message = message_cls._from_history(self, message)  # type: ignore  # there's no easy way to do this
                if not after < new_message.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return

                new_message.author = self._chat_group._maybe_member(_ID64_TO_ID32(message.sender))
                new_message.partial_reactions = [
                    PartialMessageReaction(
                        self._state,
                        new_message,
                        Emoticon(self._state, r.reaction) if r.reaction_type == Emoticon._TYPE else None,  # type: ignore
                        Sticker(self._state, r.reaction) if r.reaction_type == Sticker._TYPE else None,  # type: ignore
                    )
                    for r in message.reactions
                ]
                messages.append(new_message)
                yielded += 1

            if message is None:
                return

            last_message_timestamp = message.server_timestamp
            last_ordinal = message.ordinal

            for message_ in messages:
                yield message_

            if not resp.more_available:
                return

    async def edit(self, *, name: str | None = None, move_below: Self | None) -> None:
        """Edit the chat.

        Parameters
        ----------
        name
            The new name of the chat.
        move_below
            The chat to move this chat below.
        """
        await self._state.edit_chat(*self._location, name, move_below.id if move_below else None)

    async def delete(self) -> None:
        """Delete the chat."""
        await self._state.delete_chat(*self._location)

    async def bulk_delete(self, messages: Iterable[ChatMessage], /) -> None:
        """Bulk delete messages.

        Parameters
        ----------
        messages
            The messages to delete.
        """
        await self._state.delete_chat_messages(
            *self._location, *((int(m.created_at.timestamp()), m.ordinal) for m in messages)
        )

    async def fetch_message(self, id: int, /) -> ChatMessageT | None:
        message = await super().fetch_message(id)
        if message is not None:
            message.reactions = await message.fetch_reactions()
            return message


ChatGroupTypeT = TypeVar(
    "ChatGroupTypeT", bound=Literal[Type.Clan, Type.Chat], default=Literal[Type.Clan, Type.Chat], covariant=True
)


class ChatGroup(ID[ChatGroupTypeT], Generic[MemberT, ChatT, ChatGroupTypeT]):
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
        "_mods",
        "_officers",
        "_top_members",
        "_channels",
        "_default_channel_id",
        "_roles",
        "_default_role_id",
        "_avatar_sha",
        "_invites",
    )
    name: str
    """The name of the chat group."""
    _id: ChatGroupID
    app: PartialApp | None
    """The :class:`steam.PartialApp` that the chat group is associated with."""
    tagline: str
    """The tagline of the chat group."""
    active_member_count: int
    """The number of users in the clan."""
    chunked: bool
    """Whether the chat group has been chunked."""
    _avatar_sha: bytes
    _state: ConnectionState

    _owner_id: ID32
    _top_members: list[ID32]

    _default_channel_id: ChatID
    _default_role_id: RoleID

    def __init__(self, state: ConnectionState, id: Intable, type: ChatGroupTypeT | None = None):
        super().__init__(id, type=type)
        self._state = state
        self._init()

    def _init(self) -> None:
        self.chunked = False
        self.app: PartialApp | None = None
        self._members: dict[ID32, MemberT] = {}
        self._partial_members: dict[ID32, chat.Member] = {}  # deleted after _members is populated (if chunked)
        self._channels: dict[ChatID, ChatT] = {}
        self._roles: dict[RoleID, Role] = {}
        self._officers: list[ID32] = []
        self._mods: list[ID32] = []
        self._invites: dict[ID32, ChatGroupInvite] = {}

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
        self._top_members = cast(list[ID32], proto.top_members)
        self.tagline = proto.chat_group_tagline
        self.app = PartialApp(state, id=proto.appid) if proto.appid else self.app
        self._avatar_sha = proto.chat_group_avatar_sha

        self._default_role_id = RoleID(proto.default_role_id)
        self._update_channels(proto.chat_rooms, default_channel_id=proto.default_chat_id)

        if maybe_chunk:
            try:
                group_state = await self._state.set_chat_group_active(self._id)
            except WSException:
                pass
            else:
                self._update_group_state(group_state)

            await self._maybe_chunk()

        return self

    async def _maybe_chunk(self):
        if self._state.auto_chunk_chat_groups:
            await self.chunk()

        self._officers = [id for id, member in self._partial_members.items() if member.rank is ChatMemberRank.Officer]
        self._mods = [id for id, member in self._partial_members.items() if member.rank is ChatMemberRank.Moderator]

    @utils.classproperty
    def _type_args(cls: type[Self]) -> tuple[type[MemberT], type[ChatT], type[ChatGroupTypeT]]:  # type: ignore
        return get_original_bases(cls)[0].__args__

    async def _add_member(self, member: chat.Member) -> MemberT:
        member_cls, _, _ = self._type_args
        id32 = ID32(member.accountid)
        user = await self._state._maybe_user(id32)
        new_member = member_cls(self._state, self, user, member)
        self._members[id32] = new_member
        return new_member

    def _remove_member(self, member: chat.Member) -> MemberT | PartialMember | None:
        id32 = ID32(member.accountid)
        try:
            return self._members.pop(id32)
        except KeyError:
            return self._get_partial_member(id32)
        finally:
            self._partial_members.pop(id32, None)

    def _update_channels(
        self, channels: list[chat.State] | list[chat.ChatRoomState], *, default_channel_id: int | None = None
    ) -> None:
        _, chat_cls, _ = self._type_args
        for channel in channels:
            try:
                new_channel = self._channels[ChatID(channel.chat_id)]
            except KeyError:
                new_channel = chat_cls(self._state, self, channel)
                self._channels[new_channel.id] = new_channel
            else:
                new_channel._update(channel)

        if default_channel_id is not None:
            self._default_channel_id = ChatID(default_channel_id)

    def _update_header_state(self, proto: chat.GroupHeaderState, /) -> None:
        self.name = proto.chat_name
        self._owner_id = ID32(proto.accountid_owner)
        self.app = PartialApp(self._state, id=proto.appid)
        self.tagline = proto.tagline
        self._avatar_sha = proto.avatar_sha
        self._default_role_id = RoleID(proto.default_role_id) or self._default_role_id
        for role in proto.roles:
            for role_action in proto.role_actions:
                if role.role_id == role_action.role_id:
                    self._roles[role.role_id] = Role(self._state, self, role, role_action)  # type: ignore

    def _update_group_state(self, group_state: chat.GroupState):
        self._partial_members = cast(
            dict[ID32, chat.Member], {member.accountid: member for member in group_state.members}
        )
        self._roles = {
            RoleID(role.role_id): Role(self._state, self, role, permissions)
            for role in group_state.header_state.roles
            for permissions in group_state.header_state.role_actions
            if permissions.role_id == role.role_id
        }
        member_cls, _, _ = self._type_args
        try:
            self._members = {
                self._state.user.id: member_cls(
                    self._state,
                    self,
                    self._state.user,
                    self._partial_members[self._state.user.id],
                )
            }
        except KeyError:
            self._members = {}  # we aren't a member

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

    def get_member(self, id64: int, /) -> MemberT | None:
        """Get a member of the chat group by id.

        Parameters
        ----------
        id64
            The 64 bit ID of the member to get.
        """
        return self._members.get(_ID64_TO_ID32(id64))

    @abc.abstractmethod
    def _get_partial_member(self, id: ID32, /) -> PartialMember:
        raise NotImplementedError

    def _maybe_member(self, id: ID32, /) -> MemberT | PartialMember:
        if (member := self._members.get(id)) is not None:
            return member

        if (user := self._state.get_user(id)) is not None:
            member_cls, _, _ = self._type_args
            self._members[id] = member = member_cls(self._state, self, user, self._partial_members.pop(id))
            return member

        return self._get_partial_member(id)

    def _maybe_members(self, ids: Iterable[ID32], /) -> list[MemberT | PartialMember]:
        members: list[MemberT | PartialMember] = []
        member_cls, _, _ = self._type_args
        for id in ids:
            if (member := self._members.get(id)) is not None:
                members.append(member)
            elif (user := self._state.get_user(id)) is not None:
                self._members[id] = member = member_cls(self._state, self, user, self._partial_members.pop(id))
                members.append(member)
            else:
                members.append(self._get_partial_member(id))

        return members

    @property
    def owner(self) -> MemberT | PartialMember:
        """The chat group's owner."""
        return self._maybe_member(self._owner_id)

    @property
    def officers(self) -> list[MemberT | PartialMember]:
        """A list of the chat groups's administrators."""
        return self._maybe_members(self._officers)

    @property
    def mods(self) -> list[MemberT | PartialMember]:
        """A list of the chat group's moderators."""
        return self._maybe_members(self._mods)

    @property
    def top_members(self) -> Sequence[MemberT | PartialMember]:
        """A list of the chat group's top members."""
        return self._maybe_members(self._top_members)

    @property
    def me(self) -> MemberT:
        """The client user's account in this chat group."""
        return self._members[self._state.user.id]

    @property
    def channels(self) -> Sequence[ChatT]:
        """A list of the chat group's channels."""
        return list(self._channels.values())

    def get_channel(self, id: int, /) -> ChatT | None:
        """Get a channel from cache.

        Parameters
        ----------
        id
            The ID of the channel.
        """
        return self._channels.get(ChatID(id))

    @property
    def default_channel(self) -> ChatT:
        """The group's default channel."""
        return self._channels[self._default_channel_id]

    @property
    def roles(self) -> Sequence[Role]:
        """A list of the group's roles."""
        return list(self._roles.values())

    def get_role(self, id: int, /) -> Role | None:
        """Get a role from cache.

        Parameters
        ----------
        id
            The ID of the role.
        """
        return self._roles.get(RoleID(id))

    @property
    def default_role(self) -> Role:
        """The group's default role."""
        return self._roles[self._default_role_id]

    @property
    def avatar(self) -> Avatar:
        """The chat group's avatar."""
        return Avatar(self._state, self._avatar_sha, suffix="256")

    @abc.abstractmethod
    async def chunk(self) -> Sequence[MemberT]:
        """Get a list of all members in the group."""
        self.chunked = True
        del self._partial_members
        return self.members

    async def search(self, name: str) -> Sequence[MemberT]:
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

        return cast(
            list[MemberT],
            self._maybe_members(
                user.id for user in [self._state._store_user(user.persona) for user in msg.matching_members]
            ),
        )

    async def invite(self, user: User, /) -> None:
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

    async def edit(self, *, name: str | None = None, tagline: str | None = None, avatar: Media | None = None) -> None:
        """Edits the chat group.

        Parameters
        ----------
        name
            The new name of the chat group. If ``None``, the name will not be changed.
        tagline
            The new tagline of the chat group. If ``None``, the tagline will not be changed.
        avatar
            The new avatar of the chat group. If ``None``, the avatar will not be changed.
        """
        await self._state.edit_chat_group(self._id, name, tagline, avatar)

    async def create_role(self, name: str) -> Role:
        """Creates a role in the chat group.

        Parameters
        ----------
        name
            The name of the role to create.
        """
        return await self._state.create_role(self._id, name)

    async def create_channel(self, name: str) -> ChatT:
        """Creates a channel in the chat group.

        Parameters
        ----------
        name
            The name of the channel to create.
        """
        state = await self._state.create_chat(self._id, name)
        _, chat_cls, _ = self._type_args
        return chat_cls(self._state, self, state)

    # async def create_invite(self) -> InviteLink:  # chat.CreateInviteLinkRequest
    #     ...
    #
    # async def fetch_invite(self, code: str) -> InviteLink:  # chat.GetChatInviteLinkResponse
    #     ...
    #
    # async def invites(self) -> list[InviteLink]:  # chat.GetChatInvitesResponse
    #     ...
    #
    async def mute(self, member: IndividualID, expires_at: datetime) -> None:
        """Mutes a member of the chat group.

        Parameters
        ----------
        member
            The member to mute.
        expires_at
            When the mute expires.
        """
        await self._state.mute_chat_group_member(self._id, member.id64, expires_at)

    async def kick(self, member: IndividualID, expires_at: datetime) -> None:
        """Kicks a member of the chat group.

        Parameters
        ----------
        member
            The member to kick.
        expires_at
            When the kick expires.
        """
        await self._state.kick_chat_group_member(self._id, member.id64, expires_at)

    async def ban(self, member: IndividualID) -> None:
        """Bans a member of the chat group."""
        await self._state.set_chat_group_ban_state(self._id, member.id64, True)

    async def unban(self, user: IndividualID) -> None:
        """Unbans a member of the chat group."""
        await self._state.set_chat_group_ban_state(self._id, user.id64, False)

    # async def bans(self) -> list[Ban]:  # chat.GetBanListRequest
    #     ...
