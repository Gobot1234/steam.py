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
from datetime import datetime, timedelta
from typing import (
    Any,
    List,
    Mapping,
    Optional,
    Union
)

from . import errors
from .enums import ECurrencyCode
from .game import Game
from .http import HTTPClient, json_or_text
from .models import URL

__all__ = (
    'PriceOverview',
)

log = logging.getLogger(__name__)


def convert_items(item_names: Union[List[str], str],
                  games: Union[List[Game], Game]) -> List['FakeItem']:
    items = []
    if isinstance(games, Game):  # this is for the same game items
        for name in item_names:
            items.append(FakeItem(name, games))
    elif isinstance(games, list):
        if len(item_names) == len(games):  # this is for funky lists
            for name, game in zip(item_names, games):
                items.append(FakeItem(name, game))
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
    lowest_price: :class:`str`
        The lowest price observed by the market.
    median_price: :class:`str`
        The median price observed by the market.
    """

    __slots__ = ('volume', 'lowest_price', 'median_price')

    def __init__(self, data: dict):
        self.volume = int(data['volume'].replace(',', ''))
        self.lowest_price = data['lowest_price']
        self.median_price = data['median_price']

    def __repr__(self):
        resolved = [f'{attr}={getattr(self, attr)!r}' for attr in self.__slots__]
        return f"<PriceOverview {' '.join(resolved)}>"


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
        if isinstance(currency, str):
            self.currency = ECurrencyCode[currency.upper()].value
        if isinstance(currency, int):
            self.currency = ECurrencyCode(currency).value
        else:
            self.currency = 1
        log.info(f'Currency is set to {self.currency}')

    async def request(self, method: str, url: str, **kwargs) -> Optional[Any]:  # adapted from d.py
        kwargs['headers'] = {
            "User-Agent": self.user_agent,
            **kwargs.get('headers', {})
        }

        is_price_overview = kwargs.pop('is_price_overview', False)
        if is_price_overview:  # do rate-limit handling for price-overviews
            now = datetime.utcnow()
            one_minute_ago = now - timedelta(minutes=1)
            for time in self.times:
                if time > one_minute_ago:
                    continue
                self.times.remove(time)
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
