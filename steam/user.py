"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import weakref
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from functools import partial
from ipaddress import IPv4Address
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Literal, cast

from ._const import DOCS_BUILDING, MISSING, UNIX_EPOCH, URL, TaskGroup
from .abc import BaseUser, Messageable
from .app import PartialApp
from .enums import Language, PersonaState, PersonaStateFlag, Type
from .id import _ID64_TO_ID32, ID
from .profile import ClientUserProfile, OwnedProfileItems, ProfileInfo, ProfileItem
from .protobufs import friend_messages, player
from .protobufs.friends import CMsgClientPersonaStateFriend as UserProto
from .reaction import Emoticon, MessageReaction, Sticker
from .trade import Asset, Inventory, Item, TradeOffer
from .types.id import ID32, AppID, ContextID
from .utils import DateTime, cached_slot_property, parse_bb_code

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from typing_extensions import Self

    from .app import App
    from .channel import UserChannel
    from .friend import Friend
    from .media import Media
    from .message import UserMessage
    from .state import ConnectionState
    from .types import user

__all__ = (
    "User",
    "ClientUser",
    "AnonymousClientUser",
)


class _BaseUser(BaseUser):
    __slots__ = (
        "name",
        "app",
        "state",
        "flags",
        "last_seen_online",
        "last_logoff",
        "last_logon",
        "rich_presence",
        "game_server_ip",
        "game_server_port",
        "_state",
        "_avatar_sha",
    )

    def __init__(self, state: ConnectionState, proto: UserProto):
        super().__init__(state, proto.friendid)
        self._update(proto)

    def _update(self, proto: UserProto, /) -> None:
        self.name = proto.player_name
        """The user's username."""
        self._avatar_sha = proto.avatar_hash

        self.game_server_ip = IPv4Address(proto.game_server_ip) if proto.game_server_ip else None
        """The IP address of the game server the user is currently playing on."""
        self.game_server_port = proto.game_server_port or None
        """The port of the game server the user is currently playing on."""

        self.last_logoff = DateTime.from_timestamp(proto.last_logoff)
        """The last time the user logged off from steam."""
        self.last_logon = DateTime.from_timestamp(proto.last_logon)
        """The last time the user logged into steam."""
        self.last_seen_online = DateTime.from_timestamp(proto.last_seen_online)
        """The last time the user could be seen online."""
        self.rich_presence = (
            {message.key: message.value for message in proto.rich_presence} if proto.is_set("rich_presence") else None
        )
        """The rich presence of the user."""
        self.app = (
            PartialApp(self._state, name=proto.game_name, id=proto.game_played_app_id)
            if proto.game_played_app_id
            else None
        )
        """The app the user is playing. Is ``None`` if the user isn't in a app or one that is recognised by the API."""
        self.state = PersonaState.try_value(proto.persona_state)
        """The current persona state of the account (e.g. LookingToTrade)."""
        self.flags = PersonaStateFlag.try_value(proto.persona_state_flags)
        """The persona state flags of the account."""


class User(_BaseUser, Messageable["UserMessage"]):
    """Represents a Steam user's account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.
    """

    __slots__ = ("_cs_channel",)

    @staticmethod
    def _dict_to_proto(data: user.User) -> UserProto:
        return UserProto(
            player_name=data["personaname"],
            friendid=int(data["steamid"]),
            avatar_hash=bytes.fromhex(data["avatarhash"]) if "avatarhash" in data else b"\x00" * 20,
            persona_state=data.get("personastate", 0),
            game_played_app_id=int(data.get("gameid", 0)),
            persona_state_flags=data.get("personastateflags", 0),
            last_logoff=data.get("lastlogoff", 0),
            game_name=data.get("gameextrainfo", 0),
        )

    async def add(self) -> None:
        """Sends a friend invite to the user to your friends list."""
        await self._state.add_user(self.id64)

    async def remove(self) -> None:
        """Remove the user from your friends list."""
        await self._state.remove_user(self.id64)
        self._state.user._friends.pop(self.id, None)

    async def cancel_invite(self) -> None:
        """Cancels an invitation sent to the user. This effectively does the same thing as :meth:`remove`."""
        await self._state.remove_user(self.id64)

    async def block(self) -> None:
        """Blocks the user."""
        await self._state.block_user(self.id64)

    async def unblock(self) -> None:
        """Unblocks the user."""
        await self._state.unblock_user(self.id64)

    async def escrow(self, token: str | None = None) -> timedelta | None:
        """Check how long any received items would take to arrive. ``None`` if the user has no escrow or has a
        private inventory.

        Parameters
        ----------
        token
            The user's trade offer token, not required if you are friends with the user.
        """
        data = await self._state.http.get_user_escrow(self.id64, token)
        if (their_escrow := data.get("their_escrow")) is None:  # private
            return None
        seconds = their_escrow["escrow_end_duration_seconds"]
        return timedelta(seconds=seconds) if seconds else None

    async def send(
        self,
        content: Any = MISSING,
        /,
        *,
        trade: TradeOffer[Asset[User], Asset[ClientUser], Any] | None = None,
        media: Media | None = None,
    ) -> UserMessage[ClientUser] | None:
        """Send a message, trade or image to an :class:`User`.

        Parameters
        ----------
        content
            The message to send to the user.
        trade
            The trade offer to send to the user.

            Note
            ----
            This will have its :attr:`~steam.TradeOffer.id` attribute updated after being sent.

        media
            The media to send to the user.

        Raises
        ------
        :exc:`~steam.HTTPException`
            Sending the message failed.
        :exc:`~steam.Forbidden`
            You do not have permission to send the message.

        Returns
        -------
        The sent message only applicable if ``content`` is passed.
        """
        super_send = partial(
            Messageable["UserMessage[ClientUser]"].send, cast("Messageable[UserMessage[ClientUser]]", self)
        )  # done because calls to super() break in WrapsUser subclasses

        message = await super_send(content, media=media)
        if trade is not None:
            await self._send_trade(trade)

        return message

    @cached_slot_property("_cs_channel")
    def _channel(self) -> UserChannel:
        from .channel import UserChannel

        return UserChannel(self._state, self)

    async def history(
        self, *, limit: int | None = 100, before: datetime | None = None, after: datetime | None = None
    ) -> AsyncGenerator[UserMessage, None]:
        from .message import UserMessage

        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        after_timestamp = int(after.timestamp())
        before_timestamp = int(before.timestamp())
        yielded = 0

        last_message_timestamp = before_timestamp
        ordinal = 0

        while True:
            resp = await self._state.fetch_user_history(
                self.id64, start=after_timestamp, last=last_message_timestamp, start_ordinal=ordinal
            )

            message: friend_messages.GetRecentMessagesResponseFriendMessage | None = None

            for message in resp.messages:
                new_message = UserMessage._from_history(self._channel, message)
                new_message.created_at = DateTime.from_timestamp(message.timestamp)
                if not after < new_message.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return

                new_message.author = self if message.accountid == self.id else self._state.user
                emoticon_reactions = [
                    MessageReaction(
                        self._state,
                        new_message,
                        Emoticon(self._state, r.reaction),
                        None,
                        self if reactor == self.id else self._state.user,
                    )
                    for r in message.reactions
                    if r.reaction_type == Emoticon._TYPE
                    for reactor in r.reactors
                ]
                sticker_reactions = [
                    MessageReaction(
                        self._state,
                        new_message,
                        None,
                        Sticker(self._state, r.reaction),
                        self if reactor == self.id else self._state.user,
                    )
                    for r in message.reactions
                    if r.reaction_type == Sticker._TYPE
                    for reactor in r.reactors
                ]
                new_message.reactions = emoticon_reactions + sticker_reactions

                yield new_message
                yielded += 1

            if message is None:
                return

            last_message_timestamp = message.timestamp
            ordinal = message.ordinal

            if not resp.more_available:
                return

    @asynccontextmanager
    async def typing(self) -> AsyncGenerator[None, None]:
        """Send a typing indicator continuously to the channel while in the context manager.

        Note
        ----
        This only works in DMs.

        Usage:

        .. code:: python

            async with channel.typing():
                ...  # do your expensive operations
        """

        async def inner() -> None:
            while True:
                await self.trigger_typing()
                await asyncio.sleep(10)

        async with TaskGroup() as tg:
            t = tg.create_task(inner())
            yield
            t.cancel()

    async def trigger_typing(self) -> None:
        """Send a typing indicator to the channel once.

        Note
        ----
        This only works in DMs.
        """
        await self._state.send_user_typing(self.id64)


class ClientUser(_BaseUser):
    """Represents your account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.
    """

    # TODO more stuff to add https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/profile.js

    __slots__ = ("_friends", "_inventory_locks")

    def __init__(self, state: ConnectionState, proto: UserProto):
        super().__init__(state, proto)
        self._friends: dict[ID32, Friend] = {}
        self._inventory_locks = weakref.WeakValueDictionary[AppID, asyncio.Lock]()

    async def friends(self) -> Sequence[Friend]:
        """A list of the user's friends."""
        return list(self._friends.values())

    def get_friend(self, id: int, /) -> Friend | None:
        """Get a friend from the client user's friends list.

        Parameters
        ----------
        id
            The ID64 of the friend to get.
        """
        return self._friends.get(_ID64_TO_ID32(id))

    async def inventory(
        self, app: App, /, *, context_id: int | None = None, language: Language | None = None
    ) -> Inventory[Item[Self], Self]:
        try:
            lock = self._inventory_locks[app.id]
        except KeyError:
            lock = self._inventory_locks[app.id] = asyncio.Lock()

        if context_id is None:
            context_id = 6 if app.name == "Steam" and context_id is None else 2
        context_id = ContextID(context_id)
        async with lock:  # requires a per-app lock to avoid Result.DuplicateRequest
            resp = await self._state.fetch_user_inventory(
                self.id64, app.id, context_id, language
            )  # fast path for own account cause it works for this
            return Inventory(self._state, resp, self, app, context_id, language)

    async def setup_profile(self) -> None:
        """Set up your profile if possible."""
        params = {"welcomed": 1}
        await self._state.http.get(URL.COMMUNITY / "my/edit", params=params)

    async def clear_nicks(self) -> None:
        """Clears the client user's nickname/alias history."""
        await self._state.http.clear_nickname_history()

    async def profile_items(self, *, language: Language | None = None) -> OwnedProfileItems[Self]:
        """Fetch all the client user's profile items.

        Parameters
        ----------
        language
            The language to fetch the profile items in. If ``None`` the current language is used
        """
        items = await self._state.fetch_profile_items(language)
        return OwnedProfileItems(
            backgrounds=[
                ProfileItem(self._state, self, background, um=player.SetProfileBackgroundRequest)
                for background in items.profile_backgrounds
            ],
            mini_profile_backgrounds=[
                ProfileItem(self._state, self, mini_profile_background, um=player.SetMiniProfileBackgroundRequest)
                for mini_profile_background in items.mini_profile_backgrounds
            ],
            avatar_frames=[
                ProfileItem(self._state, self, avatar_frame, um=player.SetAvatarFrameRequest)
                for avatar_frame in items.avatar_frames
            ],
            animated_avatars=[
                ProfileItem(self._state, self, animated_avatar, um=player.SetAnimatedAvatarRequest)
                for animated_avatar in items.animated_avatars
            ],
            modifiers=[ProfileItem(self._state, self, modifier) for modifier in items.profile_modifiers],
        )

    async def profile(self, *, language: Language | None = None) -> ClientUserProfile:
        return ClientUserProfile(
            *await asyncio.gather(
                self.equipped_profile_items(language=language),
                self.profile_info(),
                self.profile_customisation_info(),
                self.profile_items(language=language),
            )
        )

    async def profile_info(self: ClientUser | Friend) -> ProfileInfo:
        """The friend's profile info."""
        info = await self._state.fetch_friend_profile_info(self.id64)
        # why this is friend only I'm not really sure considering it's available through the API
        return ProfileInfo(
            created_at=DateTime.from_timestamp(info.time_created),
            real_name=info.real_name or None,
            city_name=info.city_name or None,
            state_name=info.state_name or None,
            country_name=info.country_name or None,
            headline=info.headline or None,
            summary=parse_bb_code(info.summary),
        )

    async def edit(
        self,
        *,
        name: str | None = None,
        real_name: str | None = None,
        url: str | None = None,
        summary: str | None = None,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        avatar: Media | None = None,
        # TODO privacy params, use ums
    ) -> None:
        """Edit the client user's profile. Any values that aren't set will use their defaults.

        Parameters
        ----------
        name
            The new name you wish to go by.
        real_name
            The real name you wish to go by.
        url
            The custom url ending/path you wish to use.
        summary
            The summary/description you wish to use.
        country
            The country you want to be from.
        state
            The state you want to be from.
        city
            The city you want to be from.
        avatar
            The avatar you wish to use.

            Note
            ----
            This needs to be at least 184px x 184px.

        Raises
        -------
        :exc:`~steam.HTTPException`
            Editing your profile failed.
        """
        if any((name, real_name, url, summary, country, state, city)):
            await self._state.http.edit_profile_info(name, real_name, url, summary, country, state, city)
        if avatar is not None:
            await self._state.http.update_avatar(avatar, "player_avatar_image", sId=self.id64)
        # TODO privacy stuff


IndividualID = ID[Literal[Type.Individual]]


class WrapsUser(User if TYPE_CHECKING or DOCS_BUILDING else BaseUser, Messageable["UserMessage"]):
    """Internal class used for creating a User subclass optimised for memory. Composes the original user and forwards
    all of its attributes.

    Similar concept to discord.py's Member except more generalised for the larger number situations Steam throws at us.
    Slightly different however in that isinstance(SubclassOfWrapsUser(), User) should pass.

    Note
    ----
    This class does not forward ClientUsers attribute's so things like Clan().me.clear_nicks() will fail.

    If DOCS_BUILDING is True then this class behaves like a normal User because we need to be able to access the
    doc-strings reliably and memory usage isn't a concern.
    """

    __slots__ = ("_user", "_cs_channel")

    def __init__(self, state: ConnectionState, user: User | ClientUser):
        IndividualID.__init__(self, user.id64, type=Type.Individual)
        self._user = user

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        user_dict = User.__dict__.copy()
        user_dict.pop("__annotations__", None)
        for name, function in set(user_dict.items()) - set(object.__dict__.items()):
            if not name.startswith("__") and name not in User.__slots__:
                setattr(cls, name, function)

        if not DOCS_BUILDING:
            for name in _BaseUser.__slots__:
                setattr(cls, name, property(attrgetter(f"_user.{name}")))  # TODO time this with a compiled property
                # probably wont be different than the above

        User.register(cls)


class AnonymousClientUser(ID[Literal[Type.AnonUser]]):
    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, id64: int):
        super().__init__(id64, type=Type.AnonUser)
        self._state = state

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} universe={self.universe!r} instance={self.instance!r}>"
