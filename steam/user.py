"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import sys
import weakref
from collections.abc import Coroutine, Sequence
from datetime import timedelta
from ipaddress import IPv4Address
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from . import utils
from ._const import URL
from .abc import BaseUser, Messageable
from .app import PartialApp
from .enums import Language, PersonaState, PersonaStateFlag, Result, TradeOfferState, Type
from .errors import ClientException, ConfirmationError, HTTPException
from .id import ID
from .profile import ClientUserProfile, OwnedProfileItems, ProfileInfo, ProfileItem
from .protobufs import player
from .trade import TradeOffer
from .types.id import ID64, AppID, Intable
from .utils import DateTime

if TYPE_CHECKING:
    from .app import App
    from .friend import Friend
    from .image import Image
    from .message import UserMessage
    from .protobufs.friends import CMsgClientPersonaStateFriend as UserProto
    from .state import ConnectionState
    from .trade import Inventory

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
        "trade_url",
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
        super().__init__(proto.friendid)
        self._state = state
        self._update(proto)

    def _update(self, proto: UserProto) -> None:
        self.name = proto.player_name
        self._avatar_sha = proto.avatar_hash
        self.trade_url = URL.COMMUNITY / f"tradeoffer/new/?partner={self.id}"

        self.game_server_ip = IPv4Address(proto.game_server_ip) if proto.game_server_ip else None
        self.game_server_port = proto.game_server_port or None

        self.last_logoff = DateTime.from_timestamp(proto.last_logoff)
        self.last_logon = DateTime.from_timestamp(proto.last_logon)
        self.last_seen_online = DateTime.from_timestamp(proto.last_seen_online)
        self.rich_presence = {message.key: message.value for message in proto.rich_presence}
        self.app = (
            PartialApp(self._state, name=proto.game_name, id=proto.game_played_app_id)
            if proto.game_played_app_id
            else None
        )
        self.state = PersonaState.try_value(proto.persona_state) or self.state
        self.flags = PersonaStateFlag.try_value(proto.persona_state_flags) or self.flags


class User(_BaseUser, Messageable["UserMessage"]):
    """Represents a Steam user's account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name
        The user's username.
    state
        The current persona state of the account (e.g. LookingToTrade).
    app
        The app the user is playing. Is ``None`` if the user isn't in a app or one that is recognised by the
        api.
    avatar_url
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name
        The user's real name defined by them. Could be ``None``.
    primary_clan
        The user's primary clan.
    created_at
        The time at which the user's account was created. Could be ``None``.
    last_logon
        The last time the user logged into steam. This is only ``None`` if user hasn't been updated from the websocket.
    last_logoff
        The last time the user logged off from steam. Could be ``None`` (e.g. if they are currently online).
    last_seen_online
        The last time the user could be seen online. This is only ``None`` if user hasn't been updated from the
        websocket.
    country
        The country code of the account. Could be ``None``.
    flags
        The persona state flags of the account.
    """

    __slots__ = ()

    async def add(self) -> None:
        """Sends a friend invite to the user to your friends list."""
        await self._state.add_user(self.id64)

    async def remove(self) -> None:
        """Remove the user from your friends list."""
        await self._state.remove_user(self.id64)
        self._state.user._friends.pop(self.id64, None)

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
        resp = await self._state.http.get_user_escrow(self.id64, token)
        their_escrow = resp["response"].get("their_escrow")
        if their_escrow is None:  # private
            return None
        seconds = their_escrow["escrow_end_duration_seconds"]
        return timedelta(seconds=seconds) if seconds else None

    def _message_func(self, content: str) -> Coroutine[Any, Any, UserMessage]:
        return self._state.send_user_message(self.id64, content)

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_user_image(self.id64, image)

    async def send(
        self,
        content: Any = None,
        *,
        trade: TradeOffer | None = None,
        image: Image | None = None,
    ) -> UserMessage | None:
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

        image
            The image to send to the user.

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

        message = await super().send(content, image)
        if trade is not None:
            to_send = [item.to_dict() for item in trade.items_to_send]
            to_receive = [item.to_dict() for item in trade.items_to_receive]
            try:
                resp = await self._state.http.send_trade_offer(
                    self, to_send, to_receive, trade.token, trade.message or ""
                )
            except HTTPException as e:
                if e.code == Result.Revoked and (
                    any(item.owner != self for item in trade.items_to_receive)
                    or any(item.owner != self._state.user for item in trade.items_to_send)
                ):
                    if sys.version_info >= (3, 11):
                        e.add_note(
                            "You've probably sent an item isn't either in your inventory or the user's inventory"
                        )
                    else:
                        raise ValueError(
                            "You've probably sent an item isn't either in your inventory or the user's inventory"
                        ) from e
                raise e
            trade._has_been_sent = True
            needs_confirmation = resp.get("needs_mobile_confirmation", False)
            trade._update_from_send(self._state, resp, self, active=not needs_confirmation)
            if needs_confirmation:
                for tries in range(5):
                    try:
                        await trade.confirm()
                    except ConfirmationError:
                        break
                    except ClientException:
                        await asyncio.sleep(tries * 2)
                trade.state = TradeOfferState.Active

            # make sure the trade is updated before this function returns
            self._state._trades[trade.id] = trade
            self._state._trades_to_watch.add(trade.id)
            await self._state.wait_for_trade(trade.id)
            self._state.dispatch("trade_send", trade)

        return message

    def is_friend(self) -> bool:
        """Whether the user is in the :class:`ClientUser`'s friends."""
        return self.id64 in self._state.user._friends


class ClientUser(_BaseUser):
    """Represents your account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name
        The user's username.
    state
        The current persona state of the account (e.g. LookingToTrade).
    app
        The app the user is currently playing. Is ``None`` if the user isn't in an app or one that is recognised by the
        api.
    last_logon
        The last time the user logged into steam. This is only ``None`` if user hasn't been updated from the websocket.
    last_logoff
        The last time the user logged off from steam. Could be ``None`` (e.g. if they are currently online).
    last_seen_online
        The last time the user could be seen online. This is only ``None`` if user hasn't been updated from the
        websocket.
    flags
        The persona state flags of the account.
    """

    # TODO more stuff to add https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/profile.js

    __slots__ = ("_friends", "_inventory_locks")

    def __init__(self, state: ConnectionState, proto: UserProto):
        super().__init__(state, proto)
        self._friends: dict[ID64, Friend] = {}
        self._inventory_locks = weakref.WeakValueDictionary[AppID, asyncio.Lock]()

    async def friends(self) -> Sequence[Friend]:
        """A list of the user's friends."""
        return list(self._friends.values())

    def get_friend(self, id: Intable) -> Friend | None:
        """Get a friend from the client user's friends list."""
        id64 = utils.parse_id64(id, type=Type.Individual)
        return self._friends.get(id64)

    async def inventory(self, app: App, *, language: Language | None = None) -> Inventory:
        try:
            lock = self._inventory_locks[app.id]
        except KeyError:
            lock = self._inventory_locks[app.id] = asyncio.Lock()

        async with lock:  # requires a per-app lock to avoid Result.DuplicateRequest
            return await super().inventory(app, language=language)

    async def setup_profile(self) -> None:
        """Set up your profile if possible."""
        params = {"welcomed": 1}
        await self._state.http.get(URL.COMMUNITY / "my/edit", params=params)

    async def clear_nicks(self) -> None:
        """Clears the client user's nickname/alias history."""
        await self._state.http.clear_nickname_history()

    async def profile_items(self, *, language: Language | None = None) -> OwnedProfileItems:
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

    async def profile_info(self) -> ProfileInfo:
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
            summary=info.summary,
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
        avatar: Image | None = None,
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
            await self._state.http.update_avatar(avatar)
        # TODO privacy stuff


class WrapsUser(User if TYPE_CHECKING else BaseUser, Messageable["UserMessage"]):
    """Internal class used for creating a User subclass optimised for memory. Composes the original user and forwards
    all of its attributes.

    Similar concept to discord.py's Member except more generalised for the larger number situations Steam throws at us.
    Slightly different however in that isinstance(SubclassOfWrapsUser(), User) should pass.

    Note
    ----
    This class does not forward ClientUsers attribute's so things like Clan().me.clear_nicks() will fail.
    """

    __slots__ = ("_user",)

    def __init__(self, state: ConnectionState, user: User):
        ID.__init__(self, user.id64, type=Type.Individual)
        self._user = user

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        for name, function in set(User.__dict__.items()) - set(object.__dict__.items()):
            if not name.startswith("__"):
                setattr(cls, name, function)
        for name in _BaseUser.__slots__:
            setattr(cls, name, property(attrgetter(f"_user.{name}")))  # TODO time this with a compiled property
            # probably wont be different than the above

        User.register(cls)


class AnonymousClientUser(ID):
    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, id64: int):
        super().__init__(id64, type=Type.AnonUser)
        self._state = state

    def __repr__(self) -> str:
        return f"<AnonymousClientUser id={self.id} universe={self.universe!r}, instance={self.instance!r}>"
