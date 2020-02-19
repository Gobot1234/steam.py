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
from typing import Union

from .enums import ECurrencyCode, URL, Game

log = logging.getLogger(__name__)


def has_invalid_name(name: str) -> bool:
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
        return '/' in name
    return False


def fix_name(name: str) -> str:
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


class Market:
    """Represents a client connection that interacts with the Steam Market.
    This class is used to interact with the Steam Market and
    shouldn't have instances of it made by library users.

    Parameters
    ----------
    http: :class:`~steam.HTTPClient`
        The session used to make web requests.
    currency: Union[:class:`~steam.ECurrencyCode`, :class:`int`, :class:`str`]
        Sets the currency to be outputted.
        1, 'USD' or leave empty for United State Dollars.
    """
    BASE = f'{URL.COMMUNITY}/market/'

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
                self.currency = currency
        else:
            self.currency = 1

    async def fetch_price(self, name: str, app_id: int) -> dict:
        """Gets the price(s) and volume sales of an item.

        Parameters
        ----------
        name: :class:`str`
            The name of the item as it appears on the
            Steam Community Market.
        app_id: :class:`int`
            The AppID of the item.

        Returns
        -------
        price: :class:`dict`
            A dictionary of the prices.
        """
        if not isinstance(name, str):
            raise TypeError('name must be str')

        if not isinstance(app_id, int):
            raise TypeError('app_id must be int')

        if has_invalid_name(name):
            name = fix_name(name)

        data = {
            'appid': app_id,
            'market_hash_name': name,
            'currency': self.currency
        }

        return await self.http._request('POST', f'{self.BASE}/priceoverview', data=data)

    async def fetch_prices(self, names: list, app_id: Game) -> dict:
        """Get the price(s) and volume of each item in the list.
        If both are lists, then they need to have the same amount of elements.

        Parameters
        ----------
        names: :class:`str`
            A list of item names how each item appears on the Steam Community Market.
        app_id: :class:`str`
            The AppID of the item(s). Either a list or int.

        Returns
        -------
        prices: :class:`dict`
            A dictionary of the prices.
        """
        prices = {}

        if not isinstance(names, list):
            raise TypeError('names must be list')

        if isinstance(app_id, int):
            for name in names:
                prices[name] = await self.fetch_price(name, app_id)

        elif isinstance(app_id, list):
            if len(names) == len(app_id):
                for i, name in enumerate(names):
                    prices[name] = await self.fetch_price(name, app_id[i])
            else:
                raise IndexError('names and app_id needs to have the same length')

        return prices

    async def get_prices_from_dict(self, items: dict) -> dict:
        """
        Gets the price(s) and volume of each item in the list.

        Parameters
        ----------
        items: :class:`dict
            A dict including item names and AppIDs.

        Returns
        -------
        prices: :class:`dict`
            A dictionary of the prices.
        """
        if not isinstance(items, dict):
            raise TypeError('items must be dict')

        return {item: await self.fetch_price(item, items[item]['appid']) for item in items}

    async def fetch_price_history(self, item: str, game: Game, currency: str = ECurrencyCode.USD) -> dict:
        params = {
            'appid': game.app_id,
            'currency': currency,
            'market_hash_name': item
        }
        response = await self.http._request('GET', url=f'{self.BASE}/pricehistory/', params=params)
        return response
