"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
import asyncio
import re
from collections.abc import AsyncGenerator, Coroutine
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, TypedDict, TypeVar, runtime_checkable

from bs4 import BeautifulSoup
from typing_extensions import Required, Self
from yarl import URL as URL_

from ._const import HTML_PARSER, JSON_LOADS, MISSING, STEAM_EPOCH, UNIX_EPOCH, URL
from .app import App, PartialApp, UserApp, UserInventoryInfoApp, UserInventoryInfoContext, WishlistApp
from .badge import FavouriteBadge, UserBadges
from .enums import *
from .errors import WSException
from .game_server import GameServer
from .id import ID
from .models import Avatar, Ban
from .profile import *
from .reaction import Award, AwardReaction, Emoticon, MessageReaction, PartialMessageReaction, Sticker
from .trade import Inventory
from .types.id import ContextID
from .utils import DateTime, cached_slot_property, classproperty

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
    topic_id: int
    forum_id: int


class _CommentableThreadType(IntEnum):
    # these just came from bashing the API and seeing what works, although they can now be reliably determined using
    # ConnectionState.fetch_notifications() and observing body_data["type"] if it's a comment.
    # AFAIK there aren't any more Commentable types
    PublishedFile = 5
    Topic = 7
    Review = 8
    User = 10
    Clan = 12
    Announcement = 13
    Event = 14
    Post = 15


class Commentable(Protocol):
    """A mixin that implements commenting functionality."""

    __slots__ = ()
    _state: ConnectionState

    @property
    @abc.abstractmethod
    def _commentable_kwargs(self) -> _CommentableKwargs:
        raise NotImplementedError

    @classproperty
    def _commentable_type(cls: type[Self]) -> _CommentableThreadType:
        return _CommentableThreadType[cls.__name__]

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
                    author=ID(comment.author_id64),
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

        comments = await get_comments(min(limit or 100, 100))
        for comment, author in zip(
            comments, await self._state._maybe_users(comment.author.id64 for comment in comments)
        ):
            comment.author = author
            yield comment

        assert count is not None
        while count > 0:
            comments = await get_comments(min(limit or 100, 100))
            for comment, author in zip(
                comments, await self._state._maybe_users(comment.author.id64 for comment in comments)
            ):
                comment.author = author
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


@dataclass(slots=True)
class UserInventoryInfo:
    user: BaseUser
    app: UserInventoryInfoApp
    total_count: int
    trade_permissions: str
    load_failed: bool
    store_vetted: bool
    owner_only: bool
    contexts: list[UserInventoryInfoContext]

    async def all_inventories(self) -> AsyncGenerator[Inventory, None]:
        """An :term:`async iterator` for accessing a user's full inventory in an app."""
        for context in self.contexts:
            yield await self.user.inventory(App(id=self.app.id, context_id=context.id))


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
    last_logoff
        The last time the user logged into steam. Could be None (e.g. if they are currently online).
    flags
        The persona state flags of the account.
    rich_presence
        The user's rich presence.
    """

    __slots__ = ()

    name: str
    last_logoff: datetime | None
    last_logon: datetime | None
    last_seen_online: datetime | None
    app: PartialApp | None
    state: PersonaState | None
    flags: PersonaStateFlag | None
    rich_presence: dict[str, str] | None
    game_server_ip: IPv4Address | IPv6Address | None
    game_server_port: int | None
    _avatar_sha: bytes
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
        }

    @property
    def mention(self) -> str:
        """The string used to mention the user in chat."""
        return f"[mention={self.id}]@{self.name}[/mention]"

    @property
    def avatar(self) -> Avatar:
        return Avatar(self._state, self._avatar_sha)

    async def server(self) -> GameServer:
        """Fetch the game server this user is currently playing on."""
        if self.game_server_ip is None:
            raise ValueError("User is not playing on a game server")
        server = await self._state.client.fetch_server(
            ip=self.game_server_ip, port=self.game_server_port if self.game_server_port is not None else MISSING
        )
        assert server is not None
        return server

    async def inventory_info(self) -> list[UserInventoryInfo]:
        """Fetch the inventory info of the user.

        Returns
        -------
        UserInventoryInfo is a dataclass defined as:

        .. source:: UserInventoryInfo
        """
        resp = await self._state.http.get(URL.COMMUNITY / f"profiles/{self.id64}/inventory")
        soup = BeautifulSoup(resp, "html.parser")
        for script in soup.find_all("script", type="text/javascript"):
            if match := re.search(r"var g_rgAppContextData\s*=\s*(?P<json>{.*?});\s*", script.text):
                break
        else:
            raise ValueError("Could not find inventory info")

        app_context_data = JSON_LOADS(match["json"])

        return [
            UserInventoryInfo(
                user=self,
                app=UserInventoryInfoApp(
                    self._state,
                    id=info["appid"],
                    name=info["name"],
                    inventory_logo_url=info["inventory_logo"],
                    icon_url=info["icon"],
                ),
                total_count=info["asset_count"],
                trade_permissions=info["trade_permissions"],
                load_failed=bool(info["load_failed"]),
                store_vetted=bool(info["store_vetted"]),
                owner_only=info["owner_only"],
                contexts=[
                    UserInventoryInfoContext(ContextID(ctx["id"]), ctx["name"], ctx["asset_count"])
                    for ctx in info["rgContexts"].values()
                ],
            )
            for info in app_context_data.values()
        ]

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
        resp = await self._state.fetch_user_inventory(self.id64, app.id, app.context_id, language)
        return Inventory(state=self._state, data=resp, owner=self, app=app, language=language)

    async def friends(self) -> list[User | ID]:
        """Fetch the list of the users friends."""
        friends = await self._state.http.get_friends_ids(self.id64)
        return await self._state._maybe_users(friends)

    async def apps(self, *, include_free: bool = True) -> list[UserApp]:
        r"""Fetches the :class:`~steam.App`\s the user owns.

        Parameters
        ----------
        include_free
            Whether to include free apps in the list. Defaults to ``True``.
        """
        apps = await self._state.fetch_user_apps(self.id64, include_free)
        return [UserApp(self._state, app) for app in apps]

    async def wishlist(self) -> list[WishlistApp]:
        r"""Get the :class:`.WishlistApp`\s the user has on their wishlist."""
        data = await self._state.http.get_wishlist(self.id64)
        return [WishlistApp(self._state, id=id, data=app_info) for id, app_info in data.items()]

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

    async def is_banned(self) -> bool:
        """Specifies if the user is banned from any part of Steam.

        Shorthand for:

        .. code-block:: python3

            bans = await user.bans()
            bans.is_banned()
        """
        bans = await self.bans()
        return bans.is_banned()

    async def level(self) -> int:
        """Fetches the user's level."""
        badges = await self.badges()
        return badges.level

    async def badges(self) -> UserBadges:
        r"""Fetches the user's :class:`.UserBadges`\s."""
        resp = await self._state.http.get_user_badges(self.id64)
        return UserBadges(self._state, self, data=resp["response"])

    async def favourite_badge(self) -> FavouriteBadge | None:
        """The user's favourite badge."""
        badge = await self._state.fetch_user_favourite_badge(self.id64)
        if not badge.has_favorite_badge:
            return

        return FavouriteBadge(
            id=badge.badgeid,
            community_item_id=badge.communityitemid,
            type=badge.item_type,
            border_colour=badge.border_color,
            app=PartialApp(self._state, id=badge.appid) if badge.appid else None,
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

    async def profile_customisation_info(self) -> ProfileCustomisation:
        """Fetch a user's profile customisation information."""
        info = await self._state.fetch_user_profile_customisation(self.id64)
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
                self.profile_customisation_info(),
            )
        )

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

            for review_ in await self._state.fetch_user_reviews(self.id64, app_ids):
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

        reviews = await self._state.fetch_user_reviews(self.id64, (app.id for app in apps))
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
