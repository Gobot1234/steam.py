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
from typing import List, TYPE_CHECKING

from bs4 import BeautifulSoup

from . import utils
from .enums import ETradeOfferState
from .models import Comment, URL

if TYPE_CHECKING:
    from .market import Listing
    from .trade import TradeOffer


class AsyncIterator:
    __slots__ = ('before', 'after', 'limit', 'queue', '_current_iteration', '_state')

    def __init__(self, state, limit, before, after):
        self._state = state
        self.limit = limit
        self.before = before or datetime.utcnow()
        self.after = after or datetime.utcfromtimestamp(0)
        self._current_iteration = 0
        self.queue = asyncio.Queue()

    async def flatten(self):
        ret = []
        while 1:
            try:
                item = await self.next()
            except StopAsyncIteration:
                return ret
            else:
                ret.append(item)

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.next()

    async def next(self):
        if self.queue.empty():
            self._current_iteration += 1
            if self._current_iteration == 2:
                raise StopAsyncIteration
            await self.fill()
        return self.queue.get_nowait()

    async def fill(self):
        pass


class CommentsIterator(AsyncIterator):
    __slots__ = ('owner', '_id', '_comment_type') + AsyncIterator.__slots__

    def __init__(self, state, id, before, after, limit, comment_type):
        super().__init__(state, limit, before, after)
        self._id = id
        self._comment_type = comment_type
        self.owner = None

    async def fill(self):
        from .user import User
        from .abc import make_steam64

        data = await self._state.http.fetch_comments(id64=self._id, limit=self.limit, comment_type=self._comment_type)
        self.owner = await self._state.fetch_user(self._id) if self._comment_type == 'Profile' else \
            await self._state.client.fetch_group(self._id)
        soup = BeautifulSoup(data['comments_html'], 'html.parser')
        comments = soup.find_all('div', attrs={'class': 'commentthread_comment responsive_body_text'})
        to_fetch = []

        for comment in comments:
            if self.after < comment['data-timestamp'] < self.before:
                timestamp = datetime.utcfromtimestamp(int(comment['data-timestamp']))
                author_id = int(comment['data-miniprofile'])
                comment_id = int(re.findall(r'comment_([0-9]*)', str(comment))[0])
                content = comment.find('div', attrs={"class": 'commentthread_comment_text'}).text.strip()
                to_fetch.append(make_steam64(author_id))
                self.queue.put_nowait(Comment(state=self._state, comment_type=self._comment_type,
                                              comment_id=comment_id, timestamp=timestamp,
                                              content=content, author=author_id, owner=self.owner))
                if self.queue.qsize == self.limit:
                    return
        users = await self._state.http.fetch_profiles(to_fetch)
        for user in users:
            author = User(state=self._state, data=user)
            for comment in self.queue._queue:
                if comment.author == author.id:
                    comment.author = author

    async def flatten(self) -> List['Comment']:
        return await super().flatten()


class TradesIterator(AsyncIterator):
    __slots__ = ('_active_only',) + AsyncIterator.__slots__

    def __init__(self, state, limit, before, after, active_only):
        super().__init__(state, limit, before, after)
        self._active_only = active_only

    async def _process_trade(self, data, descriptions):
        from .trade import TradeOffer

        if self.after.timestamp() < data['time_init'] < self.before.timestamp():
            for item in descriptions:
                for asset in data.get('assets_received', []):
                    if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                        asset.update(item)
                for asset in data.get('assets_given', []):
                    if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                        asset.update(item)

            # duck type the attributes
            data['tradeofferid'] = data['tradeid']
            data['accountid_other'] = data['steamid_other']
            data['trade_offer_state'] = data['status']
            data['items_to_give'] = data.get('assets_given', [])
            data['items_to_receive'] = data.get('assets_received', [])

            trade = TradeOffer(state=self._state, data=data)
            await trade.__ainit__()
            if not self._active_only:
                self.queue.put_nowait(trade)
            elif self._active_only and trade.state in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed):
                self.queue.put_nowait(trade)

            if self.queue.qsize() == self.limit:
                raise StopAsyncIteration  # I think this is somewhat appropriate

    async def fill(self):
        resp = await self._state.http.fetch_trade_history(100, None)
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
                    resp = await self._state.http.fetch_trade_history(page, previous_time)
                    resp = resp['response']
                    for trade in resp.get('trades', []):
                        await self._process_trade(trade, descriptions)
                    previous_time = trade['time_init']
                resp = await self._state.http.fetch_trade_history(page + 100, previous_time)
                resp = resp['response']
                for trade in resp.get('trades', []):
                    await self._process_trade(trade, descriptions)
        except StopAsyncIteration:
            return

    async def flatten(self) -> List['TradeOffer']:
        return await super().flatten()


class MarketListingsIterator(AsyncIterator):

    def __init__(self, state, limit, before, after):
        super().__init__(state, limit, before, after)

    async def fill(self):
        from .market import Listing

        resp = await self._state.market.fetch_pages()
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

            for context_id in resp['assets'].values():
                for listings in context_id.values():
                    for listing in listings.values():
                        listing['assetid'] = listing['id']  # we need to swap the ids around
                        try:
                            listing['id'] = int(utils.find(lambda m: m[1] == listing['assetid'], matches)[0])
                            price = [price for price in prices
                                     if price and price[0] and price[0][0] and
                                     price[0][0] == listing['id']]
                            if price:
                                listing['price'] = price[0][1]
                        except TypeError:  # TODO
                            # this isn't very common, the listing couldn't be
                            # found I need to do more handling for this to make
                            # sure it doesn't happen but for now this will do.
                            pass
                        else:
                            self.queue.put_nowait(Listing(state=self._state, data=listing))
                        finally:
                            if self.queue.qsize == self.limit:
                                return

    async def flatten(self) -> List['Listing']:
        return await super().flatten()
