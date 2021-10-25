"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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

This contains a copy of
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
"""

from __future__ import annotations

import abc
import asyncio
import re
from collections.abc import Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

import attr
from typing_extensions import Final, Protocol, TypedDict, runtime_checkable

from .badge import FavouriteBadge, UserBadges
from .comment import Comment
from .enums import *
from .errors import WSException
from .game import Game, StatefulGame, UserGame, WishlistGame
from .iterators import AsyncIterator, CommentsIterator
from .models import URL, Ban
from .profile import *
from .trade import Inventory
from .utils import (
    _INVITE_HEX,
    _INVITE_MAPPING,
    InstanceType,
    Intable,
    TypeType,
    UniverseType,
    cached_slot_property,
    id64_from_url,
    make_id64,
)

if TYPE_CHECKING:
    from _typeshed import Self
    from aiohttp import ClientSession

    from .clan import Clan
    from .group import Group
    from .http import StrOrURL
    from .image import Image
    from .message import Authors
    from .protobufs.chat import Mentions
    from .state import ConnectionState
    from .user import User

__all__ = (
    "SteamID",
    "Message",
    "Channel",
)

C = TypeVar("C", bound="Commentable")
M_co = TypeVar("M_co", bound="Message", covariant=True)


class UserDict(TypedDict):
    steamid: str
    personaname: str
    primaryclanid: str
    profileurl: str
    realname: str
    # enums
    communityvisibilitystate: int
    profilestate: int
    commentpermission: int
    personastate: int
    personastateflags: int
    # avatar
    avatar: str
    avatarmedium: str
    avatarfull: str
    avatarhash: str
    # country stuff
    loccountrycode: str
    locstatecode: int
    loccityid: int
    # game stuff
    gameid: str  # game app id
    gameextrainfo: str  # game name
    # unix timestamps
    timecreated: int
    lastlogoff: int
    # we pass these ourselves
    last_logon: int
    last_seen_online: int


class SteamID(metaclass=abc.ABCMeta):
    """Convert a Steam ID between its various representations.

    Note
    ----
    See :func:`steam.utils.make_id64` for the full parameter list.
    """

    __slots__ = ("__BASE",)

    def __init__(
        self,
        id: Intable = 0,
        type: TypeType | None = None,
        universe: UniverseType | None = None,
        instance: InstanceType | None = None,
    ):
        self.__BASE: Final = make_id64(id, type, universe, instance)

    def __int__(self) -> int:
        return self.__BASE

    def __eq__(self, other: Any) -> bool:
        try:
            return self.__BASE == int(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __str__(self) -> str:
        return str(self.__BASE)

    def __hash__(self) -> int:
        return hash(self.__BASE)

    def __repr__(self) -> str:
        return f"SteamID(id={self.id}, type={self.type}, universe={self.universe}, instance={self.instance})"

    @property
    def instance(self) -> int:
        """The instance of the SteamID."""
        return (self.__BASE >> 32) & 0xFFFFF

    @property
    def type(self) -> Type:
        """The Steam type of the SteamID."""
        return Type((self.__BASE >> 52) & 0xF)

    @property
    def universe(self) -> Universe:
        """The Steam universe of the SteamID."""
        return Universe((self.__BASE >> 56) & 0xFF)

    @property
    def id64(self) -> int:
        """The SteamID's 64 bit ID."""
        return self.__BASE

    @property
    def id(self) -> int:
        """The SteamID's 32 bit ID."""
        return self.__BASE & 0xFFFFFFFF

    @property
    def id2(self) -> str:
        """The SteamID's ID 2.

        e.g ``STEAM_1:0:1234``.
        """
        return f"STEAM_{self.universe.value}:{self.id % 2}:{self.id >> 1}"

    @property
    def id2_zero(self) -> str:
        """The SteamID's ID 2 accounted for bugged GoldSrc and Orange Box games.

        Note
        ----
        In these games the accounts :attr:`universe`, ``1`` for :class:`.Type.Public`, should be the ``X`` component of
        ``STEAM_X:0:1234`` however, this was bugged and the value of ``X`` was ``0``.

        e.g ``STEAM_0:0:1234``.
        """
        return self.id2.replace("_1", "_0")

    @property
    def id3(self) -> str:
        """The SteamID's ID 3.

        e.g ``[U:1:1234]``.
        """
        type_char = TypeChar(self.type).name
        instance = None

        if self.type in (Type.AnonGameServer, Type.Multiseat):
            instance = self.instance
        elif self.type == Type.Individual:
            if self.instance != 1:
                instance = self.instance
        elif self.type == Type.Chat:
            if self.instance & InstanceFlag.Clan:
                type_char = "c"
            elif self.instance & InstanceFlag.Lobby:
                type_char = "L"
            else:
                type_char = "T"

        parts = [type_char, str(self.universe.value), str(self.id)]

        if instance is not None:
            parts.append(str(instance))

        return f"[{':'.join(parts)}]"

    @property
    def invite_code(self) -> str | None:
        """The SteamID's invite code in the s.team invite code format.

        e.g. ``cv-dgb``.
        """
        if self.type == Type.Individual and self.is_valid():
            invite_code = re.sub(f"[{_INVITE_HEX}]", lambda x: _INVITE_MAPPING[x.group()], f"{self.id:x}")
            split_idx = len(invite_code) // 2
            return invite_code if split_idx == 0 else f"{invite_code[:split_idx]}-{invite_code[split_idx:]}"

    @property
    def invite_url(self) -> str | None:
        """The SteamID's full invite code URL.

        e.g ``https://s.team/p/cv-dgb``.
        """
        code = self.invite_code
        return f"https://s.team/p/{code}" if code else None

    @property
    def community_url(self) -> str | None:
        """The SteamID's community url.

        e.g https://steamcommunity.com/profiles/123456789.
        """
        suffix = {
            Type.Individual: "profiles",
            Type.Clan: "gid",
        }
        try:
            return f"https://steamcommunity.com/{suffix[self.type]}/{self.id64}"
        except KeyError:
            return None

    def is_valid(self) -> bool:
        """Whether or not the SteamID is valid."""
        if self.type == Type.Invalid or self.type >= Type.Max:
            return False

        if self.universe == Universe.Invalid or self.universe >= Universe.Max:
            return False

        if self.type == Type.Individual and (self.id == 0 or self.instance > 4):
            return False

        if self.type == Type.Clan and (self.id == 0 or self.instance != 0):
            return False

        if self.type == Type.GameServer and self.id == 0:
            return False

        if self.type == Type.AnonGameServer and self.id == 0 and self.instance == 0:
            return False

        return True

    @staticmethod
    async def from_url(url: StrOrURL, session: ClientSession | None = None) -> SteamID | None:
        """A helper function creates a SteamID instance from a Steam community url.

        Note
        ----
        See :func:`id64_from_url` for the full parameter list.
        """
        id64 = await id64_from_url(url, session)
        return SteamID(id64) if id64 else None


class Commentable(Protocol):
    """A mixin that implements commenting functionality"""

    __slots__ = ()
    _state: ConnectionState

    @property
    @abc.abstractmethod
    def _commentable_kwargs(self) -> dict[str, Any]:
        raise NotImplementedError

    async def fetch_comment(self: Self, id: int) -> Comment[Self]:
        """Fetch a comment by its ID.

        Parameters
        ----------
        id
            The ID of the comment to fetch.
        """
        comment = await self._state.fetch_comment(self, id)
        return Comment(
            self._state,
            id=comment.id,
            content=comment.content,
            created_at=datetime.utcfromtimestamp(comment.timestamp),
            author=await self._state._maybe_user(comment.author_id64),
            owner=self,
        )

    async def comment(self: Self, content: str, *, subscribe: bool = True) -> Comment[Self]:
        """Post a comment to a comments section.

        Parameters
        ----------
        content
            The message to add to the comment section.
        subscribe
            Whether to subscribe to notifications on any future activity in this comment's thread.

        Returns
        -------
        The created comment.
        """
        return await self._state.post_comment(self, content, subscribe)

    def comments(
        self: Self,
        oldest_first: bool = False,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> CommentsIterator[Self]:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a comment section's :class:`~steam.Comment` objects.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for comment in commentable.comments(limit=10):
                print("Author:", comment.author, "Said:", comment.content)

        Flattening into a list:

        .. code-block:: python3

            comments = await commentable.comments(limit=50).flatten()
            # comments is now a list of Comment

        All parameters are optional.

        Parameters
        ----------
        oldest_first
            Whether or not to request comments with the oldest comments first or last. Defaults to ``False``.
        limit
            The maximum number of comments to search through.
            Default is ``None`` which will fetch the clan's entire comments section.
        before
            A time to search for comments before.
        after
            A time to search for comments after.

        Yields
        ---------
        :class:`~steam.Comment`
        """
        return CommentsIterator(
            oldest_first=oldest_first, owner=self, state=self._state, limit=limit, before=before, after=after
        )


class BaseUser(SteamID, Commentable):
    """An ABC that details the common operations on a Steam user.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClientUser`

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
    game
        The Game instance attached to the user. Is ``None`` if the user isn't in a game or one that is recognised by the
        api.
    primary_clan
        The primary clan the User displays on their profile.

        Note
        ----
        This can be lazily awaited to get more attributes of the clan.

    avatar_url
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name
        The user's real name defined by them. Could be ``None``.
    created_at
        The time at which the user's account was created. Could be ``None``.
    last_logoff
        The last time the user logged into steam. Could be None (e.g. if they are currently online).
    country
        The country code of the account. Could be ``None``.
    flags
        The persona state flags of the account.
    """

    __slots__ = (
        "name",
        "game",
        "state",
        "flags",
        "country",
        "primary_clan",
        "trade_url",
        "real_name",
        "avatar_url",
        "last_seen_online",
        "created_at",
        "last_logoff",
        "last_logon",
        "privacy_state",
        "community_url",
        "_is_commentable",
        "_setup_profile",
        "_level",
        "_state",
    )

    def __init__(self, state: ConnectionState, data: UserDict):
        super().__init__(data["steamid"])
        self._state = state
        self.name: str
        self.real_name: str | None = None
        self.community_url: str | None = None
        self.avatar_url: str | None = None  # TODO make this a property and add avatar hash
        self.primary_clan: Clan | None = None
        self.country: str | None = None
        self.created_at: datetime | None = None
        self.last_logoff: datetime | None = None
        self.last_logon: datetime | None = None
        self.last_seen_online: datetime | None = None
        self.game: StatefulGame | None = None
        self.state: PersonaState | None = None
        self.flags: PersonaStateFlag | None = None
        self.privacy_state: CommunityVisibilityState | None = None
        self._update(data)

    def _update(self, data: UserDict) -> None:
        self.name = data["personaname"]
        self.real_name = data.get("realname") or self.real_name
        self.community_url = data.get("profileurl") or super().community_url
        self.avatar_url = data.get("avatarfull") or self.avatar_url
        self.trade_url = URL.COMMUNITY / f"tradeoffer/new/?partner={self.id}"
        from .clan import Clan  # circular import

        self.primary_clan = (
            Clan(self._state, data["primaryclanid"]) if "primaryclanid" in data else self.primary_clan  # type: ignore
        )
        self.country = data.get("loccountrycode") or self.country
        self.created_at = datetime.utcfromtimestamp(data["timecreated"]) if "timecreated" in data else self.created_at
        self.last_logoff = datetime.utcfromtimestamp(data["lastlogoff"]) if "lastlogoff" in data else self.last_logoff
        self.last_logon = datetime.utcfromtimestamp(data["last_logon"]) if "last_logon" in data else self.last_logon
        self.last_seen_online = (
            datetime.utcfromtimestamp(data["last_seen_online"]) if "last_seen_online" in data else self.last_seen_online
        )
        self.game = (
            StatefulGame(self._state, name=data["gameextrainfo"], id=data["gameid"]) if "gameid" in data else self.game
        )
        self.state = PersonaState.try_value(data.get("personastate", 0)) or self.state
        self.flags = PersonaStateFlag.try_value(data.get("personastateflags", 0)) or self.flags
        self.privacy_state = CommunityVisibilityState.try_value(data.get("communityvisibilitystate", 0))
        self._is_commentable = bool(data.get("commentpermission"))
        self._setup_profile = bool(data.get("profilestate"))

    def __repr__(self) -> str:
        attrs = ("name", "state", "id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    def __del__(self):
        self._state._users.pop(self.id64, None)

    @property
    def _commentable_kwargs(self) -> dict[str, Any]:
        return {
            "id64": self.id64,
            "thread_type": 10,
        }

    @property
    def mention(self) -> str:
        """The string used to mention the user in chat."""
        return f"[mention={self.id}]@{self.name}[/mention]"

    async def inventory(self, game: Game) -> Inventory:
        """Fetch a user's :class:`~steam.Inventory` for trading.

        Parameters
        -----------
        game
            The game to fetch the inventory for.

        Raises
        ------
        :exc:`~steam.Forbidden`
            The user's inventory is private.
        """
        resp = await self._state.http.get_user_inventory(self.id64, game.id, game.context_id)
        return Inventory(state=self._state, data=resp, owner=self, game=game)

    async def friends(self) -> list[User]:
        """Fetch the list of the users friends."""
        friends = await self._state.http.get_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def games(self) -> list[UserGame]:
        r"""Fetches the :class:`~steam.Game`\s the user owns."""
        data = await self._state.http.get_user_games(self.id64)
        games = data["response"].get("games", [])
        return [UserGame(self._state, game) for game in games]

    async def clans(self) -> list[Clan]:
        r"""Fetches a list of :class:`~steam.Clan`\s the user is in."""
        clans = []

        async def getter(gid: int) -> None:
            try:
                clan = await self._state.client.fetch_clan(gid)
            except WSException as exc:
                if exc.code == Result.RateLimitExceeded:
                    await asyncio.sleep(20)
                    return await getter(gid)
                raise
            else:
                clans.append(clan)

        resp = await self._state.http.get_user_clans(self.id64)
        for clan in resp["response"]["groups"]:
            await getter(int(clan["gid"]))
        return clans

    async def bans(self) -> Ban:
        r"""Fetches the user's :class:`.Ban`\s."""
        resp = await self._state.http.get_user_bans(self.id64)
        resp = resp["players"][0]
        resp["EconomyBan"] = resp["EconomyBan"] != "none"
        return Ban(data=resp)

    async def badges(self) -> UserBadges:
        r"""Fetches the user's :class:`.UserBadges`\s."""
        resp = await self._state.http.get_user_badges(self.id64)
        return UserBadges(self._state, data=resp["response"])

    async def level(self) -> int:
        """Fetches the user's level if your account is premium, otherwise it's cached."""
        if self._state.http.api_key is not None:
            resp = await self._state.http.get_user_level(self.id64)
            return resp["response"]["player_level"]
        return self._level

    async def wishlist(self) -> list[WishlistGame]:
        r"""Get the :class:`.WishlistGame`\s the user has on their wishlist."""
        data = await self._state.http.get_wishlist(self.id64)
        return [WishlistGame(self._state, id=id, data=game_info) for id, game_info in data.items()]

    async def favourite_badge(self) -> FavouriteBadge | None:
        """The user's favourite badge"""
        badge = await self._state.fetch_user_favourite_badge(self.id64)
        if not badge.has_favorite_badge:
            return

        return FavouriteBadge(
            id=UserBadge.try_value(badge.badgeid),
            item_id=badge.communityitemid,
            type=badge.item_type,
            border_colour=badge.border_color,
            game=StatefulGame(self._state, id=badge.appid) if badge.appid else None,
            level=badge.level,
        )

    async def equipped_profile_items(self) -> EquippedProfileItems:
        """The user's equipped profile items."""
        items = await self._state.fetch_user_equipped_profile_items(self.id64)
        return EquippedProfileItems(
            background=ProfileItem(self._state, items.profile_background) if items.profile_background else None,
            mini_profile_background=ProfileItem(self._state, items.mini_profile_background)
            if items.mini_profile_background
            else None,
            avatar_frame=ProfileItem(self._state, items.avatar_frame) if items.avatar_frame else None,
            animated_avatar=ProfileItem(self._state, items.animated_avatar) if items.animated_avatar else None,
            modifier=ProfileItem(self._state, items.profile_modifier) if items.profile_modifier else None,
        )

    async def profile_info(self) -> ProfileInfo:
        """The user's profile info."""
        info = await self._state.fetch_user_profile_info(self.id64)
        return ProfileInfo(
            created_at=datetime.utcfromtimestamp(info.time_created),
            real_name=info.real_name or None,
            city_name=info.city_name or None,
            state_name=info.state_name or None,
            country_name=info.country_name or None,
            headline=info.headline or None,
            summary=info.summary,
        )

    async def profile(self) -> Profile:
        """Fetch a user's entire profile information.

        Note
        ----
        This calls all the ``profile_x`` functions to return a Profile object which has all the info set.
        """

        coros = [
            self.equipped_profile_items(),
            self.profile_info(),
        ]

        if hasattr(self, "profile_items"):
            coros.append(self.profile_items())

        profiles: tuple[EquippedProfileItems, ProfileInfo] | tuple[
            EquippedProfileItems, ProfileInfo, OwnedProfileItems
        ] = await asyncio.gather(*coros)

        return Profile(*profiles)

    def is_commentable(self) -> bool:
        """Specifies if the user's account is able to be commented on."""
        return self._is_commentable

    def is_private(self) -> bool:
        """Specifies if the user has a private profile."""
        return self.privacy_state == CommunityVisibilityState.Private

    def has_setup_profile(self) -> bool:
        """Specifies if the user has a setup their profile."""
        return self._setup_profile

    async def is_banned(self) -> bool:
        """Specifies if the user is banned from any part of Steam.

        This is equivalent to:

        .. code-block:: python3

            bans = await user.bans()
            bans.is_banned()
        """
        bans = await self.bans()
        return bans.is_banned()

    @classmethod
    def _patch_without_api(cls) -> None:
        import functools

        def __init__(self, state: ConnectionState, data: dict[str, Any]) -> None:
            super().__init__(data["steamid"])
            self._state = state
            self.name = data["persona_name"]
            self.avatar_url = data.get("avatar_url") or self.avatar_url

            self.real_name = NotImplemented
            self.trade_url = URL.COMMUNITY / f"tradeoffer/new?partner={self.id}"
            self.primary_clan = NotImplemented
            self.country = NotImplemented
            self.created_at = NotImplemented
            self.last_logoff = NotImplemented
            self.last_logon = NotImplemented
            self.last_seen_online = NotImplemented
            self.game = NotImplemented
            self.state = NotImplemented
            self.flags = NotImplemented
            self.privacy_state = NotImplemented
            self._is_commentable = NotImplemented
            self._setup_profile = NotImplemented
            self._level = data["level"]

        def __repr__(self) -> str:
            attrs = ("name", "id", "type", "universe", "instance")
            resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
            return f"<{self.__class__.__name__} {' '.join(resolved)}>"

        setattr(cls, "__init__", __init__)
        setattr(cls, "__repr__", __repr__)

        def not_implemented(function: str) -> None:
            @functools.wraps(getattr(cls, function))
            async def wrapped(*_, **__) -> None:
                raise NotImplementedError(
                    f"Accounts without an API key cannot use User.{function}, this is a Steam limitation not a library "
                    f"limitation, sorry."
                )

            setattr(cls, function, wrapped)

        not_implemented("friends")
        not_implemented("badges")
        not_implemented("is_commentable")
        not_implemented("has_setup_profile")
        not_implemented("is_private")
        not_implemented("is_banned")


@runtime_checkable
class Messageable(Protocol[M_co]):
    """An ABC that details the common operations on a Steam message.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClanChannel`
        - :class:`~steam.GroupChannel`
        - :class:`~steam.DMChannel`
    """

    __slots__ = ()

    @abc.abstractmethod
    def _message_func(self, content: str) -> Coroutine[Any, Any, M_co]:
        raise NotImplementedError

    @abc.abstractmethod
    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        raise NotImplementedError

    async def send(self, content: Any = None, image: Image | None = None) -> M_co | None:
        """Send a message to a certain destination.

        Parameters
        ----------
        content
            The content of the message to send.
        image
            The image to send to the user.

        Note
        ----
        Anything as passed to ``content`` is implicitly cast to a :class:`str`.

        Raises
        ------
        :exc:`~steam.HTTPException`
            Sending the message failed.
        :exc:`~steam.Forbidden`
            You do not have permission to send the message.

        Returns
        -------
        The sent message, only applicable if ``content`` is passed.
        """
        message = None
        if content is not None:
            message = await self._message_func(str(content))
        if image is not None:
            await self._image_func(image)

        return message


@attr.dataclass(slots=True)
class Channel(Messageable[M_co]):
    _state: ConnectionState
    clan: Clan | None = None
    group: Group | None = None

    @abc.abstractmethod
    def history(
        self,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncIterator[M_co]:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a channel's :class:`steam.Message`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for message in channel.history(limit=10):
                print("Author:", message.author, "Said:", message.content)

        Flattening into a list:

        .. code-block:: python3

            messages = await channel.history(limit=50).flatten()
            # messages is now a list of Message

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of messages to search through. Setting this to ``None`` will fetch all of the channel's
            messages, but this will be a very slow operation.
        before
            A time to search for messages before.
        after
            A time to search for messages after.

        Yields
        ------
        :class:`~steam.Message`
        """
        raise NotImplementedError


def _clean_up_content(content: str) -> str:  # steam does weird stuff with content
    return content.replace(r"\[", "[").replace("\\\\", "\\")


STEAM_EPOCH = datetime(2005, 1, 1)


class Message:
    """Represents a message from a :class:`~steam.User`. This is a base class from which all messages inherit.

    The following classes implement this:

        - :class:`~steam.UserMessage`
        - :class:`~steam.GroupMessage`
        - :class:`~steam.ClanMessage`

    Attributes
    ----------
    channel
        The channel the message was sent in.
    content
        The message's content.

        Note
        ----
        This is **not** what you will see in the steam client see :attr:`clean_content` for that.

    clean_content
        The message's clean content without bbcode.
    author
        The message's author.
    created_at
        The time the message was sent at.
    group
        The group the message was sent in. Will be ``None`` if the message wasn't sent in a :class:`~steam.Group`.
    clan
        The clan the message was sent in. Will be ``None`` if the message wasn't sent in a :class:`~steam.Clan`.
    """

    __slots__ = (
        "author",
        "content",
        "channel",
        "clean_content",
        "created_at",
        "ordinal",
        "group",
        "clan",
        "mentions",
        "_id_cs",
        "_state",
    )
    author: Authors
    created_at: datetime

    def __init__(self, channel: Channel[Message], proto: Any):
        self._state: ConnectionState = channel._state
        self.channel = channel
        self.group: Group | None = channel.group
        self.clan: Clan | None = channel.clan
        self.content: str = _clean_up_content(proto.message)
        self.ordinal: int = proto.ordinal
        self.clean_content: str = getattr(proto, "message_no_bbcode", None) or self.content
        self.mentions: Mentions | None = getattr(proto, "mentions", None)
        # self.reactions: list["Emoticon"] = []

    def __repr__(self) -> str:
        attrs = ("author", "id", "channel")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    @cached_slot_property
    def id(self) -> int:
        """A unique identifier for every message sent in a channel."""
        # a u64 "snowflake-esk" id measuring of the number of seconds passed since Steam's EPOCH and then the
        # "sequence"/ordinal of the message.
        return int(
            f"{int((self.created_at - STEAM_EPOCH).total_seconds()):032b}{self.ordinal:032b}",
            base=2,
        )
