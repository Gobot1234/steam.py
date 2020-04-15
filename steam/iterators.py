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

from .models import Comment


class AsyncIterator:
    __slots__ = ('before', 'after', 'limit', '_current_iteration', '_state')

    def __init__(self, state, limit, before, after):
        self._state = state
        self.limit = limit
        self.before = before or datetime.utcnow()
        self.after = after or datetime.utcfromtimestamp(0)
        self._current_iteration = 0

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


class CommentsIterator(AsyncIterator):
    __slots__ = ('comments', 'owner', '_user_id') + AsyncIterator.__slots__

    def __init__(self, state, user_id, before, after, limit):
        super().__init__(state, limit, before, after)
        self._user_id = user_id
        self.comments = asyncio.Queue()
        self.owner = None

    async def fill_comments(self):
        await super().fill()
        from .user import make_steam64, User

        data = await self._state.http.fetch_comments(id64=self._user_id, limit=self.limit)
        self.owner = await self._state.fetch_user(self._user_id)
        soup = BeautifulSoup(data['comments_html'], 'html.parser')
        comments = soup.find_all('div', attrs={'class': 'commentthread_comment responsive_body_text'})
        to_fetch = []

        for comment in comments:
            comment = str(comment)
            timestamp = datetime.utcfromtimestamp(int(re.findall(r'data-timestamp="([0-9]*)"', comment)[0]))
            if self.after < timestamp < self.before:
                comment_id = int(re.findall(r'comment_([0-9]*)', comment)[0])
                author_id = int(re.findall(r'data-miniprofile="([0-9]*)"', comment)[0])
                html_content = re.findall(rf'id="comment_content_{comment_id}">\s*(.*?)\s*</div>',
                                          comment)[0]
                content = re.sub(r'<.*?>', '', html_content)
                to_fetch.append(make_steam64(author_id))
                self.comments.put_nowait(Comment(state=self._state, comment_id=comment_id, timestamp=timestamp,
                                                 content=content, author=author_id, owner_id=self._user_id))
                if self.limit is not None:
                    if self.comments.qsize == self.limit:
                        return
        users = await self._state.http.fetch_profiles(to_fetch)
        for user in users:
            author = User(state=self._state, data=user)
            for comment in self.comments._queue:
                if comment.author == author.id:
                    comment.author = author

    async def next(self):
        if self.comments.empty():
            await self.fill_comments()
        return self.comments.get_nowait()


class TradesIterator(AsyncIterator):
    __slots__ = ('trades', '_active_only', '_sent', '_received') + AsyncIterator.__slots__

    def __init__(self, state, limit, before, after, active_only, sent, received):
        super().__init__(state, limit, before, after)
        self._active_only = active_only
        self._sent = sent
        self._received = received
        self.trades = asyncio.Queue()

    async def fill_trades(self):
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
                self.trades.put_nowait(trade)
            if self.limit is not None:
                if self.trades.qsize == self.limit:
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
                self.trades.put_nowait(trade)
            if self.limit is not None:
                if self.trades.qsize == self.limit:
                    return

    async def next(self):
        if self.trades.empty():
            await self.fill_trades()
        return self.trades.get_nowait()
