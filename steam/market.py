# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 offish
Copyright (c) 2020 Gobot1234

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

This contains an async version of https://github.com/offish/steam_community_market
Thanks confern for letting me use this :D
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import List, Awaitable, Mapping, Any, Union

from bs4 import BeautifulSoup

from . import utils, errors
from .enums import ECurrencyCode, EMarketListingState
from .game import Game
from .http import HTTPClient, json_or_text
from .models import URL
from .trade import Asset

__all__ = (
    'Listing',
    'PriceOverview',
)

log = logging.getLogger(__name__)


def convert_items(item_names: Union[List[str], str],
                  games: Union[List[Game], Game],
                  prices: List[float] = None):
    items = []
    if isinstance(games, Game):  # this is for the same game items
        if prices is None:
            for name in item_names:
                items.append(FakeItem(name, games))
        else:
            for name, price in zip(item_names, prices):
                items.append((FakeItem(name, games), price))
    elif isinstance(games, list):
        if prices is None:
            if len(item_names) == len(games):  # this is for funky lists
                for name, game in zip(item_names, games):
                    items.append(FakeItem(name, game))
            else:
                raise IndexError('item_names and games need to have the same length')
        else:
            if len(item_names) == len(games) == len(prices):
                for name, game, price in zip(item_names, games, prices):
                    items.append((FakeItem(name, game), price))
            else:
                raise IndexError('item_names and games need to have the same length')

    return items


class FakeItem:
    __slots__ = ('name', 'game', 'app_id')

    def __init__(self, name: str, game: Game):
        self.name = name.replace('/', '-')
        self.game = game
        self.app_id = game.app_id

    def __repr__(self):
        return f"FakeItem name={self.name!r} app_id={self.app_id}"


class PriceOverview:
    """Represents the data received from https://steamcommunity.com/market/priceoverview

    Attributes
    -------------
    volume: :class:`int`
        The amount of items are currently on the market.
    lowest_price: :class:`float`
        The lowest price observed by the market.
    median_price: :class:`float`
        The median price observed by the market.
    """

    __slots__ = ('volume', 'lowest_price', 'median_price')

    def __init__(self, data: dict):
        self.volume = int(data['volume'].replace(',', ''))
        search = re.search(r'[^\d]*(\d*)[.,](\d*)', data['lowest_price'])
        self.lowest_price = float(f'{search.group(1)}.{search.group(2)}') \
            if search.group(2) else float(search.group(1))
        search = re.search(r'[^\d]*(\d*)[.,](\d*)', data['median_price'])
        self.median_price = float(f'{search.group(1)}.{search.group(2)}') \
            if search.group(2) else float(search.group(1))

    def __repr__(self):
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in self.__slots__]
        return f"<PriceOverview {' '.join(resolved)}>"


class Listing(Asset):
    """Represents a Steam Market listing

    Attributes
    ----------
    name: :class:`str`
        The name of the listing's item.
    user_pays: Optional[:class:`float`]
        The amount the user would pay for the item.
    we_receive: Optional[:class:`float`]
        The amount the ClientUser would receive for a sale of the item.
    price: Optional[:class:`float`]
        The amount the amount the item was bought or sold for, this only applies
        to listings from :meth:`~steam.Client.listing_history`.
    id: :class:`int`
        The listing's ID.
    state: :class:`~steam.EMarketListingState`
        The state of the listing.
    colour: Optional[:class:`int`]
        The colour of the listing's item.
    market_name: Optional[:class:`str`]
        The market_name of the listing's item.
    descriptions: Optional[:class:`str`]
        The listing's item's description.
    type: Optional[:class:`str`]
        The type of the listing's item.
    tags: Optional[:class:`str`]
        The tags of the listing's item.
    icon_url: Optional[:class:`str`]
        The icon_url of the listing's item. Uses the large (184x184 px) image url.
    """

    def __init__(self, state, data):
        super().__init__(data)
        self._state = state
        self._from_data(data)

    def _from_data(self, data):
        self.name = data['name']
        self.user_pays = data.get('user_pays')
        self.we_receive = data.get('we_receive')
        self.price = data.get('price')  # for iterator
        self.id = data['id']
        self.state = EMarketListingState(data['status'])
        self.game = Game(app_id=data['appid'], context_id=int(data['contextid']))
        self.colour = int(data['name_color'], 16) if 'name_color' in data else None
        self.market_name = data.get('market_name')
        self.descriptions = data.get('descriptions')
        self.type = data.get('type')
        self.tags = data.get('tags')
        self.icon_url = f'{URL.COMMUNITY}-a.akamaihd.net/economy/image/{data["icon_url_large"]}' \
            if 'icon_url_large' in data else None
        self._is_tradable = bool(data.get('tradable', False))

    def __repr__(self):
        attrs = (
            'name', 'id'
        ) + Asset.__slots__
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Listing {' '.join(resolved)}>"

    def __hash__(self):
        return hash(self.id)

    def is_tradable(self) -> bool:
        """:class:`bool`: Whether the listing's item is tradable."""
        return self._is_tradable


class MarketClient(HTTPClient):
    """Represents a client connection that interacts with the Steam Market.
    Practically it works as an extension to the HTTPClient but for market interactions.

    Parameters
    ----------
    currency: Union[:class:`~steam.ECurrencyCode`, :class:`int`, :class:`str`]
        Sets the currency for requests. :attr:`~steam.ECurrencyCode.USD` / United State Dollars is default.
        Pass this as a ``keyword argument`` to the :class:`~steam.Client` initialization.
    """

    BASE = f'{URL.COMMUNITY}/market'

    def __init__(self, currency, loop, session, client):
        super().__init__(loop, session, client)
        self.times = []

        if isinstance(currency, ECurrencyCode):
            self.currency = currency.value
        elif isinstance(currency, str):
            self.currency = ECurrencyCode[currency.upper()].value
        elif isinstance(currency, int):
            self.currency = ECurrencyCode(currency).value
        else:
            self.currency = 1
        log.info(f'Currency is set to {self.currency}')

        self._loop.create_task(self._remover())

    async def request(self, method: str, url: str, **kwargs) -> Any:  # adapted from d.py
        kwargs['headers'] = {
            "User-Agent": self.user_agent,
            **kwargs.get('headers', {})
        }

        is_price_overview = kwargs.pop('is_price_overview', False)
        if is_price_overview:  # do rate-limit handling for price-overviews
            now = datetime.utcnow()
            if len(self.times) <= 20:
                self.times.append(now)
            else:
                await asyncio.sleep((timedelta(minutes=1) - (now - self.times[0])).total_seconds())

        async with self._lock:
            for tries in range(5):
                async with self._session.request(method, url, **kwargs) as r:
                    payload = kwargs.get('payload')
                    params = kwargs.get('params')
                    log.debug(self.REQUEST_LOG.format(
                        method=method,
                        url=url,
                        connective='with' if payload is not None or params is not None else '',
                        payload=f'\nPAYLOAD: {payload}\n' if payload else '',
                        params=f'\nPARAMS: {params}\n' if params else '',
                        status=r.status)
                    )

                    # even errors have text involved in them so this is safe to call
                    data = await json_or_text(r)

                    # the request was successful so just return the text/json
                    if 300 > r.status >= 200:
                        log.debug(f'{method} {url} has received {data}')
                        return data

                    # we are being rate limited, we shouldn't hit this however
                    if r.status == 429:
                        try:
                            await asyncio.sleep(float(r.headers['X-Retry-After']))
                        except KeyError:
                            await asyncio.sleep(2 ** tries)
                        continue

                    if r.status == 500 and is_price_overview:  # this endpoints equivalent of a 404
                        raise errors.NotFound(r, data)
                    # we've received a 500 or 502, an unconditional retry
                    if r.status in {500, 502}:
                        await asyncio.sleep(1 + tries * 3)
                        continue

                    # the usual error cases
                    if r.status == 403:
                        raise errors.Forbidden(r, data)
                    if r.status == 404:
                        raise errors.NotFound(r, data)
                    else:
                        raise errors.HTTPException(r, data)

            # we've run out of retries, raise
            raise errors.HTTPException(r, data)

    async def _remover(self) -> None:
        while 1:
            one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
            await asyncio.sleep(2)
            for time in self.times:
                if time > one_minute_ago:
                    continue
                self.times.remove(time)

    async def get_price(self, item: FakeItem) -> PriceOverview:
        params = {
            'appid': item.app_id,
            'market_hash_name': item.name,
            'currency': self.currency
        }
        return PriceOverview(await self.request('GET', url=f'{self.BASE}/priceoverview',
                                                is_price_overview=True, params=params))

    async def get_prices(self, items) -> Mapping[str, PriceOverview]:
        return {item.name: await self.get_price(item) for item in items}

    async def get_listings(self, pages: int) -> List[dict]:
        ret = []
        for start in range(0, pages, 100):
            params = {
                "start": start,
                "count": 100
            }
            resp = await self.request('GET', url=f'{self.BASE}/mylistings', params=params)
            matches = re.findall(r"CreateItemHoverFromContainer\( \w+, 'mylisting_(\d+)_"
                                 r"\w+', \d+, '\d+', '(\d+)', \d+ \);", resp["hovers"])
            # we need the listing id and the asset id(???)
            prices = []
            soup = BeautifulSoup(resp['results_html'], 'html.parser')
            for listing in soup.find_all('div', attrs={"class": 'market_listing_row'}):
                listing_id = re.findall(r'mylisting_(\d+)_\w+', str(listing))
                findall = re.findall(r'[^\d]*(\d+)(?:[.,])(\d+)', listing.text, re.UNICODE)
                price = float(f'{findall[0][0]}.{findall[0][1]}')
                to_receive = float(f'{findall[1][0]}.{findall[1][1]}')
                prices.append((listing_id, price, to_receive))

            for context_id in resp['assets'].values():
                for listings in context_id.values():
                    for listing in listings.values():
                        listing['assetid'] = listing['id']  # we need to swap the ids around
                        listing['id'] = int(utils.find(lambda m: m[1] == listing['id'], matches)[0])
                        _, listing['user_pays'], listing['we_receive'] = \
                            utils.find(lambda p: int(p[0][0]) == listing['id'], prices)
                        ret.append(listing)
        return ret

    def get_pages(self) -> Awaitable:
        params = {
            "start": 0,
            "count": 1
        }
        return self.request('GET', url=f'{self.BASE}/mylistings', params=params)
