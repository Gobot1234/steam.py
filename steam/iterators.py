# -*- coding: utf-8 -*-

"""
MIT License

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

from bs4 import BeautifulSoup

from . import utils
from .models import Comment, URL


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

    async def fill(self):
        self._current_iteration += 1
        if self._current_iteration == 2:
            raise StopAsyncIteration

    async def next(self):
        if self.queue.empty():
            await self.fill()
        return self.queue.get_nowait()


class CommentsIterator(AsyncIterator):
    __slots__ = ('owner', '_id', '_comment_type') + AsyncIterator.__slots__

    def __init__(self, state, id, before, after, limit, comment_type):
        super().__init__(state, limit, before, after)
        self._id = id
        self._comment_type = comment_type
        self.owner = None

    async def fill(self):
        await super().fill()
        from .user import make_steam64, User

        data = await self._state.http.fetch_comments(id64=self._id, limit=self.limit, comment_type=self._comment_type)
        self.owner = await self._state.fetch_user(self._id) if self._comment_type == 'Profile' else \
            await self._state.client.fetch_group(self._id)
        soup = BeautifulSoup(data['comments_html'], 'html.parser')
        comments = soup.find_all('div', attrs={'class': 'commentthread_comment responsive_body_text'})
        to_fetch = []

        for comment in comments:
            comment = str(comment)
            timestamp = datetime.utcfromtimestamp(int(re.findall(r'data-timestamp="([0-9]*)"', comment)[0]))
            if self.after < timestamp < self.before:
                comment_id = int(re.findall(r'comment_([0-9]*)', comment)[0])
                author_id = int(re.findall(r'data-miniprofile="([0-9]*)"', comment)[0])
                html_content = re.findall(rf'id="comment_content_{comment_id}">\s*(.*?)\s*</div>', comment)[0]
                content = BeautifulSoup(html_content, 'html.parser').get_text('\n')
                to_fetch.append(make_steam64(author_id))
                self.queue.put_nowait(Comment(state=self._state, comment_type=self._comment_type,
                                              comment_id=comment_id, timestamp=timestamp,
                                              content=content, author=author_id, owner=self.owner))
                if self.limit is not None and self.queue.qsize == self.limit:
                    return
        users = await self._state.http.fetch_profiles(to_fetch)
        for user in users:
            author = User(state=self._state, data=user)
            for comment in self.queue._queue:
                if comment.author == author.id:
                    comment.author = author


class TradesIterator(AsyncIterator):
    __slots__ = ('_active_only', '_sent', '_received') + AsyncIterator.__slots__

    def __init__(self, state, limit, before, after, active_only, sent, received):
        super().__init__(state, limit, before, after)
        self._active_only = active_only
        self._sent = sent
        self._received = received

    async def fill(self):
        await super().fill()
        from .trade import TradeOffer

        resp = await self._state.http.fetch_trade_offers(self._active_only, self._sent, self._received)
        data = resp['response']
        for trade in data['trade_offers_sent']:
            if self.after.timestamp() < trade['time_created'] < self.before.timestamp():
                for item in data['descriptions']:
                    for asset in trade.get('items_to_receive', []):
                        if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                            asset.update(item)
                    for asset in trade.get('items_to_give', []):
                        if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                            asset.update(item)

                trade = TradeOffer(state=self._state, data=trade)
                await trade.__ainit__()
                self.queue.put_nowait(trade)
            if self.limit is not None and self.queue.qsize == self.limit:
                return
        for trade in data['trade_offers_received']:
            if self.after.timestamp() < trade['time_created'] < self.before.timestamp():
                for item in data['descriptions']:
                    for asset in trade.get('items_to_receive', []):
                        if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                            asset.update(item)
                    for asset in trade.get('items_to_give', []):
                        if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                            asset.update(item)

                trade = TradeOffer(state=self._state, data=trade)
                await trade.__ainit__()
                self.queue.put_nowait(trade)
            if self.limit is not None:
                if self.queue.qsize == self.limit:
                    return


class MarketListingsIterator(AsyncIterator):

    def __init__(self, state, limit, before, after):
        super().__init__(state, limit, before, after)

    async def fill(self):
        await super().fill()
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
            for listing in soup.find_all('div', attrs={"class": 'market_listing_row'}):
                listing_ids = re.findall(r'history_row_\d+_(\d+)_\w+', str(listing))
                findall = re.findall(r'[^\d]*(\d+)(?:[.,])(\d+)', listing.text, re.UNICODE)
                try:
                    price = float(f'{findall[0][0]}.{findall[0][1]}')
                except IndexError:
                    price = None
                prices.append((listing_ids, price))

            for context_id in resp['assets'].values():  # TODO fix this only returning some
                for listings in context_id.values():
                    for listing in listings.values():
                        listing['assetid'] = listing['id']  # we need to swap the ids around
                        try:
                            listing['id'] = int(utils.find(lambda m: m[1] == listing['id'], matches)[0])
                            _, listing['price'] = utils.find(lambda p: int(p[0][0]) == listing['id'], prices)
                        except (TypeError, IndexError):
                            pass
                        else:
                            listing = Listing(state=self._state, data=listing)
                            self.queue.put_nowait(listing)
                        if self.limit is not None and self.queue.qsize == self.limit:
                            return