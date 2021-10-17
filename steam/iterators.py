"""
The MIT License (MIT)

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
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import deque
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from bs4 import BeautifulSoup
from typing_extensions import ClassVar, TypeAlias

from . import utils
from .comment import Comment

if TYPE_CHECKING:
    from .abc import Channel, Commentable, Message
    from .channel import ClanChannel, ClanMessage, DMChannel, GroupChannel, GroupMessage, UserMessage
    from .clan import Clan
    from .event import Announcement, Event
    from .game import StatefulGame
    from .group import Group
    from .state import ConnectionState
    from .trade import DescriptionDict, TradeOffer

T = TypeVar("T")
TT = TypeVar("TT")
ChannelT = TypeVar("ChannelT", bound="Channel[Any]", covariant=True)
CommentableT = TypeVar("CommentableT", bound="Commentable")
M = TypeVar("M", bound="Message", covariant=True)

MaybeCoro: TypeAlias = "Callable[[T], bool | Coroutine[Any, Any, bool]]"
UNIX_EPOCH = datetime.utcfromtimestamp(0)


class AsyncIterator(Generic[T]):  # TODO re-work to be fetch in chunks in V1
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
        The maximum size of the :attr:`queue`.
    queue
        The queue containing the elements of the iterator.
    """

    def __init__(
        self,
        state: ConnectionState,
        limit: int | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
    ):
        self._state = state
        self.before = before or datetime.utcnow()
        self.after = after or UNIX_EPOCH
        self._is_filled = False
        self.queue: deque[T] = deque()
        self.limit = limit

    def _append(self, element: T) -> bool:
        if self.limit is None:
            self.queue.append(element)
            return True
        if len(self.queue) < self.limit:
            self.queue.append(element)
            return True
        if len(self.queue) == self.limit:
            self.queue.append(element)

        return False

    async def _fill_queue_users(
        self,
        id64s: set[Any],  # should be set[int] but # type: ignore stuff forces this
        attributes: tuple[str, ...] = ("author",),
    ) -> None:
        for user in await self._state.fetch_users(list(id64s)):
            for element in self.queue:
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
        However unlike :func:`~steam.utils.find`, the predicate provided can be a |coroutine_link|_.

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

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    def __anext__(self) -> Coroutine[None, None, T]:
        return self.next()

    async def next(self) -> T:
        """Advances the iterator by one, if possible.

        Raises
        ------
        :exc:`StopAsyncIteration`
            There are no more elements in the iterator.
        """
        if not self.queue:
            if self._is_filled:
                raise StopAsyncIteration
            await self.fill()
            self._is_filled = True
        if not self.queue:  # yikes
            raise StopAsyncIteration
        return self.queue.pop()

    async def fill(self) -> None:
        raise NotImplementedError


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


class CommentsIterator(AsyncIterator[Comment[CommentableT]]):
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

    async def fill(self) -> None:
        comments = await self._state.fetch_comments(self.owner, self.limit, self.after, self.oldest_first)
        author_id64s = set()
        for comment in comments:
            comment = Comment(
                self._state,
                id=comment.id,
                content=comment.content,
                created_at=datetime.utcfromtimestamp(comment.timestamp),
                author=comment.author_id64,  # type: ignore
                owner=self.owner,
            )
            if not self.after < comment.created_at < self.before:
                continue
            if not self._append(comment):
                break
            author_id64s.add(comment.author)

        await self._fill_queue_users(author_id64s)


class TradesIterator(AsyncIterator["TradeOffer"]):
    def __init__(
        self,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        super().__init__(state, limit, before, after)

    async def fill(self) -> None:
        from .trade import TradeOffer

        resp = await self._state.http.get_trade_history(100, None)
        resp = resp["response"]
        total = resp.get("total_trades", 0)
        if not total:
            return

        descriptions = resp.get("descriptions", [])
        after_timestamp = self.after.timestamp()
        before_timestamp = self.before.timestamp()

        class Stop(Exception):
            ...

        async def process_trade(data: dict[str, Any], descriptions: list[DescriptionDict]) -> None:
            if not after_timestamp < data["time_init"] < before_timestamp:
                return
            for item in descriptions:
                for asset in data.get("assets_received", []):
                    if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                        asset.update(item)
                for asset in data.get("assets_given", []):
                    if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                        asset.update(item)

            # patch in the attributes cause steam is cool
            data["tradeofferid"] = data["tradeid"]
            data["accountid_other"] = data["steamid_other"]
            data["trade_offer_state"] = data["status"]
            data["items_to_give"] = data.get("assets_given", [])
            data["items_to_receive"] = data.get("assets_received", [])

            trade = TradeOffer._from_api(state=self._state, data=data)

            if not self._append(trade):
                raise Stop
            partner_id64s.add(trade.partner)

        partner_id64s = set()

        try:
            for trade in resp.get("trades", []):
                await process_trade(trade, descriptions)

            previous_time = trade["time_init"]
            if total < 100:
                for page in range(200, math.ceil((total + 100) / 100) * 100, 100):
                    resp = await self._state.http.get_trade_history(page, previous_time)
                    resp = resp["response"]

                    for trade in resp.get("trades", []):
                        previous_time = trade["time_init"]
                        await process_trade(trade, descriptions)
        except Stop:
            pass

        await self._fill_queue_users(partner_id64s, ("partner",))


class ChannelHistoryIterator(AsyncIterator[M], Generic[M, ChannelT]):
    def __init__(
        self,
        channel: ChannelT,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        super().__init__(state, limit, before, after)
        self.before = before or UNIX_EPOCH
        self.channel = channel


class DMChannelHistoryIterator(ChannelHistoryIterator["UserMessage", "DMChannel"]):
    __slots__ = ("participant",)

    def __init__(
        self,
        channel: DMChannel,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        super().__init__(channel, state, limit, before, after)
        self.participant = channel.participant

    async def fill(self) -> None:
        from .message import Message, UserMessage

        after_timestamp = int(self.after.timestamp())
        before_timestamp = int(self.before.timestamp())

        last_message_timestamp = before_timestamp

        while True:
            resp = await self._state.fetch_user_history(
                self.participant.id64, start=after_timestamp, last=last_message_timestamp
            )
            if not resp.messages:
                return

            for message in resp.messages:
                new_message = UserMessage.__new__(UserMessage)
                Message.__init__(new_message, channel=self.channel, proto=message)
                new_message.author = (  # type: ignore
                    self.participant if message.accountid == self.participant.id else self._state.client.user
                )
                new_message.created_at = datetime.utcfromtimestamp(message.timestamp)
                if not self._append(new_message):
                    return

            last_message_timestamp = int(message.timestamp)

            if not resp.more_available:
                return


GroupMessages = TypeVar("GroupMessages", bound="ClanMessage | GroupMessage")
GroupChannels = TypeVar("GroupChannels", bound="ClanChannel | GroupChannel")


class GroupChannelHistoryIterator(ChannelHistoryIterator[GroupMessages, GroupChannels]):
    __slots__ = ("group",)

    def __init__(
        self,
        channel: ClanChannel | GroupChannel,
        state: ConnectionState,
        limit: int | None,
        before: datetime | None,
        after: datetime | None,
    ):
        super().__init__(channel, state, limit, before, after)
        self.group: Group | Clan = channel.group or channel.clan  # type: ignore

    async def fill(self) -> None:
        from .message import ClanMessage, GroupMessage, Message

        after_timestamp = int(self.after.timestamp())
        before_timestamp = int(self.before.timestamp())
        last_message_timestamp = before_timestamp
        group_id = getattr(self.group, "chat_id", None) or self.group.id
        author_id64s = set()

        while True:
            resp = await self._state.fetch_group_history(
                group_id, self.channel.id, start=after_timestamp, last=last_message_timestamp
            )
            if not resp.messages:
                return

            for message in resp.messages:
                new_message = (
                    GroupMessage.__new__(GroupMessage) if self.channel.group else ClanMessage.__new__(ClanMessage)
                )
                Message.__init__(new_message, channel=self.channel, proto=message)
                new_message.author = utils.make_id64(message.sender)  # type: ignore
                author_id64s.add(new_message.author)
                new_message.created_at = datetime.utcfromtimestamp(message.server_timestamp)
                if not self._append(new_message):
                    break

            last_message_timestamp = int(message.server_timestamp)

            if not resp.more_available:
                break

        await self._fill_queue_users(author_id64s)


class _EventIterator(AsyncIterator[T]):
    ID_PARSE_REGEX: ClassVar[re.Pattern[str]]

    def __init__(
        self, clan: Clan, state: ConnectionState, limit: int | None, before: datetime | None, after: datetime | None
    ):
        super().__init__(state, limit, before, after)
        self.clan = clan

    async def fill(self) -> None:
        cls = self.__class__
        rss = await self._state.http.get_clan_rss(
            self.clan.id64
        )  # TODO make this use the calendar? does that work for announcements

        soup = BeautifulSoup(rss, "html.parser")

        ids = []
        for url in soup.find_all("guid"):
            match = cls.ID_PARSE_REGEX.findall(url.text)
            if match:
                ids.append(int(match[0]))

        if not ids:
            return

        events = await self.get_events(ids)
        to_fetch_id64s = set()
        from . import event

        event_cls: type[Announcement | Event] = getattr(
            event, cls.__orig_bases__[0].__args__[0].__forward_arg__  # type: ignore
        )

        for event_ in events["events"]:
            event = event_cls(self._state, self.clan, event_)
            to_fetch_id64s.add(event.author)
            to_fetch_id64s.add(event.last_edited_by)
            if not self._append(event):
                break

        await self._fill_queue_users(to_fetch_id64s, ("author", "last_edited_by", "approved_by"))

    async def get_events(self, ids: list[int]) -> dict[str, Any]:
        raise NotImplementedError


class EventIterator(_EventIterator["Event"]):
    ID_PARSE_REGEX = re.compile(r"events/+(\d+)")

    async def get_events(self, ids: list[int]) -> dict[str, Any]:
        return await self._state.http.get_clan_events(self.clan.id, ids)


class AnnouncementsIterator(_EventIterator["Announcement"]):
    ID_PARSE_REGEX = re.compile(r"announcements/detail/(\d+)")

    async def get_events(self, ids: list[int]) -> dict[str, Any]:
        announcements = await asyncio.gather(*(self._state.http.get_clan_announcement(self.clan.id, id) for id in ids))
        events = []
        for announcement in announcements:
            events += announcement["events"]
        return {"events": events}
