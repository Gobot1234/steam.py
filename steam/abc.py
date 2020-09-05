# -*- coding: utf-8 -*-

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

import abc
import asyncio
import re
from datetime import datetime
from typing import TYPE_CHECKING, Awaitable, Callable, List, NoReturn, Optional, SupportsInt, Tuple, Union, overload

from typing_extensions import Final, TypedDict

from .badge import UserBadges
from .comment import Comment
from .enums import (
    ECommunityVisibilityState,
    EInstanceFlag,
    EPersonaState,
    EPersonaStateFlag,
    EResult,
    EType,
    ETypeChar,
    EUniverse,
)
from .errors import WSException
from .game import Game
from .iterators import CommentsIterator
from .models import Ban, community_route
from .trade import Inventory
from .utils import (
    _INVITE_HEX,
    _INVITE_MAPPING,
    ETypeType,
    EUniverseType,
    InstanceType,
    IntOrStr,
    id64_from_url,
    make_id64,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from .clan import Clan
    from .group import Group
    from .http import StrOrURL
    from .image import Image
    from .state import ConnectionState
    from .user import User


__all__ = (
    "SteamID",
    "Message",
)


class UserDict(TypedDict):
    personaname: str
    steamid: str
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
    """Convert a Steam ID between its various representations."""

    __slots__ = (
        "__BASE",
        "__weakref__",
    )

    @overload
    def __init__(self):
        ...

    @overload
    def __init__(
        self,
        id: IntOrStr = 0,
        type: Optional[ETypeType] = None,
        universe: Optional[EUniverseType] = None,
        instance: Optional[InstanceType] = None,
    ):
        ...

    def __init__(
        self,
        id: IntOrStr = 0,
        type: Optional[ETypeType] = None,
        universe: Optional[EUniverseType] = None,
        instance: Optional[InstanceType] = None,
    ):
        self.__BASE: Final[int] = make_id64(id, type, universe, instance)

    def __int__(self):
        return self.__BASE

    def __eq__(self, other: SupportsInt):
        try:
            return int(self) == int(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __str__(self):
        return str(self.__BASE)

    def __hash__(self):
        return hash(self.__BASE)

    def __repr__(self):
        return f"SteamID(id={self.id}, type={self.type}, universe={self.universe}, instance={self.instance})"

    @property
    def instance(self) -> int:
        """:class:`int`: The instance of the SteamID."""
        return (int(self) >> 32) & 0xFFFFF

    @property
    def type(self) -> EType:
        """:class:`~steam.EType`: The Steam type of the SteamID."""
        return EType((int(self) >> 52) & 0xF)

    @property
    def universe(self) -> EUniverse:
        """:class:`~steam.EUniverse`: The Steam universe of the SteamID."""
        return EUniverse((int(self) >> 56) & 0xFF)

    @property
    def id64(self) -> int:
        """:class:`int`: The SteamID's 64 bit ID."""
        return int(self)

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
        """:class:`str`: The SteamID's ID 2 accounted for bugged GoldSrc and Orange Box games. In these games the
        accounts :attr:`universe`, ``1`` for :class:`.EType.Public`, should be the ``X`` component of ``STEAM_X:0:1234``
        however, this was bugged and the value of ``X`` was ``0``.

        e.g ``STEAM_0:0:1234``.
        """
        return self.id2.replace("_1", "_0")

    @property
    def id3(self) -> str:
        """:class:`str`: The SteamID's ID 3.

        e.g ``[U:1:1234]``.
        """
        type_char = ETypeChar(self.type).name
        instance = None

        if self.type in (EType.AnonGameServer, EType.Multiseat):
            instance = self.instance
        elif self.type == EType.Individual:
            if self.instance != 1:
                instance = self.instance
        elif self.type == EType.Chat:
            if self.instance & EInstanceFlag.Clan:
                type_char = "c"
            elif self.instance & EInstanceFlag.Lobby:
                type_char = "L"
            else:
                type_char = "T"

        parts = [type_char, int(self.universe), self.id]

        if instance is not None:
            parts.append(instance)

        return f'[{":".join(map(str, parts))}]'

    @property
    def invite_code(self) -> Optional[str]:
        """Optional[:class:`str`]: The SteamID's invite code in the s.team invite code format.

        e.g. ``cv-dgb``.
        """
        if self.type == EType.Individual and self.is_valid():

            def repl_mapper(x: re.Match):
                return _INVITE_MAPPING[x.group()]

            invite_code = re.sub(f"[{_INVITE_HEX}]", repl_mapper, f"{self.id:x}")
            split_idx = len(invite_code) // 2

            if split_idx:
                invite_code = f"{invite_code[:split_idx]}-{invite_code[split_idx:]}"

            return invite_code

    @property
    def invite_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The SteamID's full invite code URL.

        e.g ``https://s.team/p/cv-dgb``.
        """
        code = self.invite_code
        if code:
            return f"https://s.team/p/{code}"

    @property
    def community_url(self) -> Optional[str]:
        """Optional[:class:`str`]: The SteamID's community url.

        e.g https://steamcommunity.com/profiles/123456789.
        """
        suffix = {
            EType.Individual: "profiles",
            EType.Clan: "gid",
        }
        try:
            return f"https://steamcommunity.com/{suffix[self.type]}/{self.id64}"
        except KeyError:
            pass

    def is_valid(self) -> bool:
        """:class:`bool`: Whether or not the SteamID would be valid."""
        if self.type == EType.Invalid or self.type >= EType.Max:
            return False

        if self.universe == EUniverse.Invalid or self.universe >= EUniverse.Max:
            return False

        if self.type == EType.Individual:
            if self.id == 0 or self.instance > 4:
                return False

        if self.type == EType.Clan:
            if self.id == 0 or self.instance != 0:
                return False

        if self.type == EType.GameServer:
            if self.id == 0:
                return False

        if self.type == EType.AnonGameServer:
            if self.id == 0 and self.instance == 0:
                return False

        return True

    @classmethod
    async def from_url(
        cls, url: "StrOrURL", session: Optional["ClientSession"] = None, timeout: float = 30
    ) -> Optional["SteamID"]:
        """|coro|
        A helper function creates a SteamID instance from a Steam community url. See :func:`id64_from_url` for details.

        Parameters
        ----------
        url: Union[:class:`str`, :class:`yarl.URL`]
            The Steam community url to fetch.
        session: Optional[:class:`aiohttp.ClientSession`]
            The session to make the request with. If ``None`` is passed a new one is generated.
        timeout: :class:`float`
            How long to wait for a response before returning ``None``.

        Returns
        -------
        Optional[:class:`SteamID`]
            :class:`SteamID` instance or ``None``.
        """
        id64 = await id64_from_url(url, session, timeout)
        return cls(id64) if id64 else None


class BaseUser(SteamID):
    """An ABC that details the common operations on a Steam user.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClientUser`

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: x != y

            Checks if two users are not equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name: :class:`str`
        The user's username.
    state: :class:`~steam.EPersonaState`
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
    flags: List[:class:`~steam.EPersonaStateFlag`]
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
        "_state",
        "_is_commentable",
        "_setup_profile",
    )

    def __init__(self, state: "ConnectionState", data: dict):
        super().__init__(data["steamid"])
        self._state = state
        self.name: Optional[str] = None
        self.real_name: Optional[str] = None
        self.avatar_url: Optional[str] = None
        self.primary_clan: Optional[SteamID] = None
        self.country: Optional[str] = None
        self.created_at: Optional[datetime] = None
        self.last_logoff: Optional[datetime] = None
        self.last_logon: Optional[datetime] = None
        self.last_seen_online: Optional[datetime] = None
        self.game: Optional[Game] = None
        self.state: Optional[EPersonaState] = None
        self.flags: List[EPersonaStateFlag] = []
        self.privacy_state: Optional[ECommunityVisibilityState] = None
        self._update(data)

    def __repr__(self):
        attrs = ("name", "state", "id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<User {' '.join(resolved)}>"

    def __str__(self):
        return self.name

    def _update(self, data: UserDict) -> None:
        self.name = data["personaname"]
        self.real_name = data.get("realname") or self.real_name
        self.avatar_url = data.get("avatarfull") or self.avatar_url
        self.trade_url = community_route(f"tradeoffer/new/?partner={self.id}")

        self.primary_clan = SteamID(data["primaryclanid"]) if "primaryclanid" in data else self.primary_clan
        self.country = data.get("loccountrycode") or self.country
        self.created_at = datetime.utcfromtimestamp(data["timecreated"]) if "timecreated" in data else self.created_at
        self.last_logoff = datetime.utcfromtimestamp(data["lastlogoff"]) if "lastlogoff" in data else self.last_logoff
        self.last_logon = datetime.utcfromtimestamp(data["last_logon"]) if "last_logon" in data else self.last_logon
        self.last_seen_online = (
            datetime.utcfromtimestamp(data["last_seen_online"]) if "last_seen_online" in data else self.last_seen_online
        )
        self.game = Game(title=data.get("gameextrainfo"), id=data["gameid"]) if "gameid" in data else self.game
        self.state = EPersonaState(data.get("personastate", 0)) or self.state
        self.flags = EPersonaStateFlag.components(data.get("personastateflags", 0)) or self.flags
        self.privacy_state = ECommunityVisibilityState(data.get("communityvisibilitystate", 0))
        self._is_commentable = bool(data.get("commentpermission"))
        self._setup_profile = bool(data.get("profilestate"))

    @property
    def mention(self) -> str:
        """:class:`str`: The string used to mention the user."""
        return f"[mention={self.id}]@{self.name}[/mention]"

    async def comment(self, content: str) -> Comment:
        """|coro|
        Post a comment to an :class:`User`'s profile.

        Parameters
        -----------
        content: :class:`str`
            The message to add to the user's profile.

        Returns
        -------
        :class:`~steam.Comment`
            The created comment.
        """
        resp = await self._state.http.post_comment(self.id64, "Profile", content)
        id = int(re.findall(r'id="comment_(\d+)"', resp["comments_html"])[0])
        timestamp = datetime.utcfromtimestamp(resp["timelastpost"])
        comment = Comment(
            state=self._state, id=id, owner=self, timestamp=timestamp, content=content, author=self._state.client.user
        )
        self._state.dispatch("comment", comment)
        return comment

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

    async def friends(self) -> List["User"]:
        """|coro|
        Fetch the list of :class:`~steam.User`'s friends from the API.

        Returns
        -------
        List[:class:`~steam.User`]
            The list of user's friends from the API.
        """
        friends = await self._state.http.get_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def games(self) -> List[Game]:
        """|coro|
        Fetches the :class:`~steam.Game` objects the :class:`User` owns from the API.

        Returns
        -------
        List[:class:`~steam.Game`]
            The list of game objects from the API.
        """
        data = await self._state.http.get_user_games(self.id64)
        games = data["response"].get("games", [])
        return [Game._from_api(game) for game in games]

    async def clans(self) -> List["Clan"]:
        """|coro|
        Fetches a list of the :class:`User`'s :class:`~steam.Clan`
        objects the :class:`User` is in from the API.

        Returns
        -------
        List[:class:`~steam.Clan`]
            The user's clans.
        """
        clans = []

        async def getter(gid: int):
            try:
                clan = await self._state.client.fetch_clan(gid)
            except WSException as exc:
                if exc.code == EResult.RateLimitExceeded:
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
        resp["EconomyBan"] = False if resp["EconomyBan"] == "none" else True
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
        resp = await self._state.http.get_user_level(self.id64)
        return resp["response"]["player_level"]

    def is_commentable(self) -> bool:
        """:class:`bool`: Specifies if the user's account is able to be commented on."""
        return self._is_commentable

    def is_private(self) -> bool:
        """:class:`bool`: Specifies if the user has a public profile."""
        return self.privacy_state == ECommunityVisibilityState.Private

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

    def comments(
        self, limit: Optional[int] = None, before: Optional[datetime] = None, after: Optional[datetime] = None
    ) -> CommentsIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`~steam.User`'s :class:`~steam.Comment`
        objects.

        Examples
        -----------

        Usage: ::

            async for comment in user.comments(limit=10):
                print('Author:', comment.author, 'Said:', comment.content)

        Flattening into a list: ::

            comments = await user.comments(limit=50).flatten()
            # comments is now a list of Comment

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of comments to search through. Default is ``None`` which will fetch the user's entire
            comments section.
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


_EndPointReturnType = Tuple[Union[Tuple[int, int], int], Callable[..., Awaitable[None]]]


class Messageable(metaclass=abc.ABCMeta):
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

    async def send(self, content: Optional[str] = None, image: Optional["Image"] = None) -> None:
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
        """
        if content is not None:
            destination, message_func = self._get_message_endpoint()
            await message_func(destination, str(content))
        if image is not None:
            destination, image_func = self._get_image_endpoint()
            await image_func(destination, image)


class BaseChannel(Messageable):
    __slots__ = ("clan", "group", "_state")

    _state: "ConnectionState"

    def __init__(self):
        self.clan: Optional["Clan"] = None
        self.group: Optional["Group"] = None

    @abc.abstractmethod
    def typing(self) -> NoReturn:
        raise NotImplementedError

    @abc.abstractmethod
    async def trigger_typing(self) -> NoReturn:
        raise NotImplementedError


def _clean_up_content(content: str) -> str:
    return content.replace(r"\[", "[").replace("\\\\", "\\")


class Message:
    """Represents a message from a :class:`~steam.User`
    This is a base class from which all messages inherit.

    The following classes implement this:

        - :class:`~steam.UserMessage`
        - :class:`~steam.GroupMessage`
        - :class:`~steam.ClanMessage`

    Attributes
    ----------
    channel: :class:`BaseChannel`
        The channel the message was sent in.
    content: :class:`str`
        The message's content.
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
        "_state",
    )

    def __init__(self, channel: "BaseChannel", proto):
        self._state: "ConnectionState" = channel._state
        self.channel = channel
        self.group: Optional["Group"] = channel.group
        self.clan: Optional["Clan"] = channel.clan
        self.content: str = _clean_up_content(proto.message)
        self.clean_content: str = proto.message_no_bbcode or self.content
        self.author: "User"
        self.created_at: datetime

    def __repr__(self) -> str:
        attrs = ("author", "channel")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"
