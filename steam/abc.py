"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import abc
import asyncio
import re
from collections.abc import Coroutine
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, TypeVar

import attr
from typing_extensions import ClassVar, Final, Protocol, Required, Self, TypedDict, runtime_checkable

from ._const import URL
from .badge import FavouriteBadge, UserBadges
from .enums import *
from .errors import WSException
from .game import Game, StatefulGame, UserGame, WishlistGame
from .iterators import AsyncIterator, CommentsIterator, UserPublishedFilesIterator, UserReviewsIterator
from .models import Ban
from .profile import *
from .reaction import Award, AwardReaction, Emoticon, MessageReaction, PartialMessageReaction, Sticker
from .trade import Inventory
from .utils import (
    _INVITE_HEX,
    _INVITE_MAPPING,
    DateTime,
    InstanceType,
    Intable,
    TypeType,
    UniverseType,
    cached_slot_property,
    id64_from_url,
    make_id64,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from .clan import Clan
    from .comment import Comment
    from .group import Group
    from .http import StrOrURL
    from .image import Image
    from .message import Authors
    from .protobufs.chat import Mentions
    from .review import Review
    from .state import ConnectionState
    from .types.id import ID32, ID64
    from .user import User

__all__ = (
    "SteamID",
    "Message",
    "Channel",
)

C = TypeVar("C", bound="Commentable")
M_co = TypeVar("M_co", bound="Message", covariant=True)


# TODO when defaults are implemented, make this Generic over Literal[Type] maybe
# TypeT = typing.TypeVar("TypeT", bound=Type)
#
#
# class SteamID(typing.Generic[TypeT]):
#     type TypeT
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

    def __int__(self) -> ID64:
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
    def instance(self) -> InstanceFlag:
        """The instance of the SteamID."""
        return InstanceFlag.try_value((self.__BASE >> 32) & 0xFFFFF)

    @property
    def type(self) -> Type:
        """The Steam type of the SteamID."""
        return Type((self.__BASE >> 52) & 0xF)

    @property
    def universe(self) -> Universe:
        """The Steam universe of the SteamID."""
        return Universe((self.__BASE >> 56) & 0xFF)

    @property
    def id64(self) -> ID64:
        """The SteamID's 64-bit ID."""
        return self.__BASE

    @property
    def id(self) -> ID32:
        """The SteamID's 32-bit ID."""
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
            if self.instance != InstanceFlag.Desktop:
                instance = self.instance
        elif self.type == Type.Chat:
            if self.instance & InstanceFlag.ChatClan > 0:
                type_char = "c"
            elif self.instance & InstanceFlag.ChatLobby > 0:
                type_char = "L"
            else:
                type_char = "T"

        return f"[{type_char}:{self.universe.value}:{self.id}{f':{instance.value}' if instance is not None else ''}]"

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
        """Whether the SteamID is valid."""
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


class _CommentableKwargs(TypedDict, total=False):
    id64: Required[int]
    thread_type: Required[int]
    gidfeature: int
    gidfeature2: int
    thread_id: int
    upvotes: int
    include_deleted: bool


class Commentable(Protocol):
    """A mixin that implements commenting functionality."""

    __slots__ = ()
    _state: ConnectionState

    @property
    @abc.abstractmethod
    def _commentable_kwargs(self) -> _CommentableKwargs:
        raise NotImplementedError

    async def fetch_comment(self, id: int) -> Comment[Self]:
        """Fetch a comment by its ID.

        Parameters
        ----------
        id
            The ID of the comment to fetch.
        """
        from .comment import Comment

        comment = await self._state.fetch_comment(self, id)
        return Comment(
            self._state,
            id=comment.id,
            content=comment.content,
            created_at=DateTime.from_timestamp(comment.timestamp),
            author=await self._state._maybe_user(comment.author_id64),
            owner=self,
            reactions=[AwardReaction(self._state, reaction) for reaction in comment.reactions],
        )

    async def comment(self, content: str, *, subscribe: bool = True) -> Comment[Self]:
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
        self,
        *,
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
            Default is ``None`` which will fetch the all the comments in the comments section.
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


class Awardable(Protocol):
    """A mixin that implements award functionality."""

    __slots__ = ()

    id: int
    _state: ConnectionState
    _AWARDABLE_TYPE: ClassVar[int]

    async def award(self, award: Award) -> None:
        """Add an :class:`Award` to this piece of user generated content.

        Parameters
        ----------
        award
            The award to add.
        """
        await self._state.add_award(self, award)

    # async def fetch_reactions(self) -> list[AwardReaction]:
    #     """Fetch the reactions on this piece of user generated content."""
    #     reactions = await self._state.fetch_award_reactions(self)
    #     return [AwardReaction(self._state, reaction) for reaction in reactions]


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
    rich_presence
        The user's rich presence.
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
        "rich_presence",
        "privacy_state",
        "community_url",
        "comment_permissions",
        "profile_state",
        "_level",
        "_state",
        "__weakref__",
    )

    name: str
    real_name: str | None
    community_url: str | None
    avatar_url: str | None  # TODO make this a property and add avatar hash
    primary_clan: Clan | None
    country: str | None
    created_at: datetime | None
    last_logoff: datetime | None
    last_logon: datetime | None
    last_seen_online: datetime | None
    game: StatefulGame | None
    state: PersonaState | None
    flags: PersonaStateFlag | None
    privacy_state: CommunityVisibilityState | None
    comment_permissions: CommentPrivacyState | None
    profile_state: CommunityVisibilityState | None
    rich_presence: dict[str, str] | None
    _state: ConnectionState

    def __repr__(self) -> str:
        attrs = ("name", "state", "id", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.id64,
            "thread_type": 10,
        }

    @property
    def mention(self) -> str:
        """The string used to mention the user in chat."""
        return f"[mention={self.id}]@{self.name}[/mention]"

    async def inventory(self, game: Game, *, language: Language | None = None) -> Inventory:
        """Fetch a user's :class:`~steam.Inventory` for trading.

        Parameters
        -----------
        game
            The game to fetch the inventory for.
        language
            The language to fetch the inventory in. If ``None`` will default to the current language.

        Raises
        ------
        :exc:`~steam.Forbidden`
            The user's inventory is private.
        """
        resp = await self._state.http.get_user_inventory(self.id64, game.id, game.context_id, language)
        return Inventory(state=self._state, data=resp, owner=self, game=game, language=language)

    async def friends(self) -> list[User]:
        """Fetch the list of the users friends."""
        friends = await self._state.http.get_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def games(self, *, include_free: bool = True) -> list[UserGame]:
        r"""Fetches the :class:`~steam.Game`\s the user owns.

        Parameters
        ----------
        include_free
            Whether to include free games in the list. Defaults to ``True``.
        """
        games = await self._state.fetch_user_games(self.id64, include_free)
        return [UserGame(self._state, game) for game in games]

    async def clans(self) -> list[Clan]:
        r"""Fetches a list of :class:`~steam.Clan`\s the user is in."""

        async def getter(gid: int) -> Clan:
            try:
                clan = await self._state.client.fetch_clan(gid)
                assert clan is not None
                return clan
            except WSException as exc:
                if exc.code == Result.RateLimitExceeded:
                    await asyncio.sleep(20)
                    return await getter(gid)
                raise

        resp = await self._state.http.get_user_clans(self.id64)
        return await asyncio.gather(*(getter(int(clan["gid"])) for clan in resp["response"]["groups"]))  # type: ignore

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
        """The user's favourite badge."""
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

    async def equipped_profile_items(self, *, language: Language | None = None) -> EquippedProfileItems:
        """The user's equipped profile items.

        Parameters
        ----------
        language
            The language to fetch the profile items in. If ``None`` the current language is used
        """
        items = await self._state.fetch_user_equipped_profile_items(self.id64, language)
        return EquippedProfileItems(
            background=ProfileItem(self._state, self, items.profile_background) if items.profile_background else None,
            mini_profile_background=(
                ProfileItem(self._state, self, items.mini_profile_background) if items.mini_profile_background else None
            ),
            avatar_frame=ProfileItem(self._state, self, items.avatar_frame) if items.avatar_frame else None,
            animated_avatar=ProfileItem(self._state, self, items.animated_avatar) if items.animated_avatar else None,
            modifier=ProfileItem(self._state, self, items.profile_modifier) if items.profile_modifier else None,
        )

    async def profile_customisation_info(self, *, language: Language | None = None) -> ProfileCustomisation:
        """Fetch a user's profile customisation information.

        Parameters
        ----------
        language
            The language to fetch the profile items in. If ``None`` the current language is used
        """
        info = await self._state.fetch_user_profile_customisation(self.id64, language)
        return ProfileCustomisation(self._state, self, info)

    async def profile(self, *, language: Language | None = None) -> Profile:
        """Fetch a user's entire profile information.

        Parameters
        ----------
        language
            The language to fetch the profile items in. If ``None`` the current language is used

        Note
        ----
        This calls all the profile related functions to return a Profile object which has all the info set.
        """

        return Profile(
            *await asyncio.gather(
                self.equipped_profile_items(language=language),
                self.profile_customisation_info(language=language),
            )
        )

    def is_commentable(self) -> bool:
        """Specifies if the user's account can be commented on."""
        if hasattr(self, "is_friend"):
            return self.comment_permissions in (
                CommentPrivacyState.Public,
                CommentPrivacyState.FriendsOnly if self.is_friend() else CommentPrivacyState.Public,
            )
        return True  # our account

    def is_private(self) -> bool:
        """Specifies if the user has a private profile."""
        return self.privacy_state == CommunityVisibilityState.Private

    async def is_banned(self) -> bool:
        """Specifies if the user is banned from any part of Steam.

        Shorthand for:

        .. code-block:: python3

            bans = await user.bans()
            bans.is_banned()
        """
        bans = await self.bans()
        return bans.is_banned()

    def reviews(
        self,
        *,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> UserReviewsIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a user's :class:`~steam.Review`\\s.

        Examples
        --------
        Usage:

        .. code-block:: python3

            async for review in user.reviews(limit=10):
                print(f"Author: {review.author} {'recommended' if review.recommend 'doesn\\'t recommend'} {review.game}")

        Flattening into a list:

        .. code-block:: python3

            reviews = await user.reviews(limit=50).flatten()
            # reviews is now a list of Review

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of reviews to search through. Setting this to ``None`` will fetch all the
            user's reviews.
        before
            A time to search for reviews before.
        after
            A time to search for reviews after.

        Yields
        ------
        :class:`~steam.Review`
        """
        return UserReviewsIterator(self._state, self, limit, before, after)

    async def fetch_review(self, game: Game) -> Review:
        """Fetch this user's review for a game.

        Parameters
        ----------
        game
            The games to fetch the reviews for.
        """
        (review,) = await self.fetch_reviews(game)
        return review

    async def fetch_reviews(self, *games: Game) -> list[Review]:
        """Fetch this user's review for games.

        Parameters
        ----------
        games
            The games to fetch the reviews for.
        """
        from .review import Review

        reviews = await self._state.fetch_user_review(self.id64, (game.id for game in games))
        return [Review._from_proto(self._state, review, self) for review in reviews]

    def published_files(
        self,
        *,
        game: Game | None = None,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        type: PublishedFileType = PublishedFileType.Community,
        language: Language | None = None,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> UserPublishedFilesIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a user's :class:`~steam.PublishedFile`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for file in user.published_files(limit=10):
                print("Author:", file.author, "Published:", file.name)

        Flattening into a list:

        .. code-block:: python3

            files = await user.published_files(limit=50).flatten()
            # files is now a list of PublishedFile

        All parameters are optional.

        Parameters
        ----------
        game
            The game to fetch published files in.
        type
            The type of published file to fetch.
        revision
            The desired revision of the published file to fetch.
        language
            The language to fetch the published file in. If ``None``, the current language is used.
        limit
            The maximum number of published files to search through. Setting this to ``None`` will fetch all of the
            user's published files.
        before
            A time to search for published files before.
        after
            A time to search for published files after.

        Yields
        ------
        :class:`~steam.PublishedFile`
        """
        return UserPublishedFilesIterator(self._state, self, game, type, revision, language, limit, before, after)

    @classmethod
    def _patch_without_api(cls) -> None:
        import functools

        def __init__(self, state: ConnectionState, data: dict[str, Any]) -> None:
            super().__init__(data["steamid"])
            self._state = state
            self.name = data["persona_name"]
            self.avatar_url = data.get("avatar_url") or self.avatar_url
            self.community_url = super().community_url
            self.trade_url = URL.COMMUNITY / f"tradeoffer/new?partner={self.id}"

            self.real_name = NotImplemented
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
            self.comment_permissions = NotImplemented
            self.profile_state = NotImplemented
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
        message = None if content is None else await self._message_func(str(content))
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
        *,
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


STEAM_EPOCH = datetime(2005, 1, 1, tzinfo=timezone.utc)


class Message(metaclass=abc.ABCMeta):
    """Represents a message from a :class:`~steam.User`. This is a base class from which all messages inherit.

    The following classes implement this:

        - :class:`~steam.UserMessage`
        - :class:`~steam.GroupMessage`
        - :class:`~steam.ClanMessage`

    .. container:: operations

        .. describe:: x == y

            Checks if two messages are equal

        .. describe:: hash(x)

            Returns the hash of a message.

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
        "reactions",
        "partial_reactions",
        "_id_cs",
        "_state",
    )

    author: Authors
    """The message's author."""
    channel: Channel[Self]
    """The channel the message was sent in."""
    content: str
    """The message's content.

    Note
    ----
    This is **not** what you will see in the steam client see :attr:`clean_content` for that.
    """
    clean_content: str
    """The message's clean content without BBCode."""
    created_at: datetime
    """The time this message was sent at."""
    clan: Clan | None
    """The clan the message was sent in. Will be ``None`` if the message wasn't sent in a :class:`~steam.Clan`."""
    group: Group | None
    """The group the message was sent in. Will be ``None`` if the message wasn't sent in a :class:`~steam.Group`."""
    reactions: list[MessageReaction]
    """The message's reactions."""
    ordinal: int
    """A per-channel incremented integer up to ``1000`` for every message sent in a second window."""
    mentions: Mentions | None
    """An object representing mentions in this message."""
    reactions: list[MessageReaction]
    """The reactions this message has received."""
    partial_reactions: list[PartialMessageReaction]

    def __init__(self, channel: Channel[Self], proto: Any):
        self._state: ConnectionState = channel._state
        self.channel = channel
        self.group = channel.group
        self.clan = channel.clan
        self.content = _clean_up_content(proto.message)
        self.ordinal = proto.ordinal
        self.clean_content = getattr(proto, "message_no_bbcode", "") or self.content
        self.mentions = getattr(proto, "mentions", None)
        self.partial_reactions = []
        self.reactions = []

    def __repr__(self) -> str:
        attrs = ("author", "id", "channel")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return (
            self.channel == other.channel and self.id == other.id
            if isinstance(other, self.__class__)
            else NotImplemented
        )

    def __hash__(self) -> int:
        return hash((self.channel, self.id))

    @cached_slot_property
    def id(self) -> int:
        """A unique identifier for every message sent in a channel.

        Note
        ----
        This is **not** something Steam provides, this is meant to be a simple way to compare messages.
        """
        # a u64 "snowflake-esk" id measuring of the number of seconds passed since Steam's EPOCH and then the
        # "sequence"/ordinal of the message.
        return int(
            f"{int((self.created_at - STEAM_EPOCH).total_seconds()):032b}{self.ordinal:032b}",
            base=2,
        )

    # @abc.abstractmethod
    # async def delete(self) -> None:
    #     raise NotImplementedError()

    @abc.abstractmethod
    async def add_emoticon(self, emoticon: Emoticon) -> None:
        """Adds an emoticon to this message.

        Parameters
        ----------
        emoticon
            The emoticon to add to this message.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def remove_emoticon(self, emoticon: Emoticon) -> None:
        """Removes an emoticon from this message.

        Parameters
        ----------
        emoticon
            The emoticon to remove from this message.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def add_sticker(self, sticker: Sticker) -> None:
        """Adds a sticker to this message.

        Parameters
        ----------
        sticker
            The sticker to add to this message.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def remove_sticker(self, sticker: Sticker) -> None:
        """Adds a sticker to this message.

        Parameters
        ----------
        sticker
            The sticker to remove from this message.
        """
        raise NotImplementedError()
