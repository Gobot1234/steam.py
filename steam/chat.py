"""
The shared base classes for chat group interactions.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import Coroutine, Sequence
from datetime import datetime
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from typing_extensions import Self, TypeAlias

from . import utils
from .abc import BaseUser, Channel, Message, Messageable, SteamID
from .enums import ChatMemberRank, Type
from .errors import WSForbidden
from .game import StatefulGame
from .iterators import ChatHistoryIterator
from .protobufs import MsgProto, chat
from .reaction import Emoticon, MessageReaction, Sticker
from .role import Role
from .user import User
from .utils import DateTime

if TYPE_CHECKING:
    from .channel import ClanChannel, GroupChannel
    from .clan import Clan
    from .group import Group
    from .image import Image
    from .message import Authors, ClanMessage, GroupMessage, UserMessage
    from .state import ConnectionState
    from .types.id import ID64, ChannelID, ChatGroupID


ChatT = TypeVar("ChatT", bound="Chat[Any]", covariant=True)
MemberT = TypeVar("MemberT", bound="Member", covariant=True)


class WrapsUser(User if TYPE_CHECKING else BaseUser):
    __slots__ = ("_user",)

    def __init__(self, state: ConnectionState, user: User):
        super().__init__(user.id64, type=Type.Individual)  # type: ignore
        self._user = user
        self._state = state

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        for name, function in set(User.__dict__.items()) - set(object.__dict__.items()):
            setattr(cls, name, function)
        for name in (*User.__slots__, *BaseUser.__slots__):
            setattr(cls, name, property(attrgetter(f"_user.{name}")))  # TODO time this with a compiled property
            # probably wont be different than the above

        User.register(cls)


class Member(WrapsUser, Messageable["UserMessage"]):
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

    def __init__(self, state: ConnectionState, user: User, proto: chat.Member) -> None:
        super().__init__(state, user)
        self.clan = None
        self.group = None
        self._update(proto)

    def _update(self, proto: chat.Member) -> None:
        self.rank = ChatMemberRank.try_value(proto.rank)
        self._role_ids = tuple(proto.role_ids)
        self.kick_expires_at = DateTime.from_timestamp(proto.time_kick_expire)

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
        is_emoticon = isinstance(emoticon, Emoticon)
        reactors = await self._state.fetch_message_reactors(
            *self.channel._location,
            server_timestamp=int(self.created_at.timestamp()),
            ordinal=self.ordinal,
            reaction_name=str(emoticon) if is_emoticon else emoticon.name,
            reaction_type=1 if is_emoticon else 2,
        )

        reaction = utils.find(
            lambda r: (r.emoticon or r.sticker).name == emoticon.name, self.partial_reactions
        )  # type: ignore
        assert reaction
        return [
            MessageReaction(
                self._state,
                self,
                reaction.emoticon,
                reaction.sticker,
                user=reactor,
            )
            for reactor in await self._state._maybe_users(reactors)
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
        self, state: ConnectionState, group: ChatGroup[Any, Any], proto: GroupChannelProtos
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
        message_cls: type[ChatMessageT] = self.__class__.__orig_bases__[0].__args__[0]  # type: ignore
        if isinstance(proto, chat.IncomingChatMessageNotification):
            steam_id = SteamID(proto.steamid_sender, type=Type.Individual)
            self.last_message = message_cls(proto, self, self._state.get_user(steam_id.id64) or steam_id)  # type: ignore

    def __repr__(self) -> str:
        cls = self.__class__
        attrs = ("name", "id", "group" if self.group is not None else "clan", "position")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{cls.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return self._location == other._location if isinstance(other, Chat) else NotImplemented

    @property
    def _location(self) -> tuple[ChatGroupID, ChannelID]:
        chat = self.clan or self.group
        assert chat is not None
        chat_id = chat._id
        assert chat_id is not None
        return chat_id, self.id

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


class ChatGroup(SteamID, Generic[MemberT, ChatT]):
    __slots__ = (
        "name",
        "top_members",
        "game",
        "owner",
        "tagline",
        "avatar_url",
        "active_member_count",
        "_state",
        "_members",
        "_channels",
        "_default_channel_id",
        "_roles",
        "_default_role_id",
    )
    name: str
    top_members: Sequence[MemberT | SteamID]
    game: StatefulGame
    owner: User
    tagline: str
    avatar_url: str
    _state: ConnectionState

    _members: dict[ID64, MemberT]

    _channels: dict[int, ChatT]
    _default_channel_id: int

    _roles: dict[int, Role]
    _default_role_id: int

    @classmethod
    @abc.abstractmethod
    async def _from_proto(
        cls,
        state: ConnectionState,
        proto: chat.GetChatRoomGroupSummaryResponse,
    ) -> Self:
        raise NotImplemented

    @property
    @abc.abstractmethod
    def _id(self) -> ChatGroupID:
        raise NotImplementedError

    @_id.setter
    def _id(self, value: ChatGroupID) -> None:
        raise NotImplementedError

    def _update_channels(
        self, channels: list[chat.State] | list[chat.ChatRoomState], *, default_channel_id: int | None = None
    ) -> None:
        channel_cls: type[ChatT] = self.__class__.__orig_bases__[0].__args__[1]  # type: ignore
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
        self.owner = self._state.get_user(proto.accountid_owner) or self.owner
        self.game = StatefulGame(self._state, id=proto.appid)
        self.tagline = proto.tagline
        self.avatar_url = utils._get_avatar_url(proto.avatar_sha)
        self._default_role_id = proto.default_role_id or self._default_role_id
        for role in proto.roles:
            for role_action in proto.role_actions:
                if role.role_id == role_action.role_id:
                    self._roles[role.role_id] = Role(self._state, self, role, role_action)  # type: ignore

    async def _populate_roles(self, actions: list[chat.RoleActions]) -> None:
        if self._id is None:
            return
        try:
            roles = await self._state.fetch_chat_group_roles(self._id)
        except WSForbidden:
            pass
        else:
            self._roles = {
                role.role_id: Role(self._state, self, role, permissions)  # type: ignore
                for role in roles
                for permissions in actions
                if permissions.role_id == role.role_id
            }

    def __repr__(self) -> str:
        attrs = ("name", "id", "type", "universe", "instance")
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
        return self._members.get(id64)

    @property
    def me(self) -> MemberT:
        """The client user's account in this chat group."""
        return self._members[self._state.user.id64]

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

    async def chunk(self) -> Sequence[MemberT]:
        """Get a list of all members in the group."""
        assert self._id is not None
        return
        state = await self._state.chunk_chat_group_members(self._id, 1_000_000)
        print(len(state.members))
        self._members: dict[ID64, MemberT] = {}
        member_cls: type[MemberT] = self.__class__.__orig_bases__[0].__args__[0]  # type: ignore
        users = await self._state._maybe_users(utils.make_id64(member.accountid) for member in state.members)

        for member, user in zip(state.members, users):
            self._members[user.id64] = member_cls(self._state, user, member)
        return self.members

    async def search(self, name: str):
        """Search for members in the chat group.

        Parameters
        ----------
        name
            The name of the member to search for.
        """
        assert self._id is not None
        msg: MsgProto[chat.SearchMembersResponse] = await self._state.ws.send_um_and_wait(
            "ChatRoom.SearchMembers",
            chat_group_id=self._id,
            search_text=name,
            max_results=10,
        )
        member_cls: type[MemberT] = self.__class__.__orig_bases__[0].__args__[0]  # type: ignore
        print(msg)
        return [
            member_cls(self._state, User(self._state, self._state.patch_user_from_ws({}, member.persona)), member)
            for member in msg.body.matching_members
        ]

    async def invite(self, user: User) -> None:
        """Invites a :class:`~steam.User` to the chat group.

        Parameters
        -----------
        user
            The user to invite to the chat group.
        """
        await self._state.invite_user_to_chat(user.id64, self._id)

    async def join(self, *, invite_code: str | None = None) -> None:
        """Joins the chat group.

        Parameters
        ----------
        invite_code
            The invite code to use to join the chat group.
        """
        await self._state.join_chat_group(self._id, invite_code)

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
