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
from datetime import datetime
from typing import Union, List

from .enums import ECurrencyCode, URL, Game

log = logging.getLogger(__name__)


def has_valid_name(name: str):
    """Check if the name of an item is serializable.

    Parameters
    ----------
    name: :class:`str`
        The name of the item to check.

    Returns
    -------
    is_valid: :class:`bool`
        Returns if an can be sterilized.
    """
    if isinstance(name, str):
        return '/' not in name
    return False


def fix_name(name: str):
    """Sterilize the name of an item to be able to request the price.

    Parameters
    ----------
    name: :class:`str`
        The name of the item to sterilize.

    Returns
    -------
    price: :class:`str`
        The fixed name.
    """
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
    """

    BASE = f'{URL.COMMUNITY}/market'

    def __init__(self, http, currency: Union[ECurrencyCode, int, str] = ECurrencyCode.USD):
        self.http = http

        if isinstance(currency, ECurrencyCode):
            self.currency = currency.value
        elif isinstance(currency, str):
            currency = currency.upper()
            if currency in [item.name for item in ECurrencyCode]:
                self.currency = ECurrencyCode[currency].value
            else:
                raise IndexError(f'Currency {currency} not found')
        elif isinstance(currency, int):
            if currency > 32 or currency < 1:
                self.currency = 1
            else:
                raise IndexError(f'Currency {currency} not found')
        else:
            self.currency = 1

    async def fetch_price(self, item_name: str, game: Game):
        """Gets the price(s) and volume sales of an item.

        Parameters
        ----------
        item_name: str
            The name of the item to fetch the price of.
        game: :class:`~steam.enums.Game`
            The game the item is from.

        Returns
        -------
        price_overview: :class:`PriceOverview`
            A class to represent the data from these transactions
        """
        item = FakeItem(fix_name(item_name), game)
        data = {
            'appid': item.app_id,
            'market_hash_name': item.name,
            'currency': self.currency
        }

        return PriceOverview(await self.http.request('POST', f'{self.BASE}/priceoverview', data=data))

    async def fetch_prices(self, item_names: List[str], games: Union[List[Game], Game]):
        """Get the price(s) and volume of each item in the list.

        Parameters
        ----------
        item_names: List[str]
            A list of the items to get the prices for.
        games: Union[List[Game], Game]
            A list of :class:`~steam.Game`s or :class:`~steam.Game` the items are from.

        Returns
        -------
        prices: :class:`dict`
            A dictionary of the prices with the mapping of {:class:`~steam.Item`: :class:`PriceOverview`}
        """
        items = convert_items(item_names, games)

        prices = {item: await self.fetch_price(item.name, item.game) for item in items}
        return prices

    async def fetch_price_history(self, item_name: str, game: Game, *, limit=100):
        example = {
            "success": True,
            "price_prefix": "\u00a3",
            "prices": [
                [datetime.strptime("%b %d %Y %H: %z +0"), 1.893, "341"]
            ]
        }
        params = {
            'appid': game.app_id,
            'currency': self.currency,
            'market_hash_name': item_name
        }
        response = await self.http.request('GET', url=f'{self.BASE}/pricehistory', params=params)
        return response

    async def create_market_listing(self, item_name: str, game: Game, *, price: float):
        """Creates a market listing for an item.
        .. note::
            This could end up getting your account terminated.

        Parameters
        ----------
        item_name: str
            The name of the item to order.
        game: :class:`~steam.enums.Game`
            The game the item is from.
        price: Union[:class:`int`, :class:`float`]
            The price to pay for the item in decimal form.
            eg. $1 = 1.00 or £2.50 = 2.50
        """
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

        await self.http.request('POST', f'{URL.COMMUNITY}/market/createbuyorder/', data=data, headers=headers)

    async def create_market_listings(self, item_names: List[str], games: Union[List[Game], Game],
                                     prices: Union[List[Union[int, float]], Union[int, float]]):
        """Creates market listing for items.
        .. note::
            This could end up getting your account terminated.

        Parameters
        ----------
        item_names: List[str]
            A list of item names to order.
        games: :class:`~steam.enums.Game`
            The game the item(s) is/are from.
        prices: Union[List[Union[:class:`int`, :class:`float`]], Union[:class:`int`, :class:`float`]]
            The price to pay for each item in decimal form.
            eg. $1 = 1.00 or £2.50 = 2.50
        """
        items = convert_items(item_names, games, prices)  # TODO make this support multiple of the same items
        for (item, price) in items:
            data = {
                "sessionid": self.http.session_id,
                "currency": self.currency,
                "appid": item.app_id,
                "market_hash_name": item.name,
                "price_total": price * 100,
                "quantity": 1
            }
            headers = {"Referer": f'{URL.COMMUNITY}/market/listings/{item.app_id}/{item.name}'}

            await self.http.request('POST', f'{URL.COMMUNITY}/market/createbuyorder/', data=data, headers=headers)
