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

import json
import re

from aiohttp import InvalidURL, ClientSession

from steam.utils.models import URL


def url_to_ID64(url: str) -> int:
    return int(re.search(r'profiles/([0-9]*)', url).group(0)[9:])


async def name_to_ID64(session: ClientSession, name: str) -> int:
    try:
        page = await session.get(url=f'{URL.COMMUNITY}/id/{name}')
    except InvalidURL:
        raise InvalidURL(f'{name} is not a valid Steam user')
    else:  # Give me an API key this is very bad
        _dict = re.search(r"""g_rgProfileData = {(?:.*)};""", await page.text()).group(0)  # getting the dict
        return json.loads(  # formatting dict to remove description as it's HTML and brakes JSONs
            '{}}'.format(re.split(r""","summary":(?:.*)};""", _dict.replace("g_rgProfileData = ", ""))[0])
        )['steamid']


async def ID64_to_name(session: ClientSession, ID64: int) -> str:
    try:
        page = await session.get(url=f'{URL.COMMUNITY}/profiles/{ID64}')
    except InvalidURL:
        raise
    else:  # this method isn't as bad
        return re.split(rf'{URL.COMMUNITY}/id/', str(page.url))[1][:-1]


def ID64_to_ID2(ID64: int) -> str:
    return f'STEAM_{int(bin(ID64)[:1], 2)}:{int(bin(ID64)[-1:], 2)}:{int(bin(ID64)[27:-1], 2)}'


def ID2_to_ID3(ID2: str) -> str:
    return f'[U:1:{int((bin(int(ID2[10:]) * 0b10)), 2)}]'


def ID64_to_ID3(ID64: int) -> str:
    return ID2_to_ID3(ID64_to_ID2(ID64))

