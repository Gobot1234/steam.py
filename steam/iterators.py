"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import itertools
import math
import re
from collections.abc import AsyncGenerator, Callable, Coroutine, Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from bs4 import BeautifulSoup
from typing_extensions import ClassVar, Self, TypeAlias
from yarl import URL as URL_

from . import utils
from ._const import HTML_PARSER, URL
from .enums import EventType, Language, PublishedFileQueryFileType, PublishedFileRevision, PublishedFileType
from .utils import DateTime

if TYPE_CHECKING:
    from .abc import Authors, BaseUser, Commentable, Message
    from .channel import DMChannel, UserMessage
    from .chat import Chat, ChatMessage
    from .clan import Clan
    from .comment import Comment
    from .event import Announcement, Event
    from .game import Game, StatefulGame
    from .group import Group
    from .manifest import Manifest
    from .protobufs import friend_messages
    from .published_file import PublishedFile
    from .review import Review
    from .state import ConnectionState
    from .trade import TradeOffer
    from .user import User

T = TypeVar("T")
TT = TypeVar("TT")
CommentableT = TypeVar("CommentableT", bound="Commentable")
M = TypeVar("M", bound="Message", covariant=True)

MaybeCoro: TypeAlias = "Callable[[T], bool | Coroutine[Any, Any, bool]]"
UNIX_EPOCH = DateTime.from_timestamp(0)


class AsyncIterator(Generic[T]):
    """A class from which async iterators (see :pep:`525`) can ben easily derived.

    .. container:: operations

        .. describe:: async for y in x

            Iterates over the contents of the async iterator.

    Attributes
    ----------
    before
        When to find objects before.
    after
        When to find objects after.
    limit
        The maximum number of elements to be yielded.
    """

    def __init__(
        self,
        state: ConnectionState,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ):
        self._state = state
        self.before = before or DateTime.now()
        self.after = after or UNIX_EPOCH
        self._is_filled = False
        self.limit = limit
        self._fill = self.fill()
        self._seen = 0

    async def _fill_queue_users(
        self,
        iterable: Iterable[T],
        attributes: tuple[str, ...] = ("author",),
        *,
        user_attribute_name: str | None = None,
    ) -> None:
        user_attribute_name = user_attribute_name or attributes[0]
        users = await self._state._maybe_users(getattr(element, user_attribute_name) for element in iterable)
        for user, element in itertools.product(
            users,
            iterable,
        ):
            for attribute in attributes:
                if getattr(element, attribute, None) == user:
                    setattr(element, attribute, user)

    async def get(self, **attrs: Any) -> T | None:
        """A helper function which is similar to :func:`~steam.utils.get` except it runs over the async iterator.

        This is roughly equivalent to:

        .. code-block:: python3


            elements = await async_iterator.flatten()
            element = steam.utils.get(elements, name="Item")

        Example
        -------
        Getting the last comment from a user named 'Dave' or None:

        .. code-block:: python3

            comment = await user.comments().get(author__name="Dave")

        Parameters
        ----------
        attrs
            Keyword arguments that denote attributes to match.

        Returns
        -------
        The first element from the ``iterable`` which matches all the traits passed in ``attrs`` or ``None`` if no
        matching element was found.
        """

        def predicate(elem: T) -> bool:
            for attr, val in attrs.items():
                nested = attr.split("__")
                obj = elem
                for attribute in nested:
                    obj = getattr(obj, attribute)

                if obj != val:
                    return False
            return True

        return await self.find(predicate)

    async def find(self, predicate: MaybeCoro[T]) -> T | None:
        """A helper function which is similar to :func:`~steam.utils.find` except it runs over the async iterator.
        However, unlike :func:`~steam.utils.find`, the predicate provided can be a |coroutine_link|_.

        This is roughly equivalent to:

        .. code-block:: python3

            elements = await async_iterator.flatten()
            element = steam.utils.find(elements, lambda e: e.name == "Item")

        Example
        -------
        Getting the last trade with a message or None:

        .. code-block:: python3

            def predicate(trade: steam.TradeOffer) -> bool:
                return trade.message is not None


            trade = await client.trade_history().find(predicate)

        Parameters
        ----------
        predicate
            A callable/coroutine that returns a boolean.

        Returns
        -------
        The first element from the iterator for which the ``predicate`` returns ``True`` or ``None`` if no matching
        element was found.
        """
        async for elem in self:
            ret = await utils.maybe_coroutine(predicate, elem)
            if ret:
                return elem

    async def flatten(self) -> list[T]:
        """A helper function that iterates over the :class:`AsyncIterator` returning a list of all the elements in the
        iterator.

        This is equivalent to:

        .. code-block:: python3

            elements = [element async for element in async_iterator]
        """
        return [element async for element in self]

    def filter(self, predicate: Callable[[T], bool]) -> FilteredIterator[T]:
        """Filter members of the async iterator according to a predicate. This function acts similarly to :func:`filter`.

        Examples
        --------
        .. code-block:: python3

            for dave in async_iterator.filter(lambda x: x.name == "Dave"):
                ...  # the element now has to have a name of Dave.

        Parameters
        ----------
        predicate
            The predicate to filter elements through.
        """
        return FilteredIterator(predicate, self)

    def map(self, func: Callable[[TT], Any]) -> MappedIterator[T, TT]:
        """Map the elements of the async iterator through a function. This function acts similarly to :func:`map`.

        Examples
        --------
        .. code-block:: python3

            for name in async_iterator.map(lambda x: x.name):
                ...  # name is now the iterators element's name.

        Parameters
        ----------
        func
            The function to map the elements through.
        """
        return MappedIterator(func, self)

    def __aiter__(self) -> Self:
        return self

    def __anext__(self) -> Coroutine[None, None, T]:
        self._seen += 1
        if self.limit and self._seen > self.limit:
            raise StopAsyncIteration
        return self._fill.__anext__()  # type: ignore  # this is typed wrong

    async def next(self) -> T:
        """Advances the iterator by one, if possible.

        Raises
        ------
        :exc:`StopAsyncIteration`
            There are no more elements in the iterator.
        """
        return await self.__anext__()

    async def fill(self) -> AsyncGenerator[T, None]:
        raise NotImplementedError
        yield


class FilteredIterator(AsyncIterator[T]):
    def __init__(self, predicate: MaybeCoro[T], async_iterator: AsyncIterator[T]):
        self.predicate = predicate
        self.iterator = async_iterator

    async def next(self) -> T:
        while True:
            item = await self.iterator.next()
            if await utils.maybe_coroutine(self.predicate, item):
                return item


class MappedIterator(AsyncIterator[TT], Generic[T, TT]):
    def __init__(self, map_func: Callable[[Any], TT | Coroutine[Any, Any, TT]], async_iterator: AsyncIterator[T]):
        self.map_func = map_func
        self.iterator = async_iterator

    async def next(self) -> TT:
        item = await self.iterator.next()
        return await utils.maybe_coroutine(self.map_func, item)


class CommentsIterator(AsyncIterator["Comment[CommentableT]"]):
    def __init__(
        self,
        owner: CommentableT,
        oldest_first: bool,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        self.owner = owner
        self.oldest_first = oldest_first
        super().__init__(state, limit, before, after)

    async def fill(self) -> AsyncGenerator["Comment[CommentableT]", None]:
        from .comment import Comment
        from .reaction import AwardReaction

        after = self.after
        before = self.before
        count: int | None = None
        total_count = 0

        async def get_comments(chunk: int) -> list[Comment[CommentableT]]:
            nonlocal after, before, count, total_count

            starting_from = total_count - count if total_count and count else 0
            proto = await self._state.fetch_comments(self.owner, chunk, starting_from, self.oldest_first)

            if count is None:
                total_count = count = proto.total_count

            comments: list[Comment[CommentableT]] = []
            comment = None
            for comment in proto.comments:
                comment = Comment(
                    self._state,
                    id=comment.id,
                    content=comment.content,
                    created_at=DateTime.from_timestamp(comment.timestamp),
                    reactions=[AwardReaction(self._state, reaction) for reaction in comment.reactions],
                    author=comment.author_id64,  # type: ignore
                    owner=self.owner,
                )
                if self.after < comment.created_at < self.before:
                    comments.append(comment)
                else:
                    break

            await self._fill_queue_users(comments)
            count -= len(comments)
            return comments

        for comment in await get_comments(min(self.limit or 100, 100)):
            yield comment

        assert count is not None
        while count > 0:
            for comment in await get_comments(min(count, 100)):
                yield comment


class TradesIterator(AsyncIterator["TradeOffer"]):
    def __init__(
        self,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
        language: Language | None,
    ):
        super().__init__(state, limit, before, after)
        self.language = language

    async def fill(self) -> AsyncGenerator[TradeOffer, None]:
        from .trade import TradeOffer

        total = 100
        previous_time = 0
        after_timestamp = self.after.timestamp()
        before_timestamp = self.before.timestamp()

        async def get_trades(page: int = 100) -> list[TradeOffer]:
            nonlocal total, previous_time
            resp = await self._state.http.get_trade_history(page, previous_time, self.language)
            data = resp["response"]
            if total is None:
                total = data.get("total_trades", 0)
            if not total:
                return []

            trades: list[TradeOffer] = []
            descriptions = data.get("descriptions", ())
            trade = None
            for trade in data.get("trades", []):
                if not after_timestamp < trade["time_init"] < before_timestamp:
                    break
                for item in descriptions:
                    for asset in trade.get("assets_received", []):
                        if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                            asset.update(item)
                    for asset in trade.get("assets_given", []):
                        if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                            asset.update(item)

                trades.append(TradeOffer._from_history(state=self._state, data=trade))

            assert trade is not None
            previous_time = trade["time_init"]
            await self._fill_queue_users(trades, ("partner",))
            return trades

        for trade in await get_trades():
            for item in trade.items_to_receive:
                item.owner = trade.partner
            yield trade

        if total < 100:
            for page in range(200, math.ceil((total + 100) / 100) * 100, 100):
                for trade in await get_trades(page):
                    for item in trade.items_to_receive:
                        item.owner = trade.partner
                    yield trade


class DMChannelHistoryIterator(AsyncIterator["UserMessage"]):
    def __init__(
        self,
        channel: DMChannel,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        super().__init__(state, limit, before, after)
        self.channel = channel
        self.participant = channel.participant

    async def fill(self) -> AsyncGenerator[UserMessage, None]:
        from .message import Message, UserMessage
        from .reaction import Emoticon, MessageReaction, Sticker

        after_timestamp = int(self.after.timestamp())
        before_timestamp = int(self.before.timestamp())

        last_message_timestamp = before_timestamp
        ordinal = 0

        while True:
            resp = await self._state.fetch_user_history(
                self.participant.id64, start=after_timestamp, last=last_message_timestamp, start_ordinal=ordinal
            )

            message: friend_messages.GetRecentMessagesResponseFriendMessage | None = None

            for message in resp.messages:
                new_message = UserMessage.__new__(UserMessage)
                new_message.created_at = DateTime.from_timestamp(message.timestamp)
                if not self.after < new_message.created_at < self.before:
                    return

                Message.__init__(new_message, channel=self.channel, proto=message)
                new_message.author = self.participant if message.accountid == self.participant.id else self._state.user
                emoticon_reactions = [
                    MessageReaction(
                        self._state,
                        new_message,
                        Emoticon(self._state, r.reaction),
                        None,
                        self.participant if reactor == self.participant.id else self._state.user,
                    )
                    for r in message.reactions
                    if r.reaction_type == 1
                    for reactor in r.reactors
                ]
                sticker_reactions = [
                    MessageReaction(
                        self._state,
                        new_message,
                        None,
                        Sticker(self._state, r.reaction),
                        self.participant if reactor == self.participant.id else self._state.user,
                    )
                    for r in message.reactions
                    if r.reaction_type == 2
                    for reactor in r.reactors
                ]
                new_message.reactions = emoticon_reactions + sticker_reactions

                yield new_message

            if message is None:
                return

            last_message_timestamp = message.timestamp
            ordinal = message.ordinal

            if not resp.more_available:
                return


ChatMessageT = TypeVar("ChatMessageT", bound="ChatMessage", covariant=True)
ChatT = TypeVar("ChatT", bound="Chat[Any]", covariant=True)


class ChatHistoryIterator(AsyncIterator[ChatMessageT], Generic[ChatMessageT, ChatT]):
    def __init__(
        self,
        channel: ChatT,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        super().__init__(state, limit, before, after)
        self.channel = channel
        self.group: Group | Clan = channel.group or channel.clan  # type: ignore

    async def fill(self) -> AsyncGenerator[ChatMessageT, None]:
        from .abc import SteamID
        from .message import Message
        from .reaction import Emoticon, PartialMessageReaction, Sticker

        after_timestamp = int(self.after.timestamp())
        before_timestamp = int(self.before.timestamp())
        last_message_timestamp = before_timestamp
        last_ordinal: int = getattr(self.channel.last_message, "ordinal", 0)
        message_cls: type[ChatMessageT] = self.channel._type_args[0]

        while True:
            resp = await self._state.fetch_group_history(
                *self.channel._location, start=after_timestamp, last=last_message_timestamp, last_ordinal=last_ordinal
            )
            message = None
            messages: list[ChatMessageT] = []

            for message in resp.messages:
                new_message = message_cls.__new__(message_cls)
                Message.__init__(new_message, channel=self.channel, proto=message)
                new_message.created_at = DateTime.from_timestamp(message.server_timestamp)
                if not self.after < new_message.created_at < self.before:
                    return

                new_message.author = SteamID(message.sender)
                emoticon_reactions = [
                    PartialMessageReaction(
                        self._state,
                        new_message,
                        Emoticon(self._state, r.reaction),
                        None,
                    )
                    for r in message.reactions
                    if r.reaction_type == 1
                ]
                sticker_reactions = [
                    PartialMessageReaction(
                        self._state,
                        new_message,
                        None,
                        Sticker(self._state, r.reaction),
                    )
                    for r in message.reactions
                    if r.reaction_type == 2
                ]
                new_message.partial_reactions = emoticon_reactions + sticker_reactions

                messages.append(new_message)

            if message is None:
                return

            await self._fill_queue_users(messages)
            for message in messages:
                yield message

            last_message_timestamp = message.server_timestamp
            last_ordinal = message.ordinal

            if not resp.more_available:
                return


class GameReviewsIterator(AsyncIterator["Review"]):
    def __init__(
        self,
        state: ConnectionState,
        game: StatefulGame,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ):  # TODO add support for the other params and make this more efficient
        super().__init__(state, limit, before, after)
        self.game = game

    async def fill(self) -> AsyncGenerator[Review, None]:
        from .review import Review, ReviewGame

        cursor = "*"
        while True:
            data = await self._state.http.get_reviews(self.game.id, "all", "all", "all", cursor)
            if cursor == "*":
                self.game = ReviewGame(self._state, self.game.id, data["query_summary"]["review_score"])
            assert isinstance(self.game, ReviewGame)
            cursor = data["cursor"]
            reviews = data["reviews"]

            for review, user in zip(
                reviews,
                await self._state.fetch_users(int(review["author"]["steamid"]) for review in reviews),
            ):
                if user is None:
                    continue
                review = Review._from_data(self._state, review, self.game, user)
                if not self.after < review.created_at < self.before:
                    return

                yield review


class UserReviewsIterator(AsyncIterator["Review"]):
    def __init__(
        self,
        state: ConnectionState,
        user: BaseUser,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ):
        super().__init__(state, limit, before, after)
        self.user = user

    async def fill(self) -> AsyncGenerator[Review, None]:
        from .review import Review

        pages = 1

        # ideally I'd like to find an actual api for these
        async def get_app_ids(page_number: int = 1) -> list[int]:
            nonlocal pages
            page = await self._state.http.get(
                URL.COMMUNITY / f"profiles/{self.user.id64}/recommended", params={"p": page_number}
            )
            soup = BeautifulSoup(page, HTML_PARSER)
            if pages == 1:
                *_, pages = [1] + [
                    int(a["href"][len("?p=") :]) for a in soup.find_all("a", class_="pagelink")
                ]  # str.removeprefix
            return [
                int(URL_(review.find("div", class_="leftcol").a["href"]).parts[-1])
                for review in soup.find_all("div", class_="review_box_content")
            ]

        for review_ in await self._state.fetch_user_review(self.user.id64, await get_app_ids()):
            review = Review._from_proto(self._state, review_, self.user)
            if not self.after < review.created_at < self.before:
                return

            yield review

        for page in range(2, pages + 1):
            for review_ in await self._state.fetch_user_review(self.user.id64, await get_app_ids(page)):
                review = Review._from_proto(self._state, review_, self.user)
                if not self.after < review.created_at < self.before:
                    return

                yield review


class _EventIterator(AsyncIterator[T]):
    ID_PARSE_REGEX: ClassVar[re.Pattern[str]]

    def __init__(
        self, clan: Clan, state: ConnectionState, limit: int | None, before: datetime | None, after: datetime | None
    ):
        super().__init__(state, limit, before, after)
        self.clan = clan

    async def fill(self) -> AsyncGenerator[T, None]:
        cls = self.__class__
        rss = await self._state.http.get_clan_rss(
            self.clan.id64
        )  # TODO make this use the calendar? does that work for announcements

        soup = BeautifulSoup(rss, HTML_PARSER)

        ids = []
        for url in soup.find_all("guid"):
            match = cls.ID_PARSE_REGEX.findall(url.text)
            if match:
                ids.append(int(match[0]))

        if not ids:
            return

        from . import event

        event_cls: type[Announcement | Event[EventType]] = getattr(
            event, cls.__orig_bases__[0].__args__[0].__forward_arg__  # type: ignore
        )
        events = []
        for event_ in await self.get_events(ids):
            event = event_cls(self._state, self.clan, event_)
            if not self.after < event.starts_at < self.before:
                return
            events.append(event)

        await self._fill_queue_users(events, ("author", "last_edited_by", "approved_by"))

        for event in events:
            yield event

    async def get_events(self, ids: list[int]) -> list[dict[str, Any]]:
        raise NotImplementedError


class EventIterator(_EventIterator["Event[EventType]"]):
    ID_PARSE_REGEX = re.compile(r"events/+(\d+)")

    async def get_events(self, ids: list[int]) -> list[dict[str, Any]]:
        data = await self._state.http.get_clan_events(self.clan.id, ids)
        return data["events"]


class AnnouncementsIterator(_EventIterator["Announcement"]):
    ID_PARSE_REGEX = re.compile(r"announcements/detail/(\d+)")

    async def get_events(self, ids: list[int]) -> list[dict[str, Any]]:
        announcements = await asyncio.gather(*(self._state.http.get_clan_announcement(self.clan.id, id) for id in ids))
        events = []
        for announcement in announcements:
            events += announcement["events"]
        return events


class ManifestIterator(AsyncIterator["Manifest"]):
    def __init__(
        self,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
        game: StatefulGame,
        branch: str,
        password: str | None,
        password_hash: str,
    ):
        super().__init__(state, limit, before, after)
        self.game = game
        self.branch = branch
        self.password = password
        self.password_hash = password_hash

    async def fill(self) -> AsyncGenerator[Manifest, None]:
        manifest_coros = await self._state.fetch_manifests(
            self.game.id, self.branch, self.password, self.limit, self.password_hash
        )
        for chunk in utils.chunk(manifest_coros, 100):
            for manifest in await asyncio.gather(*chunk):
                if self.after < manifest.created_at < self.before:
                    yield manifest


class UserPublishedFilesIterator(AsyncIterator["PublishedFile"]):
    def __init__(
        self,
        state: ConnectionState,
        user: BaseUser,
        game: Game | None,
        type: PublishedFileType = PublishedFileType.Community,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ):
        super().__init__(state, limit, before, after)
        self.user = user
        self.app_id = getattr(game, "id", 0)
        self.revision = revision
        self.type = type
        self.language = language

    async def fill(self):
        from .published_file import PublishedFile

        initial = await self._state.fetch_user_published_files(
            self.user.id64, self.app_id, 1, self.type, self.revision, self.language
        )

        for file in initial.publishedfiledetails:
            file = PublishedFile(self._state, file, self.user)
            if not self.after < file.created_at < self.before:
                return
            yield file

        for page in range(2, math.ceil((initial.total + 30) / 30)):
            msg = await self._state.fetch_user_published_files(
                self.user.id64, self.app_id, page, self.type, self.revision, self.language
            )

            for file in msg.publishedfiledetails:
                file = PublishedFile(self._state, file, self.user)
                if not self.after < file.created_at < self.before:
                    return
                yield file


class GamePublishedFilesIterator(AsyncIterator["PublishedFile"]):
    def __init__(
        self,
        state: ConnectionState,
        game: Game,
        type: PublishedFileQueryFileType = PublishedFileQueryFileType.Items,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ):
        super().__init__(state, limit, before, after)
        self.game = game
        self.type = type
        self.revision = revision
        self.language = language

    async def fill(self):
        from .published_file import PublishedFile

        remaining = None
        cursor = "*"

        while remaining is None or remaining > 0:
            protos = await self._state.fetch_game_published_files(
                self.game.id, self.after, self.before, self.type, self.revision, self.language, self.limit, cursor
            )
            if remaining is None:
                remaining = protos.total
            remaining -= len(protos.publishedfiledetails)
            cursor = protos.next_cursor

            files: list[PublishedFile] = []
            for file in protos.publishedfiledetails:
                author: Authors = file.creator  # type: ignore
                file = PublishedFile(self._state, file, author)
                if not self.after < file.created_at < self.before:
                    remaining = 0
                    break
                files.append(file)

            await self._fill_queue_users(files)
            for file in files:
                yield file
