# -*- coding: utf-8 -*-

"""
MIT License

Copyright (c) 2020 offish

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

This is an async version of https://github.com/offish/steam_community_market
Thanks confern for letting me use this :D
"""

import logging

from .enums import ECurrencyCode
from .models import Game, URL

log = logging.getLogger(__name__)


def has_valid_name(name: str):
    if isinstance(name, str):
        return '/' not in name
    return False


def fix_name(name: str):
    if isinstance(name, str):
        return name.replace('/', '-')
    raise TypeError('name is not a string')


class FakeItem:
    __slots__ = ('name', 'game', 'app_id')

    def __init__(self, name: str, game: Game):
        self.name = name
        self.game = game
        self.app_id = game.app_id


class PriceOverview:
    """Represents the data received from https://steamcommunity.com/market/priceoverview

    Attributes
    -------------
    currency: :class:`str`
        The currency identifier for the item eg. "$" or "£".
    volume: :class:`int`
        The amount of items are currently on the market.
    lowest_price: :class:`float`
        The lowest price observed by the market.
    median_price: :class:`float`
        The median price observed by the market.
    """

    __slots__ = ('currency', 'volume', 'lowest_price', 'median_price')

    def __init__(self, data):
        self.currency = data['lowest_price'][:1]
        self.volume = int(data['volume'].replace(',', ''))
        self.lowest_price = float(data['lowest_price'][1:])
        self.median_price = float(data['median_price'][1:])


def convert_items(item_names, games, prices=None):
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


class Market:
    """Represents a client connection that interacts with the Steam Market.
    This class is used to interact with the Steam Market.

    Parameters
    ----------
    currency: Union[:class:`~steam.ECurrencyCode`, :class:`int`, :class:`str`]
        Sets the currency for requests. :attr:`~steam.ECurrencyCode.USD`/United State Dollars is default.
        Pass this as a ``kwarg`` to the :class:`~steam.Client` initialization.
    """

    BASE = f'{URL.COMMUNITY}/market'

    def __init__(self, http, currency):
        self.http = http

        if isinstance(currency, ECurrencyCode):
            self.currency = currency.value
        elif isinstance(currency, str):
            self.currency = ECurrencyCode[currency.upper()].value
        elif isinstance(currency, int):
            self.currency = ECurrencyCode(currency).value
        else:
            self.currency = 1

    async def fetch_price(self, item_name, game):
        item = FakeItem(fix_name(item_name), game)
        data = {
            'appid': item.app_id,
            'market_hash_name': item.name,
            'currency': self.currency
        }

        return PriceOverview(await self.http.request('POST', f'{self.BASE}/priceoverview', data=data))

    async def fetch_prices(self, item_names, games):
        items = convert_items(item_names, games)

        return {item: await self.fetch_price(item.name, item.game) for item in items}

    def create_listing(self, item_name, game, *, price):
        item = FakeItem(fix_name(item_name), game)
        data = {
            "sessionid": self.http.session_id,
            "currency": self.currency,
            "appid": item.app_id,
            "market_hash_name": item.name,
            "price_total": price * 100,
            "quantity": 1
        }

        headers = {"Referer": f'{URL.COMMUNITY}/market/listings/{game.app_id}/{item.name}'}

        self.http.request('POST', f'{URL.COMMUNITY}/market/createbuyorder/', data=data, headers=headers)

    def create_listings(self, item_names, games, *, prices):
        to_list = []
        items = convert_items(item_names, games, prices)
        for (item, price) in items:
            final_price = price * items.count((item, price))
            for (_, __) in items:
                items.remove((item, price))
            to_list.append((item, final_price))
        for (item, price) in items:
            to_list.append((item, price))

        for (item, price) in to_list:
            data = {
                "sessionid": self.http.session_id,
                "currency": self.currency,
                "appid": item.app_id,
                "market_hash_name": item.name,
                "price_total": price * 100,
                "quantity": 1
            }
            headers = {"Referer": f'{URL.COMMUNITY}/market/listings/{item.app_id}/{item.name}'}

            self.http.request('POST', f'{URL.COMMUNITY}/market/createbuyorder/', data=data, headers=headers)
