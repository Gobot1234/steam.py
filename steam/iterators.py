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

import asyncio
import re
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator as _AsyncIterator,
    Awaitable,
    Callable,
    List,
    Optional,
    Union,
)

from bs4 import BeautifulSoup

from . import utils
from .enums import ETradeOfferState
from .models import URL, Comment

if TYPE_CHECKING:
    from .abc import BaseUser
    from .group import Group
    from .market import Listing
    from .trade import TradeOffer
    from .state import ConnectionState

maybe_coro_predicate = Callable[..., Union[bool, Awaitable[bool]]]


class AsyncIterator(_AsyncIterator):
    """A class from which async iterators (see :pep:`525`) can ben easily derived.

    .. container:: operations

        .. describe:: async for x in y

            Iterates over the contents of the async iterator.

    Attributes
    ----------
    before: :class:`datetime.datetime`
        When to find objects before.
    after: :class:`datetime.datetime`
        When to find objects after.
    limit: Optional[:class:`int`]
        The maximum size of the :attr:`AsyncIterator.queue`.
    queue: :class:`asyncio.Queue`
        The queue containing the elements of the iterator.
    """
    __slots__ = ('before', 'after', 'limit', 'queue', '_is_filled', '_state')

    def __init__(self, state: 'ConnectionState', limit: Optional[int],
                 before: Optional[datetime], after: Optional[datetime]):
        self._state = state
        self.before = before or datetime.utcnow()
        self.after = after or datetime.utcfromtimestamp(0)
        self._is_filled = False
        self.queue = asyncio.Queue(maxsize=limit or 0)
        self.limit = limit

    def get(self, **attrs) -> Optional[Any]:
        r"""A helper function which is similar to :func:`~steam.utils.get`
        except it runs over the :class:`AsyncIterator`.

        This is roughly equipment to: ::

            elements = await AsyncIterator.flatten()
            element = steam.utils.get(name='Item', elements)

        Example
        -------
        Getting the last comment from a user named 'Dave' or None: ::

            msg = await User.comments().get(author__name='Dave')

        Parameters
        ----------
        \*\*attrs
            Keyword arguments that denote attributes to match.

        Returns
        -------
        Optional[Any]
            The first element from the ``iterable``
            which matches all the traits passed in ``attrs``
            or ``None`` if no matching element was found.
        """

        def predicate(elem):
            for attr, val in attrs.items():
                nested = attr.split('__')
                obj = elem
                for attribute in nested:
                    obj = getattr(obj, attribute)

                if obj != val:
                    return False
            return True

        return self.find(predicate)

    async def find(self, predicate: maybe_coro_predicate) -> Optional[Any]:
        """|coro|
        A helper function which is similar to :func:`~steam.utils.find`
        except it runs over the :class:`AsyncIterator`. However unlike
         :func:`~steam.utils.find`, the predicate provided can be a |coroutine_link|_.

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
        predicate: Callable[..., Union[:class:`bool`, Awaitable[:class:`bool`]]]
            A callable/coroutine that returns a boolean.

        Returns
        -------
        Optional[Any]
            The first element from the ``iterable``
            for which the ``predicate`` returns ``True``
            or ``None`` if no matching element was found.
        """
        while 1:
            try:
                elem = await self.next()
            except StopAsyncIteration:
                return None

            ret = await utils.maybe_coroutine(predicate, elem)
            if ret:
                return elem

    async def flatten(self) -> List[Any]:
        """|coro|
        A helper function that iterates over the :class:`AsyncIterator`
        returning a list of all the elements in the iterator.

        This is equivalent to: ::

            elements = [element async for element in AsyncIterator]

        Returns
        -------
        List[Any]
            A list of every element in the iterator.
        """
        return [element async for element in self]

    async def __anext__(self) -> Any:
        return await self.next()

    async def next(self) -> Any:
        """|coro|
        Advances the iterator by one, if possible.

        Raises
        --------
        :exc:`StopAsyncIteration`:
            There are no more elements in the iterator.
        """
        if self.queue.empty():
            if self._is_filled:
                raise StopAsyncIteration
            await self.fill()
            self._is_filled = True
        return self.queue.get_nowait()

    async def fill(self) -> None:
        pass


class CommentsIterator(AsyncIterator):
    __slots__ = ('owner', '_id')

    def __init__(self, state: 'ConnectionState', before: datetime,
                 after: datetime, limit: int, owner: Union['BaseUser', 'Group']):
        super().__init__(state, limit, before, after)
        self.owner = owner

    async def fill(self) -> None:
        from .user import User

        data = await self._state.http.get_comments(
            id64=self.owner.id64, limit=self.limit,
            comment_type='Profile' if isinstance(self.owner, User) else 'Clan'
        )
        soup = BeautifulSoup(data['comments_html'], 'html.parser')
        comments = soup.find_all('div', attrs={'class': 'commentthread_comment responsive_body_text'})
        to_fetch = []

        for comment in comments:
            timestamp = datetime.utcfromtimestamp(int(comment['data-timestamp']))
            if self.after < timestamp < self.before:
                author_id = int(comment['data-miniprofile'])
                comment_id = int(re.findall(r'comment_([0-9]*)', str(comment))[0])
                content = comment.find('div', attrs={"class": 'commentthread_comment_text'}).get_text().strip()
                to_fetch.append(utils.make_steam64(author_id))
                comment = Comment(
                    state=self._state, id=comment_id, timestamp=timestamp,
                    content=content, author=author_id, owner=self.owner
                )
                try:
                    self.queue.put_nowait(comment)
                except asyncio.QueueFull:
                    return
        users = await self._state.http.get_profiles(to_fetch)
        for user in users:
            author = User(state=self._state, data=user)
            for comment in self.queue._queue:
                if comment.author == author.id:
                    comment.author = author

    def get(self, **attrs) -> Optional[Comment]:
        return super().get(**attrs)

    async def find(self, predicate: maybe_coro_predicate) -> Optional[Comment]:
        return await super().find(predicate)

    async def flatten(self) -> List[Comment]:
        return await super().flatten()


class TradesIterator(AsyncIterator):
    __slots__ = ('_active_only',)

    def __init__(self, state: 'ConnectionState', limit: int, before: datetime,
                 after: datetime, active_only: bool):
        super().__init__(state, limit, before, after)
        self._active_only = active_only

    async def _process_trade(self, data: dict, descriptions: dict) -> None:
        from .trade import TradeOffer

        if self.after.timestamp() < data['time_init'] < self.before.timestamp():
            for item in descriptions:
                for asset in data.get('assets_received', []):
                    if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                        asset.update(item)
                for asset in data.get('assets_given', []):
                    if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                        asset.update(item)

            # patch in the attributes cause steam is cool
            data['tradeofferid'] = data['tradeid']
            data['accountid_other'] = data['steamid_other']
            data['trade_offer_state'] = data['status']
            data['items_to_give'] = data.get('assets_given', [])
            data['items_to_receive'] = data.get('assets_received', [])

            trade = await TradeOffer._from_api(state=self._state, data=data)

            try:
                if not self._active_only:
                    self.queue.put_nowait(trade)
                elif self._active_only and trade.state in \
                        (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed):
                    self.queue.put_nowait(trade)

            except asyncio.QueueFull:
                raise StopAsyncIteration

    async def fill(self) -> None:
        resp = await self._state.http.get_trade_history(100, None)
        resp = resp['response']
        total = resp.get('total_trades', 0)
        if not total:
            return

        descriptions = resp.get('descriptions', [])
        try:
            for trade in resp.get('trades', []):
                await self._process_trade(trade, descriptions)

            previous_time = trade['time_init']
            if total > 100:
                for page in range(0, total, 100):
                    if page in (0, 100):
                        continue
                    resp = await self._state.http.get_trade_history(page, previous_time)
                    resp = resp['response']
                    for trade in resp.get('trades', []):
                        await self._process_trade(trade, descriptions)
                    previous_time = trade['time_init']
                resp = await self._state.http.get_trade_history(page + 100, previous_time)
                resp = resp['response']
                for trade in resp.get('trades', []):
                    await self._process_trade(trade, descriptions)
        except StopAsyncIteration:
            return

    def get(self, **attrs) -> Optional['TradeOffer']:
        return super().get(**attrs)

    async def find(self, predicate: maybe_coro_predicate) -> Optional['TradeOffer']:
        return await super().find(predicate)

    async def flatten(self) -> List['TradeOffer']:
        return await super().flatten()


class MarketListingsIterator(AsyncIterator):

    async def fill(self) -> None:
        from .market import Listing

        resp = await self._state.market.get_pages()
        pages = resp['total_count']
        if not pages:  # they have no listings just return
            return
        for start in range(0, pages, 100):
            params = {
                "start": start,
                "count": 100
            }
            resp = await self._state.request('GET', url=f'{URL.COMMUNITY}/market/myhistory/render', params=params)
            matches = re.findall(r"CreateItemHoverFromContainer\( \w+, 'history_row_\d+_(\d+)_\w+', "
                                 r"\d+, '\d+', '(\d+)', \d+ \);", resp["hovers"])
            # we need the listing id and the asset id(???)
            prices = []
            soup = BeautifulSoup(resp['results_html'], 'html.parser')
            compiled = re.compile(r'market_listing[\s\w]*')
            div = soup.find_all('div', attrs={"class": compiled})
            span = soup.find_all('span', attrs={"class": compiled})
            div.extend(span)
            for listing in div:
                listing_id = re.findall(r'history_row_\d+_(\d+)_\w+', str(listing))
                price = re.findall(r'[^\d]*(\d+)(?:[.,])(\d+)', listing.text, re.UNICODE)
                try:
                    price = float(f'{price[0][0]}.{price[0][1]}')
                except IndexError:
                    price = None
                prices.append((listing_id, price))

            for game_context_id in resp['assets'].values():
                for games_listings in game_context_id.values():
                    for listing in games_listings.values():
                        listing['assetid'] = listing['id']  # we need to swap the ids around
                        try:
                            listing['id'] = int([m for m in matches if m[1] == listing['assetid']][0])
                            price = [price for price in prices
                                     if price and price[0] and price[0][0] and
                                     price[0][0] == listing['id']]
                            if price:
                                listing['price'] = price[0][1]
                        except TypeError:  # TODO
                            # this isn't very common, the listing couldn't be
                            # found I need to do more handling for this to make
                            # sure it doesn't happen but for now this will do.
                            continue
                        try:
                            self.queue.put_nowait(Listing(state=self._state, data=listing))
                        except asyncio.QueueFull:
                            return

    def get(self, **attrs) -> Optional['Listing']:
        return super().get(**attrs)

    async def find(self, predicate: maybe_coro_predicate) -> Optional['Listing']:
        return await super().find(predicate)

    async def flatten(self) -> List['Listing']:
        return await super().flatten()
