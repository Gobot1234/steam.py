"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import abc
import asyncio
from collections.abc import AsyncGenerator, Coroutine
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypedDict, TypeVar, runtime_checkable

from bs4 import BeautifulSoup
from typing_extensions import Required, Self
from yarl import URL as URL_

from ._const import HTML_PARSER, UNIX_EPOCH, URL
from .app import App, StatefulApp, UserApp, WishlistApp
from .badge import FavouriteBadge, UserBadges
from .enums import *
from .errors import WSException
from .id import ID
from .models import Ban
from .profile import *
from .reaction import Award, AwardReaction, Emoticon, MessageReaction, PartialMessageReaction, Sticker
from .trade import Inventory
from .utils import DateTime, cached_slot_property

if TYPE_CHECKING:
    from .clan import Clan
    from .comment import Comment
    from .group import Group
    from .image import Image
    from .message import Authors
    from .protobufs.chat import Mentions
    from .published_file import PublishedFile
    from .review import Review
    from .state import ConnectionState
    from .user import User

__all__ = (
    "Message",
    "Channel",
)

C = TypeVar("C", bound="Commentable")
M_co = TypeVar("M_co", bound="Message", covariant=True)


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

    async def comments(
        self,
        *,
        oldest_first: bool = False,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[Comment[Self], None]:
        """An :term:`async iterator` for accessing a comment section's :class:`~steam.Comment` objects.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for comment in commentable.comments(limit=10):
                print("Author:", comment.author, "Said:", comment.content)

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
        from .comment import Comment
        from .reaction import AwardReaction

        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        count: int | None = None
        total_count = 0
        yielded = 0

        async def get_comments(chunk: int) -> list[Comment[Self]]:
            nonlocal after, before, count, total_count, yielded

            starting_from = total_count - count if total_count and count else 0
            proto = await self._state.fetch_comments(self, chunk, starting_from, oldest_first)

            if count is None:
                total_count = count = proto.total_count

            comments: list[Comment[Self]] = []
            comment = None
            for comment in proto.comments:
                comment = Comment(
                    self._state,
                    id=comment.id,
                    content=comment.content,
                    created_at=DateTime.from_timestamp(comment.timestamp),
                    reactions=[AwardReaction(self._state, reaction) for reaction in comment.reactions],
                    author=comment.author_id64,  # type: ignore
                    owner=self,
                )
                if after < comment.created_at < before:
                    if limit is not None and yielded >= limit:
                        break
                    comments.append(comment)
                    yielded += 1
                else:
                    break

            count -= len(comments)
            return comments

        for comment in await get_comments(min(limit or 100, 100)):
            yield comment

        assert count is not None
        while count > 0:
            for comment in await get_comments(min(count, 100)):
                yield comment


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


class BaseUser(ID, Commentable):
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
    app
        The App instance attached to the user. Is ``None`` if the user isn't in an app or one that is recognised by the
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
        "app",
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
    app: StatefulApp | None
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

    async def inventory(self, app: App, *, language: Language | None = None) -> Inventory:
        """Fetch a user's :class:`~steam.Inventory` for trading.

        Parameters
        -----------
        app
            The app to fetch the inventory for.
        language
            The language to fetch the inventory in. If ``None`` will default to the current language.

        Raises
        ------
        :exc:`~steam.Forbidden`
            The user's inventory is private.
        """
        resp = await self._state.http.get_user_inventory(self.id64, app.id, app.context_id, language)
        return Inventory(state=self._state, data=resp, owner=self, app=app, language=language)

    async def friends(self) -> list[User]:
        """Fetch the list of the users friends."""
        friends = await self._state.http.get_friends(self.id64)
        return [self._state._store_user(friend) for friend in friends]

    async def apps(self, *, include_free: bool = True) -> list[UserApp]:
        r"""Fetches the :class:`~steam.App`\s the user owns.

        Parameters
        ----------
        include_free
            Whether to include free apps in the list. Defaults to ``True``.
        """
        apps = await self._state.fetch_user_apps(self.id64, include_free)
        return [UserApp(self._state, app) for app in apps]

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

    async def wishlist(self) -> list[WishlistApp]:
        r"""Get the :class:`.WishlistApp`\s the user has on their wishlist."""
        data = await self._state.http.get_wishlist(self.id64)
        return [WishlistApp(self._state, id=id, data=app_info) for id, app_info in data.items()]

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
            app=StatefulApp(self._state, id=badge.appid) if badge.appid else None,
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

    async def reviews(
        self,
        *,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[Review, None]:
        """An :term:`async iterator` for accessing a user's :class:`~steam.Review`\\s.

        Examples
        --------
        Usage:

        .. code-block:: python3

            async for review in user.reviews(limit=10):
                print(f"Author: {review.author} {'recommended' if review.recommend 'doesn\\'t recommend'} {review.app}")

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
        from .review import Review

        pages = 1
        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        yielded = 0

        async def get_reviews(page_number: int = 1) -> AsyncGenerator[Review, None]:
            nonlocal yielded, pages

            # ideally I'd like to find an actual api for these
            page = await self._state.http.get(
                URL.COMMUNITY / f"profiles/{self.id64}/recommended", params={"p": page_number}
            )
            soup = BeautifulSoup(page, HTML_PARSER)
            if pages == 1:
                *_, pages = [1] + [int(a["href"].removeprefix("?p=")) for a in soup.find_all("a", class_="pagelink")]
            app_ids = [
                int(URL_(review.find("div", class_="leftcol").a["href"]).parts[-1])
                for review in soup.find_all("div", class_="review_box_content")
            ]

            for review_ in await self._state.fetch_user_review(self.id64, app_ids):
                review = Review._from_proto(self._state, review_, self)
                if not after < review.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return

                yield review
                yielded += 1

        async for review in get_reviews():
            yield review

        for page in range(2, pages + 1):
            async for review in get_reviews(page):
                yield review

    async def fetch_review(self, app: App) -> Review:
        """Fetch this user's review for an app.

        Parameters
        ----------
        app
            The apps to fetch the reviews for.
        """
        (review,) = await self.fetch_reviews(app)
        return review

    async def fetch_reviews(self, *apps: App) -> list[Review]:
        """Fetch this user's review for apps.

        Parameters
        ----------
        apps
            The apps to fetch the reviews for.
        """
        from .review import Review

        reviews = await self._state.fetch_user_review(self.id64, (app.id for app in apps))
        return [Review._from_proto(self._state, review, self) for review in reviews]

    async def published_files(
        self,
        *,
        app: App | None = None,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        type: PublishedFileType = PublishedFileType.Community,
        language: Language | None = None,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[PublishedFile, None]:
        """An :term:`async iterator` for accessing a user's :class:`~steam.PublishedFile`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for file in user.published_files(limit=10):
                print("Author:", file.author, "Published:", file.name)

        All parameters are optional.

        Parameters
        ----------
        app
            The app to fetch published files in.
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
        from .published_file import PublishedFile

        before = before or DateTime.now()
        after = after or UNIX_EPOCH
        app_id = app.id if app else 0
        total = 30
        yielded = 0

        while yielded < total:
            page = yielded // 30 + 1
            msg = await self._state.fetch_user_published_files(self.id64, app_id, page, type, revision, language)
            if msg.total:
                total = msg.total

            for file in msg.publishedfiledetails:
                file = PublishedFile(self._state, file, self)
                if not after < file.created_at < before:
                    return
                if limit is not None and yielded >= limit:
                    return
                yield file
                yielded += 1

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
            self.app = NotImplemented
            self.state = NotImplemented
            self.flags = NotImplemented
            self.privacy_state = NotImplemented
            self._commentable = NotImplemented
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
        not_implemented("is_private")
        not_implemented("is_banned")

    async def fetch_post(self, id: int) -> Post:
        ...

    def posts(self) -> AsyncIterator[Post]:
        ...


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


@dataclass(slots=True)
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
    ) -> AsyncGenerator[M_co, None]:
        """An :term:`async iterator` for accessing a channel's :class:`steam.Message`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for message in channel.history(limit=10):
                print("Author:", message.author, "Said:", message.content)

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
