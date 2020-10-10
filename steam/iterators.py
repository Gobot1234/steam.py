# -*- coding: utf-8 -*-

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

import itertools
import re
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Generic, Optional, TypeVar, Union

from bs4 import BeautifulSoup

from . import utils
from .comment import Comment
from .enums import ETradeOfferState

if TYPE_CHECKING:
    from .abc import BaseUser
    from .clan import Clan
    from .state import ConnectionState
    from .trade import TradeOffer

T = TypeVar("T")
MaybeCoro = Callable[[T], Union[bool, Coroutine[None, None, bool]]]


class AsyncIterator(Generic[T]):
    """A class from which async iterators (see :pep:`525`) can ben easily derived.

    .. container:: operations

        .. describe:: async for y in x

            Iterates over the contents of the async iterator.

    Attributes
    ----------
    before: :class:`datetime.datetime`
        When to find objects before.
    after: :class:`datetime.datetime`
        When to find objects after.
    limit: Optional[:class:`int`]
        The maximum size of the :attr:`AsyncIterator.queue`.
    queue: :class:`collections.deque[T]`
        The queue containing the elements of the iterator.
    """

    __slots__ = ("before", "after", "limit", "queue", "_is_filled", "_state")

    def __init__(
        self, state: ConnectionState, limit: Optional[int], before: Optional[datetime], after: Optional[datetime]
    ):
        self._state = state
        self.before = before or datetime.utcnow()
        self.after = after or datetime.utcfromtimestamp(0)
        self._is_filled = False
        self.queue: deque[T] = deque()
        self.limit = limit

    def append(self, element: T) -> bool:
        if self.limit is None:
            self.queue.append(element)
            return True
        if len(self.queue) <= self.limit:
            self.queue.append(element)
            return True
        if len(self.queue) == self.limit:
            self.queue.append(element)
            return False
        return False

    def get(self, **attrs: Any) -> Coroutine[None, None, Optional[T]]:
        """|coro|
        A helper function which is similar to :func:`~steam.utils.get` except it runs over the :class:`AsyncIterator`.

        This is roughly equipment to: ::

            elements = await AsyncIterator.flatten()
            element = steam.utils.get(name='Item', elements)

        Example
        -------
        Getting the last comment from a user named 'Dave' or None: ::

            msg = await User.comments().get(author__name='Dave')

        Parameters
        ----------
        **attrs
            Keyword arguments that denote attributes to match.

        Returns
        -------
        Optional[T]
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

        return self.find(predicate)

    async def find(self, predicate: MaybeCoro) -> Optional[T]:
        """|coro|
        A helper function which is similar to :func:`~steam.utils.find` except it runs over the :class:`AsyncIterator`.
        However unlike :func:`~steam.utils.find`, the predicate provided can be a |coroutine_link|_.

        This is roughly equivalent to: ::

            elements = await AsyncIterator.flatten()
            element = steam.utils.find(elements, lambda e: e.name == 'Item')

        Example
        -------
        Getting the last trade with a message or None: ::

            def predicate(trade):
                return trade.message is not None

            trade = await Client.trade_history().find(predicate)

        Parameters
        ----------
        predicate: Callable[[T], Union[:class:`bool`, Awaitable[:class:`bool`]]]
            A callable/coroutine that returns a boolean.

        Returns
        -------
        Optional[T]
            The first element from the iterator for which the ``predicate`` returns ``True`` or ``None`` if no matching
            element was found.
        """
        async for elem in self:
            ret = await utils.maybe_coroutine(predicate, elem)
            if ret:
                return elem

    async def flatten(self) -> list[T]:
        """|coro|
        A helper function that iterates over the :class:`AsyncIterator` returning a list of all the elements in the
        iterator.

        This is equivalent to: ::

            elements = [element async for element in AsyncIterator]

        Returns
        -------
        list[T]
            A list of every element in the iterator.
        """
        return [element async for element in self]

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    def __anext__(self) -> Coroutine[None, None, T]:
        return self.next()

    async def next(self) -> T:
        """|coro|
        Advances the iterator by one, if possible.

        Raises
        --------
        :exc:`StopAsyncIteration`
            There are no more elements in the iterator.
        """
        if not self.queue:
            if self._is_filled:
                raise StopAsyncIteration
            await self.fill()
            if not self.queue:  # yikes
                raise StopAsyncIteration
            self._is_filled = True
        return self.queue.pop()

    async def fill(self) -> None:
        raise NotImplementedError


class CommentsIterator(AsyncIterator[Comment]):
    __slots__ = ("owner",)

    def __init__(
        self,
        state: ConnectionState,
        limit: Optional[int],
        before: Optional[datetime],
        after: Optional[datetime],
        owner: Union[BaseUser, Clan],
    ):
        super().__init__(state, limit, before, after)
        self.owner = owner

    async def fill(self) -> None:
        data = await self._state.http.get_comments(
            id64=self.owner.id64, comment_path=self.owner.comment_path, limit=self.limit
        )
        soup = BeautifulSoup(data["comments_html"], "html.parser")
        to_fetch = []

        for comment in soup.find_all("div", attrs={"class": "commentthread_comment responsive_body_text"}):
            timestamp = comment.find("span", attrs={"class": "commentthread_comment_timestamp"})["data-timestamp"]
            timestamp = datetime.utcfromtimestamp(int(timestamp))
            if self.after < timestamp < self.before:
                author_id = int(comment.find("a", attrs={"class": "commentthread_author_link"})["data-miniprofile"])
                comment_id = int(re.findall(r"comment_([0-9]*)", str(comment))[0])
                content = comment.find("div", attrs={"class": "commentthread_comment_text"}).get_text().strip()
                to_fetch.append(utils.make_id64(author_id))
                comment = Comment(
                    state=self._state,
                    id=comment_id,
                    timestamp=timestamp,
                    content=content,
                    author=author_id,
                    owner=self.owner,
                )
                if not self.append(comment):
                    return
        users = await self._state.fetch_users(to_fetch)
        for user, comment in itertools.product(users, self.queue):
            if comment.author == user.id:
                comment.author = user


class TradesIterator(AsyncIterator["TradeOffer"]):
    __slots__ = ("_active_only",)

    def __init__(
        self,
        state: ConnectionState,
        limit: Optional[int],
        before: Optional[datetime],
        after: Optional[datetime],
        active_only: bool,
    ):
        super().__init__(state, limit, before, after)
        self._active_only = active_only

    async def fill(self) -> None:
        from .trade import TradeOffer

        resp = await self._state.http.get_trade_history(100, None)
        resp = resp["response"]
        total = resp.get("total_trades", 0)
        if not total:
            return

        descriptions = resp.get("descriptions", [])

        async def process_trade(data: dict, descriptions: dict) -> None:
            if not self.after.timestamp() < data["time_init"] < self.before.timestamp():
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

            trade = await TradeOffer._from_api(state=self._state, data=data)

            if not self._active_only:
                if not self.append(trade):
                    raise StopAsyncIteration
            elif trade.state in (
                ETradeOfferState.Active,
                ETradeOfferState.ConfirmationNeed,
            ):
                if not self.append(trade):
                    raise StopAsyncIteration

        try:
            for trade in resp.get("trades", []):
                await process_trade(trade, descriptions)

            previous_time = trade["time_init"]
            if total > 100:
                for page in range(0, total, 100):
                    if page in (0, 100):
                        continue
                    resp = await self._state.http.get_trade_history(page, previous_time)
                    resp = resp["response"]
                    for trade in resp.get("trades", []):
                        await process_trade(trade, descriptions)
                    previous_time = trade["time_init"]
                resp = await self._state.http.get_trade_history(page + 100, previous_time)
                resp = resp["response"]
                for trade in resp.get("trades", []):
                    await process_trade(trade, descriptions)
        except StopAsyncIteration:
            return
