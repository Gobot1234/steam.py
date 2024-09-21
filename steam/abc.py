"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypedDict, cast, runtime_checkable

from bs4 import BeautifulSoup
from typing_extensions import Required, Self, TypeVar
from yarl import URL as URL_

from . import utils
from ._const import HTML_PARSER, MISSING, STEAM_EPOCH, UNIX_EPOCH, URL, VDF_BINARY_LOADS, ReadOnly
from .achievement import UserAppAchievement, UserAppStats
from .app import *
from .badge import FavouriteBadge, UserBadges
from .enums import *
from .errors import ConfirmationError, HTTPException, WSException
from .id import ID
from .models import Avatar, Ban
from .profile import *
from .protobufs import econ
from .reaction import Award, AwardReaction, Emoticon, MessageReaction, PartialMessageReaction, Sticker
from .trade import Asset, Inventory, Item, TradeOffer
from .types.id import ID64, AppID, AssetID, CommentID, ContextID, Intable, PostID, PublishedFileID
from .types.user import UserT
from .utils import DateTime, classproperty, parse_bb_code

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine, Sequence
    from ipaddress import IPv4Address

    from .clan import Clan
    from .comment import Comment
    from .game_server import GameServer
    from .group import Group
    from .invite import AppInvite
    from .media import Media
    from .message import UserMessage
    from .post import Post
    from .published_file import PublishedFile
    from .review import Review
    from .state import ConnectionState
    from .types import achievement
    from .user import ClientUser, User

__all__ = (
    "Message",
    "Channel",
    "PartialUser",
    "UserInventoryInfo",
)

MessageT = TypeVar("MessageT", bound="Message", default="Message", covariant=True)


class _CommentableKwargs(TypedDict, total=False):
    id64: Required[int]
    topic_id: int
    forum_id: int


class _CommentThreadType(IntEnum):
    # from https://github.com/SteamDatabase/Protobufs/blob/62702bd83148fff64945f20a09eaf8f250782829/steam/enums.proto#L386
    WorkshopAccountDeveloper = 2
    WorkshopAccount = 3
    PublishedFileDeveloper = 4
    PublishedFile = 5
    Test = 6
    Topic = 7
    Review = 8
    User = 10
    NewsPost = 11
    Clan = 12
    Announcement = 13
    Event = 14
    Post = 15
    UserReceivedNewGame = 16
    PublishedFileAnnouncement = 17
    ModeratorMessage = 18
    ClanCuratedApp = 19
    QAndASession = 20


class Commentable(Protocol):
    """A mixin that implements commenting functionality."""

    __slots__ = ()
    _state: ConnectionState

    @property
    @abc.abstractmethod
    def _commentable_kwargs(self) -> _CommentableKwargs:
        raise NotImplementedError

    @classproperty
    def _COMMENTABLE_TYPE(cls: type[Self]) -> _CommentThreadType:
        try:
            return _CommentThreadType[cls.__name__]
        except KeyError:
            raise AttributeError(f"{cls.__name__} is not a valid commentable type")

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if (
            cls.__dict__.get("_COMMENTABLE_TYPE") is Commentable.__dict__["_COMMENTABLE_TYPE"]
            and cls.__name__ != "BaseEvent"
        ):
            assert cls.__name__ in _CommentThreadType.__members__, f"{cls.__name__} is not a valid commentable type"

    async def fetch_comment(self, id: int, /) -> Comment[Self]:
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
            id=CommentID(comment.id),
            content=comment.content,
            created_at=DateTime.from_timestamp(comment.timestamp),
            author=await self._state._maybe_user(comment.author_id64),
            owner=self,
            reactions=[AwardReaction(self._state, reaction) for reaction in comment.reactions],
        )

    async def comment(self, content: str, /, *, subscribe: bool = True) -> Comment[Self, ClientUser]:
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
        """An :term:`asynchronous iterator` for accessing a comment section's :class:`~steam.Comment` objects.

        Examples
        --------

        Usage:

        .. code:: python3

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
                    id=CommentID(comment.id),
                    content=comment.content,
                    created_at=DateTime.from_timestamp(comment.timestamp),
                    reactions=[AwardReaction(self._state, reaction) for reaction in comment.reactions],
                    author=self._state.get_partial_user(comment.author_id64),
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


class _AwardableType(IntEnum):
    # from https://github.com/SteamDatabase/SteamTracking/blob/9ed188c12e9a3474416972873601185c6e0848c7/store.steampowered.com/public/javascript/applications/store/reviewaward.js#L453-L466
    # yes I know it's not great, I thought I had a better one but until I find that, suffer.
    Review = 1
    PublishedFile = 2
    Post = 3
    Topic = 4
    Comment = 5


IDT = TypeVar("IDT", bound=int, default=int, covariant=True)


class Awardable(Protocol[IDT]):  # type: ignore  # ReadOnly (PEP 705) should save this
    """A mixin that implements award functionality."""

    __slots__ = ()

    _state: ConnectionState
    id: ReadOnly[IDT]

    @classproperty
    def _AWARDABLE_TYPE(cls: type[Self]) -> _AwardableType:
        try:
            return _AwardableType[cls.__name__]
        except KeyError:
            raise AttributeError(f"{cls.__name__} is not a valid awardable type")

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        assert cls.__name__ in _AwardableType.__members__, f"{cls.__name__} is not a valid awardable type"

    async def award(self, award: Award, /) -> None:
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
class UserInventoryInfo(Generic[UserT]):
    user: UserT
    app: UserInventoryInfoApp
    total_count: int
    trade_permissions: str
    load_failed: bool
    store_vetted: bool
    owner_only: bool
    contexts: list[UserInventoryInfoContext]

    async def inventories(self) -> AsyncGenerator[Inventory[Item[UserT], UserT], None]:
        """An :term:`asynchronous iterator` for accessing a user's full inventory in an app."""
        for context in self.contexts:
            yield await self.user.inventory(App(id=self.app.id), context_id=context.id)


class PartialUser(ID[Literal[Type.Individual]], Commentable):
    def __init__(self, state: ConnectionState, id: Intable):
        super().__init__(id, type=Type.Individual)
        self._state = state

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.id64,
        }

    @classproperty
    def _COMMENTABLE_TYPE(cls: type[Self]) -> _CommentThreadType:  # type: ignore
        return _CommentThreadType.User

    def _send_message(self, content: str) -> Coroutine[Any, Any, UserMessage]:
        return self._state.send_user_message(self.id64, content)

    def _send_media(self, media: Media) -> Coroutine[Any, Any, None]:
        return self._state.http.send_user_media(self.id64, media)

    async def _send_trade(self, trade: TradeOffer[Asset[PartialUser], Asset[ClientUser], Any], **kwargs: Any) -> None:
        try:
            resp = await self._state.http.send_trade_offer(
                self,
                [item.to_dict() for item in trade.sending],
                [item.to_dict() for item in trade.receiving],
                trade.token,
                trade.message or "",
                **kwargs,
            )
        except HTTPException as e:
            if e.code == Result.Revoked and (
                any(item.owner != self for item in trade.receiving)
                or any(item.owner != self._state.user for item in trade.sending)
            ):
                if sys.version_info >= (3, 11):
                    e.add_note("You've probably sent an item isn't either in your inventory or the user's inventory")
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
                    break
                except ConfirmationError:
                    await asyncio.sleep(tries * 2)
            else:
                raise ConfirmationError("Failed to confirm trade offer")
            trade.state = TradeOfferState.Active

        # make sure the trade is updated before this function returns
        self._state._trades[trade.id] = cast(
            "TradeOffer[Item[User], Item[ClientUser], User]", trade
        )  # it gets upcast to this anyway after wait_for_trade
        await self._state.wait_for_trade(trade.id)
        self._state.dispatch("trade", trade)

    @property
    def trade_url(self) -> URL_:
        """The trade url of the user."""
        return URL.COMMUNITY / "tradeoffer/new/" % {"partner": str(self.id)}

    async def inventory_info(self) -> list[UserInventoryInfo[Self]]:
        """Fetch the inventory info of the user.

        .. source:: UserInventoryInfo
        """
        data = await self._state.http.get_user_inventory_info(self.id64)

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
            for info in data
        ]

    async def inventory(
        self, app: App, /, *, context_id: int | None = None, language: Language | None = None
    ) -> Inventory[Item[Self], Self]:
        """Fetch a user's :class:`~steam.Inventory` for trading.

        Parameters
        -----------
        app
            The app to fetch the inventory for.
        context_id
            The context ID for the inventory normally ``2``.
        language
            The language to fetch the inventory in. If ``None`` will default to the current language.

        Raises
        ------
        :exc:`~steam.Forbidden`
            The user's inventory is private.
        """
        if context_id is None:
            context_id = 6 if app.name == "Steam" and context_id is None else 2
        context_id = ContextID(context_id)
        resp = econ.GetInventoryItemsWithDescriptionsResponse().from_dict(
            await self._state.http.get_user_inventory(self.id64, app.id, context_id, language)
        )
        return Inventory(state=self._state, proto=resp, owner=self, app=app, context_id=context_id, language=language)

    async def inventories(self) -> AsyncGenerator[Inventory[Item[Self], Self], None]:
        """Fetches all the inventories a user has."""
        for inventory_info in await self.inventory_info():
            async for inventory in inventory_info.inventories():
                yield inventory

    async def friends(self) -> Sequence[User]:
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

    async def recently_played(self) -> list[UserRecentlyPlayedApp]:
        """Fetches the apps the user has recently played."""
        apps = await self._state.http.get_user_recently_played_apps(self.id64)
        return [UserRecentlyPlayedApp(self._state, app) for app in apps]

    async def app_stats(self, app: App, /, *, language: Language | None = None) -> UserAppStats:
        """Fetch the stats for the user in the app.

        Parameters
        ----------
        language
            The language to fetch the stats in. If ``None`` will default to the current language.
        """
        msg = await self._state.fetch_user_app_stats(self.id64, app.id)
        schema = VDF_BINARY_LOADS(msg.schema)
        data = cast("achievement.UserAppStats", schema[str(app.id)])
        return UserAppStats(self._state, app, msg, data, language or self._state.language)

    # TODO find a better way to do this
    async def achievements(self, app: App, /, *, language: Language | None = None) -> list[UserAppAchievement]:
        """Fetch the achievements for the user in the app.

        Parameters
        ----------
        language
            The language to fetch the stats in. If ``None`` will default to the current language.
        """
        stats = await self.app_stats(app, language=language)
        return stats.achievements

    async def wishlist(self) -> list[WishlistApp]:
        r"""Get the :class:`.WishlistApp`\s the user has on their wishlist."""
        return [
            WishlistApp(self._state, id=app_id, data=data)
            async for app_id, data in self._state.http.get_user_wishlist(self.id64)
        ]

    async def clans(self, *, auto_chunk: bool = False) -> list[Clan]:
        r"""Fetches a list of :class:`~steam.Clan`\s the user is in.

        Parameters
        ----------
        auto_chunk
            Whether to automatically chunk the clans that are fetched. Defaults to ``False``.
        """

        async def getter(id64: ID64) -> Clan:
            try:
                return await self._state.fetch_clan(id64, maybe_chunk=auto_chunk)
            except WSException as exc:
                if exc.code == Result.RateLimitExceeded:
                    await asyncio.sleep(20)
                    return await getter(id64)
                raise

        return await asyncio.gather(*map(getter, await self._state.http.get_user_clans(self.id64)))

    async def bans(self) -> Ban:
        r"""Fetches the user's :class:`.Ban`\s."""
        (ban,) = await self._state.http.get_user_bans(self.id64)
        return Ban(ban)

    async def is_banned(self) -> bool:
        """Specifies if the user is banned from any part of Steam.

        Shorthand for:

        .. code:: python

            bans = await user.bans()
            bans.is_banned()
        """
        (ban,) = await self._state.http.get_user_bans(self.id64)
        return any((ban["community_banned"], ban["economy_ban"] != "none", ban["vac_banned"]))

    async def level(self) -> int:
        """Fetches the user's level."""
        levels = await self._state.fetch_user_levels(self.id)
        return levels[self.id]

    async def badges(self) -> UserBadges[Self]:
        r"""Fetches the user's :class:`.UserBadges`\s."""
        data = await self._state.http.get_user_badges(self.id64)
        return UserBadges(self._state, self, data=data)

    async def favourite_badge(self) -> FavouriteBadge[PartialApp | Literal[STEAM]] | None:
        """The user's favourite badge."""
        badge = await self._state.fetch_user_favourite_badge(self.id64)
        if not badge.has_favorite_badge:
            return

        return FavouriteBadge(
            self._state,
            id=badge.badgeid,
            app=PartialApp(self._state, id=badge.appid) if badge.appid else STEAM,
            owner=self,
            level=badge.level,
            community_item_id=AssetID(badge.communityitemid),
            type=badge.item_type,
            border_colour=badge.border_color,
        )

    async def equipped_profile_items(self, *, language: Language | None = None) -> EquippedProfileItems[Self]:
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

    async def profile_customisation_info(self) -> ProfileCustomisation[Self]:
        """Fetch a user's profile customisation information."""
        info = await self._state.fetch_user_profile_customisation(self.id64)
        return ProfileCustomisation(self._state, self, info)

    async def profile(self, *, language: Language | None = None) -> Profile[Self]:
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
        """An :term:`asynchronous iterator` for accessing a user's :class:`~steam.Review`\\s.

        Examples
        --------
        Usage:

        .. code:: python

            async for review in user.reviews(limit=10):
                recommended = "recommended" if review.recommend else "doesn't recommend"
                print(f"Author: {review.author} {recommended} {review.app}")

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
        from .user import ClientUser, User

        pages = 1
        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        yielded = 0
        if type(self) is PartialUser:
            self = await self._state._maybe_user(self.id64)
        assert isinstance(self, (User, ClientUser))

        async def get_reviews(page_number: int = 1) -> AsyncGenerator[Review, None]:
            nonlocal yielded, pages

            # ideally I'd like to find an actual api for these
            page = await self._state.http.get(f"{self.community_url}/recommended", params={"p": page_number})
            soup = BeautifulSoup(page, HTML_PARSER)
            if pages == 1:
                *_, pages = [1] + [int(a["href"].removeprefix("?p=")) for a in soup.find_all("a", class_="pagelink")]
            app_ids = [
                AppID(int(URL_(review.find("div", class_="leftcol").a["href"]).parts[-1]))
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
        from .user import ClientUser, User

        reviews = await self._state.fetch_user_reviews(self.id64, (app.id for app in apps))
        if type(self) is PartialUser:
            # this kinda sucks but it's the best thing I can think of until intersections are added
            self = await self._state.fetch_user(self.id64)
        assert isinstance(self, (User, ClientUser))
        return [Review._from_proto(self._state, review, self) for review in reviews]

    async def fetch_published_file(
        self,
        id: int,
        /,
        *,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
    ) -> PublishedFile[Self] | None:
        """Fetch a published file by its id.

        Parameters
        ----------
        id
            The id of the published file to fetch.
        revision
            The desired revision of the published file to fetch.
        language
            The language to fetch the published file in. If ``None``, the current language is used.
        """
        (file,) = await self._state.fetch_published_files_with_author((PublishedFileID(id),), self, revision, language)
        return file

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
    ) -> AsyncGenerator[PublishedFile[Self], None]:
        """An :term:`asynchronous iterator` for accessing a user's :class:`~steam.PublishedFile`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
        app_id = app.id if app else AppID(0)
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

    async def fetch_post(self, id: int, /) -> Post[Self]:
        """Fetch a post by its id.

        Parameters
        ----------
        id
            The id of the post to fetch.
        """
        from .post import Post

        post = await self._state.fetch_user_post(self.id64, PostID(id))
        return Post(
            self._state,
            PostID(post.postid),
            post.status_text,
            self,
            PartialApp(self._state, id=post.appid) if post.appid else None,
        )

    async def invite_to(self, app: App) -> AppInvite: ...

    def is_friend(self) -> bool:
        """Whether the user is in the :class:`ClientUser`'s friends."""
        return self.id in self._state.user._friends


class BaseUser(PartialUser):
    """An ABC that details the common operations on a Steam user.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClientUser`
        - :class:`~steam.Friend`
        - :class:`~steam.Member`

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.
    """

    __slots__ = ()

    name: str
    """The user's username."""
    last_logoff: datetime | None
    """The last time the user logged off steam. Could be None (e.g. if they are currently online)."""
    last_logon: datetime | None
    """The last time the user logged into steam."""
    last_seen_online: datetime | None
    """The last time the user was seen online."""
    app: PartialApp[str] | None
    """The app the user is currently in. Is ``None`` if the user isn't in an app."""
    state: PersonaState
    """The current persona state of the account (e.g. LookingToTrade)."""
    flags: PersonaStateFlag
    """The persona state flags of the account."""
    rich_presence: dict[str, str] | None
    """The user's rich presence."""
    game_server_ip: IPv4Address | None
    """The IP address of the game server the user is currently playing on."""
    game_server_port: int | None
    """The port of the game server the user is currently playing on."""
    _avatar_sha: bytes
    _state: ConnectionState

    def __repr__(self) -> str:
        attrs = ("name", "state", "id", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    @property
    def mention(self) -> str:
        """The string used to mention the user in chat."""
        return f"[mention={self.id}]@{self.name}[/mention]"

    @property
    def avatar(self) -> Avatar:
        """The user's avatar."""
        return Avatar(self._state, self._avatar_sha)

    async def server(self) -> GameServer:
        """Fetch the game server this user is currently playing on."""
        if self.game_server_ip is None:
            raise ValueError("User is not playing on a game server")
        server = await self._state.client.fetch_server(ip=self.game_server_ip, port=self.game_server_port)
        assert server is not None
        return server


@runtime_checkable
class Messageable(Protocol[MessageT]):
    """An ABC that details the common operations on a Steam message.
    The following classes implement this ABC:

        - :class:`~steam.User`
        - :class:`~steam.ClanChannel`
        - :class:`~steam.GroupChannel`
        - :class:`~steam.UserChannel`
    """

    __slots__ = ()
    _state: ConnectionState

    @abc.abstractmethod
    def _send_message(self, content: str) -> Coroutine[Any, Any, MessageT]:
        raise NotImplementedError

    @abc.abstractmethod
    def _send_media(self, media: Media) -> Coroutine[Any, Any, None]:
        raise NotImplementedError

    async def send(self, content: Any = MISSING, /, *, media: Media | None = None) -> MessageT | None:
        """Send a message to a certain destination.

        Parameters
        ----------
        content
            The content of the message to send.
        media
            The media to send to the user.

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
        message = None if content is MISSING else await self._send_message(str(content))
        if media is not None:
            await self._send_media(media)

        return message

    @abc.abstractmethod
    async def history(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[MessageT, None]:
        """An :term:`asynchronous iterator` for accessing a channel's :class:`steam.Message`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
        yield

    async def fetch_message(self, id: int, /) -> MessageT | None:
        """Fetch a message by its :attr:`Message.id`."""
        created_at = STEAM_EPOCH + timedelta(seconds=id >> 32)
        ordinal = id & 0xFFFF
        return await utils.get(
            self.history(
                before=created_at + timedelta(seconds=1),
                after=created_at - timedelta(seconds=1),
            ),
            ordinal=ordinal,
            created_at=created_at,
        )


ClanT = TypeVar("ClanT", bound="Clan | None", default="Clan | None", covariant=True)
GroupT = TypeVar("GroupT", bound="Group | None", default="Group | None", covariant=True)


@dataclass(slots=True)
class Channel(Messageable[MessageT], Generic[MessageT, ClanT, GroupT]):
    _state: ConnectionState
    clan: ClanT = cast(ClanT, None)
    """The clan this channel belongs to."""
    group: GroupT = cast(GroupT, None)
    """The group this channel belongs to."""


def _clean_up_content(content: str) -> str:  # steam does weird stuff with content
    return content.replace(r"\[", "[").replace("\\\\", "\\")


ChannelT = TypeVar("ChannelT", bound=Channel, default=Channel, covariant=True)


class Message(Generic[UserT, ChannelT], metaclass=abc.ABCMeta):
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
        "reactions",
        "partial_reactions",
        "_state",
    )

    author: UserT
    """The message's author."""
    created_at: datetime
    """The time this message was sent at."""

    def __init__(self, channel: ChannelT, proto: Any):
        self._state: ConnectionState = channel._state
        self.channel = channel
        """The channel the message was sent in."""
        self.group = channel.group
        """The group the message was sent in. ``None`` if the message wasn't sent in a :class:`~steam.Group`."""
        self.clan = channel.clan
        """The clan the message was sent in. ``None`` if the message wasn't sent in a :class:`~steam.Clan`."""
        self.content = parse_bb_code(proto.message)
        """The message's content.

        Note
        ----
        This is **not** what you will see in the steam client see :attr:`clean_content` for that.
        """
        self.ordinal: int = proto.ordinal
        """A per-channel incremented integer up to ``1000`` for every message sent in a second window."""
        self.clean_content: str = getattr(proto, "message_no_bbcode", "") or _clean_up_content(self.content)
        """The message's clean content without BBCode."""
        self.reactions: list[MessageReaction] = []
        """The message's reactions."""
        self.partial_reactions: list[PartialMessageReaction] = []
        """The message's partial reactions."""

    def __repr__(self) -> str:
        attrs = ("author", "id", "channel")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self.channel == other.channel and self.id == other.id

    def __hash__(self) -> int:
        return hash((self.channel, self.id))

    @classmethod
    @abc.abstractmethod
    def _from_history(cls, channel: ChannelT, proto: Any) -> Self:  # type: ignore  # it's a constructor so covariance is fine
        raise NotImplementedError

    @property
    def id(self) -> int:
        """A unique identifier for every message sent in a channel.

        Note
        ----
        This is **not** something Steam provides, this is meant to be a simple way to compare messages.
        """
        # a u64 "snowflake-esk" id measuring of the number of seconds passed since Steam's EPOCH and then the
        # "sequence"/ordinal of the message.
        return int((self.created_at - STEAM_EPOCH).total_seconds()) << 32 | self.ordinal

    @abc.abstractmethod
    async def _react(self, emoticon: Emoticon | Sticker, add: bool) -> None:
        raise NotImplementedError

    async def add_emoticon(self, emoticon: Emoticon, /) -> None:
        """Adds an emoticon to this message.

        Parameters
        ----------
        emoticon
            The emoticon to add to this message.
        """
        await self._react(emoticon, True)

    async def remove_emoticon(self, emoticon: Emoticon, /) -> None:
        """Removes an emoticon from this message.

        Parameters
        ----------
        emoticon
            The emoticon to remove from this message.
        """
        await self._react(emoticon, False)

    async def add_sticker(self, sticker: Sticker, /) -> None:
        """Adds a sticker to this message.

        Parameters
        ----------
        sticker
            The sticker to add to this message.
        """
        await self._react(sticker, True)

    async def remove_sticker(self, sticker: Sticker, /) -> None:
        """Adds a sticker to this message.

        Parameters
        ----------
        sticker
            The sticker to remove from this message.
        """
        await self._react(sticker, False)

    @abc.abstractmethod
    async def ack(self) -> None:
        """Acknowledge this message.

        Note
        ----
        This will acknowledge any messages sent before this message
        """
        raise NotImplementedError()
