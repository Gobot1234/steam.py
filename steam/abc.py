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
import inspect
import re
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union, overload

import attr
from typing_extensions import Final, Protocol, TypeAlias, TypedDict, runtime_checkable

from .badge import FavouriteBadge, UserBadges
from .comment import Comment
from .enums import (
    CommunityVisibilityState,
    InstanceFlag,
    PersonaState,
    PersonaStateFlag,
    Result,
    Type,
    TypeChar,
    Universe,
)
from .errors import WSException
from .game import Game, UserGame, WishlistGame
from .iterators import AsyncIterator, CommentsIterator
from .models import URL, Ban
from .trade import Inventory
from .utils import _INVITE_HEX, _INVITE_MAPPING, InstanceType, Intable, TypeType, UniverseType, id64_from_url, make_id64

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from .clan import Clan
    from .group import Group
    from .http import StrOrURL
    from .image import Image
    from .protobufs.steammessages_chat import CChatMentions
    from .state import ConnectionState
    from .user import User

__all__ = (
    "SteamID",
    "Message",
    "Channel",
)

C = TypeVar("C", bound="Commentable")
M = TypeVar("M", bound="Message")


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

    Parameters
    ----------
    id: Union[:class:`int`, :class:`str`]
        The ID of the Steam ID, can be an :attr:`id64`, :attr:`id`, :attr:`id2` or an :attr:`id3`.
    type: Union[:class:`.Type`, :class:`int`, :class:`str`]
        The Type for the Steam ID.
    universe: Union[:class:`.Universe`, :class:`int`, :class:`str`]
        The Universe for the Steam ID.
    instance: :class:`int`
        The instance for the Steam ID.
    """

    __slots__ = ("__BASE",)

    @overload
    def __init__(self):
        ...

    @overload
    def __init__(
        self,
        id: Intable = 0,
        type: Optional[TypeType] = None,
        universe: Optional[UniverseType] = None,
        instance: Optional[InstanceType] = None,
    ):
        ...

    def __init__(
        self,
        id: Intable = 0,
        type: Optional[TypeType] = None,
        universe: Optional[UniverseType] = None,
        instance: Optional[InstanceType] = None,
    ):
        self.__BASE: Final[int] = make_id64(id, type, universe, instance)

    def __int__(self) -> int:
        return self.__BASE

    def __eq__(self, other: Any) -> bool:
        try:
            return int(self) == int(other)
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
        """:class:`int`: The instance of the SteamID."""
        return (int(self) >> 32) & 0xFFFFF

    @property
    def type(self) -> Type:
        """:class:`~steam.Type`: The Steam type of the SteamID."""
        return Type((int(self) >> 52) & 0xF)

    @property
    def universe(self) -> Universe:
        """:class:`~steam.Universe`: The Steam universe of the SteamID."""
        return Universe((int(self) >> 56) & 0xFF)

    @property
    def id64(self) -> int:
        """:class:`int`: The SteamID's 64 bit ID."""
        return self.__BASE

    @property
    def id(self) -> int:
        """:class:`int`: The SteamID's 32 bit ID."""
        return int(self) & 0xFFFFFFFF

    @property
    def id2(self) -> str:
        """:class:`str`: The SteamID's ID 2.

        e.g ``STEAM_1:0:1234``.
        """
        return f"STEAM_{int(self.universe)}:{self.id % 2}:{self.id >> 1}"

    @property
    def id2_zero(self) -> str:
        """:class:`str`: The SteamID's ID 2 accounted for bugged GoldSrc and Orange Box games.

        Note
        ----
        In these games the accounts :attr:`universe`, ``1`` for :class:`.Type.Public`, should be the ``X`` component of
        ``STEAM_X:0:1234`` however, this was bugged and the value of ``X`` was ``0``.

        e.g ``STEAM_0:0:1234``.
        """
        return self.id2.replace("_1", "_0")

    @property
    def id3(self) -> str:
        """:class:`str`: The SteamID's ID 3.

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
    def invite_code(self) -> Optional[str]:
        """Optional[:class:`str`]: The SteamID's invite code in the s.team invite code format.

        e.g. ``cv-dgb``.
        """
        if self.type == Type.Individual and self.is_valid():
            invite_code = re.sub(f"[{_INVITE_HEX}]", lambda x: _INVITE_MAPPING[x.group()], f"{self.id:x}")
            split_idx = len(invite_code) // 2
            return invite_code if split_idx == 0 else f"{invite_code[:split_idx]}-{invite_code[split_idx:]}"

    @property
    def invite_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The SteamID's full invite code URL.

        e.g ``https://s.team/p/cv-dgb``.
        """
        code = self.invite_code
        return f"https://s.team/p/{code}" if code else None

    @property
    def community_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The SteamID's community url.

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
        """:class:`bool`: Whether or not the SteamID would be valid."""
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
    async def from_url(url: StrOrURL, session: Optional[ClientSession] = None) -> Optional[SteamID]:
        """|coro|
        A helper function creates a SteamID instance from a Steam community url.

        Parameters
        ----------
        url: Union[:class:`str`, :class:`yarl.URL`]
            The Steam community url to fetch.
        session: Optional[:class:`aiohttp.ClientSession`]
            The session to make the request with. If ``None`` is passed a new one is generated.

        Returns
        -------
        Optional[:class:`SteamID`]
            :class:`SteamID` instance or ``None``.
        """
        id64 = await id64_from_url(url, session)
        return SteamID(id64) if id64 else None


class Commentable(SteamID):
    """A mixin that implements commenting functionality"""

    __slots__ = (
        "comment_path",
        "_state",
        "__weakref__",
    )

    comment_path: Final[str]  # noqa  # type: ignore

    def __init_subclass__(cls, comment_path: str = "Profile") -> None:
        cls.comment_path: Final[str] = comment_path  # noqa  # type: ignore

    def copy(self: C) -> C:
        cls = self.__class__
        commentable = cls.__new__(cls)
        for name, attr in inspect.getmembers(self):
            try:
                setattr(commentable, name, attr)
            except (AttributeError, TypeError):
                pass
        return commentable

    __copy__ = copy

    async def comment(self, content: str) -> Comment:
        """|coro|
        Post a comment to a profile.

        Parameters
        -----------
        content: :class:`str`
            The message to add to the profile.

        Returns
        -------
        :class:`~steam.Comment`
            The created comment.
        """
        resp = await self._state.http.post_comment(self.id64, self.comment_path, content)
        id = int(re.findall(r'id="comment_(\d+)"', resp["comments_html"])[0])
        timestamp = datetime.utcfromtimestamp(resp["timelastpost"])
        comment = Comment(
            state=self._state, id=id, owner=self, timestamp=timestamp, content=content, author=self._state.client.user
        )
        self._state.dispatch("comment", comment)
        return comment

    def comments(
        self, limit: Optional[int] = None, before: Optional[datetime] = None, after: Optional[datetime] = None
    ) -> CommentsIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a profile's :class:`~steam.Comment` objects.

        Examples
        ---------

        Usage: ::

            async for comment in commentable.comments(limit=10):
                print('Author:', comment.author, 'Said:', comment.content)

        Flattening into a list: ::

            comments = await commentable.comments(limit=50).flatten()
            # comments is now a list of Comment

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of comments to search through.
            Default is ``None`` which will fetch the clan's entire comments section.
        before: Optional[:class:`datetime.datetime`]
            A time to search for comments before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for comments after.

        Yields
        ---------
        :class:`~steam.Comment`
            The comment with the comment information parsed.
        """
        return CommentsIterator(state=self._state, owner=self, limit=limit, before=before, after=after)


class BaseUser(Commentable):
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
    name: :class:`str`
        The user's username.
    state: :class:`~steam.PersonaState`
        The current persona state of the account (e.g. LookingToTrade).
    game: Optional[:class:`~steam.Game`]
        The Game instance attached to the user. Is ``None`` if the user isn't in a game or one that is recognised by the
        api.
    primary_clan: Optional[:class:`SteamID`]
        The primary clan the User displays on their profile.
    avatar_url: :class:`str`
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name: Optional[:class:`str`]
        The user's real name defined by them. Could be ``None``.
    created_at: Optional[:class:`datetime.datetime`]
        The time at which the user's account was created. Could be ``None``.
    last_logoff: Optional[:class:`datetime.datetime`]
        The last time the user logged into steam. Could be None (e.g. if they are currently online).
    country: Optional[:class:`str`]
        The country code of the account. Could be ``None``.
    flags: list[:class:`~steam.PersonaStateFlag`]
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
        "favourite_badge",
        "community_url",
        "_is_commentable",
        "_setup_profile",
        "_level",
    )

    def __init__(self, state: ConnectionState, data: UserDict):
        super().__init__(data["steamid"])
        self._state = state
        self.name: Optional[str] = None
        self.real_name: Optional[str] = None
        self.community_url: Optional[str] = None
        self.avatar_url: Optional[str] = None
        self.primary_clan: Optional[SteamID] = None
        self.country: Optional[str] = None
        self.created_at: Optional[datetime] = None
        self.last_logoff: Optional[datetime] = None
        self.last_logon: Optional[datetime] = None
        self.last_seen_online: Optional[datetime] = None
        self.game: Optional[Game] = None
        self.state: Optional[PersonaState] = None
        self.flags: list[PersonaStateFlag] = []
        self.privacy_state: Optional[CommunityVisibilityState] = None
        self._update(data)

    def _update(self, data: UserDict) -> None:
        self.name = data["personaname"]
        self.real_name = data.get("realname") or self.real_name
        self.community_url = data.get("profileurl") or super().community_url
        self.avatar_url = data.get("avatarfull") or self.avatar_url
        self.trade_url = URL.COMMUNITY / f"tradeoffer/new/?partner={self.id}"

        self.primary_clan = SteamID(data["primaryclanid"]) if "primaryclanid" in data else self.primary_clan
        self.country = data.get("loccountrycode") or self.country
        self.created_at = datetime.utcfromtimestamp(data["timecreated"]) if "timecreated" in data else self.created_at
        self.last_logoff = datetime.utcfromtimestamp(data["lastlogoff"]) if "lastlogoff" in data else self.last_logoff
        self.last_logon = datetime.utcfromtimestamp(data["last_logon"]) if "last_logon" in data else self.last_logon
        self.last_seen_online = (
            datetime.utcfromtimestamp(data["last_seen_online"]) if "last_seen_online" in data else self.last_seen_online
        )
        self.game = Game(title=data.get("gameextrainfo"), id=data["gameid"]) if "gameid" in data else self.game
        self.state = PersonaState(data.get("personastate", 0)) or self.state
        self.flags = PersonaStateFlag.components(data.get("personastateflags", 0)) or self.flags
        self.privacy_state = CommunityVisibilityState(data.get("communityvisibilitystate", 0))
        self._is_commentable = bool(data.get("commentpermission"))
        self._setup_profile = bool(data.get("profilestate"))

    def __repr__(self) -> str:
        attrs = ("name", "state", "id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    @property
    def mention(self) -> str:
        """:class:`str`: The string used to mention the user."""
        return f"[mention={self.id}]@{self.name}[/mention]"

    async def inventory(self, game: Game) -> Inventory:
        """|coro|
        Fetch an :class:`User`'s :class:`~steam.Inventory` for trading.

        Parameters
        -----------
        game: :class:`~steam.Game`
            The game to fetch the inventory for.

        Raises
        ------
        :exc:`~steam.Forbidden`
            The user's inventory is private.

        Returns
        -------
        :class:`Inventory`
            The user's inventory.
        """
        resp = await self._state.http.get_user_inventory(self.id64, game.id, game.context_id)
        return Inventory(state=self._state, data=resp, owner=self)

    async def friends(self) -> list[User]:
        """|coro|
        Fetch the list of :class:`~steam.User`'s friends from the API.

        Returns
        -------
        list[:class:`~steam.User`]
            The list of user's friends from the API.
        """
        friends = await self._state.http.get_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def games(self) -> list[UserGame]:
        """|coro|
        Fetches the :class:`~steam.Game` objects the :class:`User` owns from the API.

        Returns
        -------
        list[:class:`.UserGame`]
            The list of game objects from the API.
        """
        data = await self._state.http.get_user_games(self.id64)
        games = data["response"].get("games", [])
        return [UserGame(game) for game in games]

    async def clans(self) -> list[Clan]:
        """|coro|
        Fetches a list of the :class:`User`'s :class:`~steam.Clan`
        objects the :class:`User` is in from the API.

        Returns
        -------
        list[:class:`~steam.Clan`]
            The user's clans.
        """
        clans = []

        async def getter(gid: int) -> None:
            try:
                clan = await self._state.client.fetch_clan(gid)
            except WSException as exc:
                if exc.code == Result.RateLimitExceeded:
                    await asyncio.sleep(20)
                    await getter(gid)
            else:
                clans.append(clan)

        resp = await self._state.http.get_user_clans(self.id64)
        for clan in resp["response"]["groups"]:
            await getter(int(clan["gid"]))
        return clans

    async def bans(self) -> Ban:
        """|coro|
        Fetches the :class:`User`'s :class:`~steam.Ban` objects.

        Returns
        -------
        :class:`~steam.Ban`
            The user's bans.
        """
        resp = await self._state.http.get_user_bans(self.id64)
        resp = resp["players"][0]
        resp["EconomyBan"] = resp["EconomyBan"] != "none"
        return Ban(data=resp)

    async def badges(self) -> UserBadges:
        """|coro|
        Fetches the :class:`User`'s :class:`~steam.UserBadges` objects.

        Returns
        -------
        :class:`~steam.UserBadges`
            The user's badges.
        """
        resp = await self._state.http.get_user_badges(self.id64)
        return UserBadges(data=resp["response"])

    async def level(self) -> int:
        """|coro|
        Fetches the :class:`User`'s level.

        Returns
        -------
        :class:`int`
            The user's level.
        """
        if self._state.http.api_key is not None:
            resp = await self._state.http.get_user_level(self.id64)
            return resp["response"]["player_level"]
        return self._level

    async def wishlist(self) -> list[WishlistGame]:
        """|coro|
        Get a users wishlist.

        Returns
        -------
        list[:class:`.WishlistGame`]
        """
        data = await self._state.http.get_wishlist(self.id64)
        return [WishlistGame(id=id, data=game_info) for id, game_info in data.items()]

    def is_commentable(self) -> bool:
        """:class:`bool`: Specifies if the user's account is able to be commented on."""
        return self._is_commentable

    def is_private(self) -> bool:
        """:class:`bool`: Specifies if the user has a private profile."""
        return self.privacy_state == CommunityVisibilityState.Private

    def has_setup_profile(self) -> bool:
        """:class:`bool`: Specifies if the user has a setup their profile."""
        return self._setup_profile

    async def is_banned(self) -> bool:
        """|coro|
        Specifies if the user is banned from any part of Steam.

        This is equivalent to: ::

            bans = await user.bans()
            bans.is_banned()

        Returns
        -------
        :class:`bool`
            Whether or not the user is banned.
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
            self.trade_url = NotImplemented
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

            try:
                favourite_badge = data["favorite_badge"]
            except KeyError:
                self.favourite_badge = None
            else:
                icon_url = favourite_badge.pop("icon")
                self.favourite_badge = FavouriteBadge(**favourite_badge, icon_url=icon_url)

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


_EndPointReturnType: TypeAlias = "tuple[Union[tuple[int, int], int], Callable[..., Coroutine[None, None, Any]]]"


class _SupportsStr(Protocol):
    def __str__(self) -> str:
        ...


@runtime_checkable
class Messageable(Protocol[M]):
    """An ABC that details the common operations on a Steam message.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClanChannel`
        - :class:`~steam.GroupChannel`
        - :class:`~steam.DMChannel`
    """

    __slots__ = ()

    @abc.abstractmethod
    def _get_message_endpoint(self) -> _EndPointReturnType:
        raise NotImplementedError

    @abc.abstractmethod
    def _get_image_endpoint(self) -> _EndPointReturnType:
        raise NotImplementedError

    async def send(self, content: Optional[_SupportsStr] = None, image: Optional[Image] = None) -> Optional[M]:
        """|coro|
        Send a message to a certain destination.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content of the message to send.
        image: Optional[:class:`.Image`]
            The image to send to the user.

        Raises
        ------
        :exc:`~steam.HTTPException`
            Sending the message failed.
        :exc:`~steam.Forbidden`
            You do not have permission to send the message.

        Returns
        -------
        Optional[:class:`Message`]
            The sent message only applicable if ``content`` is passed.
        """
        message = None
        if content is not None:
            destination, message_func = self._get_message_endpoint()
            message = await message_func(destination, str(content))
        if image is not None:
            destination, image_func = self._get_image_endpoint()
            await image_func(destination, image)

        return message


@attr.dataclass(slots=True)
class Channel(Messageable[M]):
    _state: ConnectionState
    clan: Optional[Clan] = None
    group: Optional[Group] = None

    @abc.abstractmethod
    def history(
        self,
        limit: Optional[int] = 100,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> AsyncIterator[M]:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`steam.Channel`'s :class:`steam.Message`
        objects.

        Examples
        --------

        Usage: ::

            async for message in channel.history(limit=10):
                print('Author:', message.author, 'Said:', message.content)

        Flattening into a list: ::

            messages = await channel.history(limit=50).flatten()
            # messages is now a list of Message

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of trades to search through.
            Setting this to ``None`` will fetch all of the channel's messages, but this will be a very slow operation.
        before: Optional[:class:`datetime.datetime`]
            A time to search for messages before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for messages after.

        Yields
        ------
        :class:`~steam.Message`
        """
        raise NotImplementedError

    if TYPE_CHECKING:

        async def send(self, content: Optional[_SupportsStr] = None, image: Optional[Image] = None) -> Optional[M]:
            ...


def _clean_up_content(content: str) -> str:  # steam does weird stuff with content
    return content.replace(r"\[", "[").replace("\\\\", "\\")


class Message:
    """Represents a message from a :class:`~steam.User`. This is a base class from which all messages inherit.

    The following classes implement this:

        - :class:`~steam.UserMessage`
        - :class:`~steam.GroupMessage`
        - :class:`~steam.ClanMessage`

    Attributes
    ----------
    channel: :class:`Channel`
        The channel the message was sent in.
    content: :class:`str`
        The message's content.

        Note
        ----
        This is **not** what you will see in the steam client see :attr:`clean_content` for that.
    clean_content: :class:`str`
        The message's clean content without bbcode.
    author: :class:`~steam.User`
        The message's author.
    created_at: :class:`datetime.datetime`
        The time the message was sent at.
    group: Optional[:class:`~steam.Group`]
        The group the message was sent in. Will be ``None`` if the message wasn't sent in a :class:`~steam.Group`.
    clan: Optional[:class:`~steam.Clan`]
        The clan the message was sent in. Will be ``None`` if the message wasn't sent in a :class:`~steam.Clan`.
    """

    __slots__ = (
        "author",
        "content",
        "channel",
        "clean_content",
        "created_at",
        "group",
        "clan",
        "mentions",
        "_state",
    )
    author: User
    created_at: datetime

    def __init__(self, channel: Channel, proto: Any):
        self._state: ConnectionState = channel._state
        self.channel = channel
        self.group: Optional[Group] = channel.group
        self.clan: Optional[Clan] = channel.clan
        self.content: str = _clean_up_content(proto.message)
        self.clean_content: str = getattr(proto, "message_no_bbcode", None) or self.content
        self.mentions: Optional[CChatMentions] = getattr(proto, "mentions", None)

    def __repr__(self) -> str:
        attrs = ("author", "channel")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"
