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

from aiohttp import ClientSession

from .enums import ECurrencyCode, URL

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


def fix_name(name: str) -> Union[bool, str]:
    """Sterilize the name of an item to be able to request the price.

    Parameters
    ----------
    name: :class:`str`
        The name of the item to sterilize.

    Returns
    -------
    price: :class:`typing.Union`[:class:`bool`, :class:`str`]
        The fixed name.
    """
    if isinstance(name, str):
        return name.replace('/', '-')
    raise TypeError('name is not a string')


class Market:
    """Represents a client connection that interacts with the Steam Market.
    This class is used to interact with the Steam Market.

    Parameters
    ----------
    session: :py:class:`aiohttp.ClientSession`
        The session used to make web requests.
    currency: :py:class:`typing.Union`[:class:`int`, :class:`str`]
        Sets the currency to be outputted.
        1, 'USD' or leave empty for American Dollars.
    """

    def __init__(self, session: ClientSession, currency: Union[int, str] = 1):
        if isinstance(currency, str):
            currency = currency.upper()

            if currency in [i.name for i in ECurrencyCode]:
                currency = ECurrencyCode[currency].value
            else:
                raise IndexError(f'Currency {currency} not found')

        if isinstance(currency, int):
            if currency > 32 or currency < 1:
                currency = 1
        else:
            currency = 1

        self.currency = currency
        self.session = session
        self.url = f'{URL.COMMUNITY}/market/priceoverview'

    async def request(self, url: str, payload: dict) -> dict:
        log.debug(f'Requesting price info for with {payload}')
        async with self.session.post(url=url, params=payload) as r:
            if r.status == 200:
                return await r.json()
            else:
                return {'success': False, 'status_code': r.status, 'text': await r.text()}

    async def get_price(self, name: str, app_id: int) -> dict:
        """Gets the price(s) and volume sales of an item.

        Parameters
        ----------
        name: :class:`str`
            The name of the item how it appears on the Steam Community Market.
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

        payload = {
            'appid': app_id,
            'market_hash_name': name,
            'currency': self.currency
        }

        return await self.request(self.url, payload)

    async def get_prices(self, names: list, app_id: Union[int, list]) -> dict:
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
            raise TypeError('Names must be list')

        if isinstance(app_id, int):
            for name in names:
                prices[name] = await self.get_price(name, app_id)

        elif isinstance(app_id, list):
            if len(names) == len(app_id):
                for i, name in enumerate(names):
                    print(name, app_id[i])
                    prices[name] = await self.get_price(name, app_id[i])
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

        prices = {}

        if not isinstance(items, dict):
            raise TypeError('items must be dict')

        for item in items:
            prices[item] = await self.get_price(item, items[item]['appid'])
        return prices
