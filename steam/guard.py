# -*- coding: utf-8 -*-

"""
MIT License

Copyright (c) 2016 Michał Bukowski gigibukson@gmail.com
Copyright (c) 2017 Nate the great

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

This contains a copy of
https://github.com/bukson/steampy/blob/master/steampy/guard.py
and
https://github.com/Zwork101/steam-trade/blob/master/pytrade/confirmations.py
with extra doc-strings and it's slightly sped up.
"""

import base64
import hmac
import logging
import re
import struct
from hashlib import sha1
from time import time

from bs4 import BeautifulSoup

from . import errors
from .models import URL

log = logging.getLogger(__name__)


def generate_one_time_code(shared_secret: str, timestamp: int = int(time())) -> str:
    """Generate a Steam Guard code for signing in.

    Parameters
    -----------
    shared_secret: :class:`str`
        Identity secret from steam guard.
    timestamp: Optional[:class:`int`]
        The unix timestamp to generate the key for.

    Returns
    --------
    :class:`str`
        The desired 2FA code for the timestamp.
    """
    time_buffer = struct.pack('>Q', timestamp // 30)  # pack as Big endian, uint64
    time_hmac = hmac.new(base64.b64decode(shared_secret), time_buffer, digestmod=sha1).digest()
    begin = ord(time_hmac[19:20]) & 0xf
    full_code = struct.unpack('>I', time_hmac[begin:begin + 4])[0] & 0x7fffffff  # unpack as Big endian uint32
    chars = '23456789BCDFGHJKMNPQRTVWXY'
    code = []
    for _ in range(5):
        full_code, i = divmod(full_code, len(chars))
        code.append(chars[i])
    return ''.join(code)  # faster than string concatenation


def generate_confirmation_key(identity_secret: str, tag: str, timestamp: int = int(time())) -> str:
    """Generate a trade confirmation key.

    Parameters
    -----------
    identity_secret: :class:`str`
        Identity secret from steam guard.
    tag: :class:`str`
        Tag to encode to.
    timestamp: Optional[:class:`int`]
        The time to generate the key for.

    Returns
    --------
    :class:`bytes`
        Confirmation key for the set timestamp.
    """
    buffer = f'{struct.pack(">Q", timestamp)}{tag.encode("ascii")}'
    return base64.b64encode(hmac.new(base64.b64decode(identity_secret), buffer, digestmod=sha1).digest()).decode()


def generate_device_id(steam_id: str) -> str:
    """
    Parameters
    -----------
    steam_id: :class:`str`
        The steam id to generate the id for

    Returns
    --------
    :class:`str`
        The device id
    """
    # It works, however it's different that one generated from mobile app

    hexed_steam_id = sha1(steam_id.encode('ascii')).hexdigest()
    partial_id = [
        hexed_steam_id[:8],
        hexed_steam_id[8:12],
        hexed_steam_id[12:16],
        hexed_steam_id[16:20],
        hexed_steam_id[20:32]
    ]
    return f'android:{"-".join(partial_id)}'


def parse_token(url: str):
    return re.search(r"https?://(?:www.)?steamcommunity.com/tradeoffer/new/\?partner=(?:\d+)(?:&|&amp;)"
                     r"token=(?P<token>[a-zA-Z0-9-_]+)", url)


class Confirmation:
    def __init__(self, manager, state, offer_id, confirmation_id, data_key, creator):
        self.manager = manager
        self._state = state
        self.id = int(offer_id.split('conf')[1])
        self.confirmation_id = confirmation_id
        self.data_key = data_key
        self.tag = f'details{self.id}'
        self.creator = creator

    def _confirm_params(self, tag):
        return {
            'p': generate_device_id(self.manager.id64),
            'a': self.manager.id,
            'k': generate_confirmation_key(tag, self.manager.identity_secret),
            't': int(time()),
            'm': 'android',
            'tag': tag
        }

    async def confirm(self):
        params = self._confirm_params('allow')
        params['op'] = 'allow'
        params['cid'] = self.confirmation_id
        params['ck'] = self.data_key
        return await self._state.request('GET', url=f'{self.manager.BASE}/ajaxop', params=params)

    async def cancel(self):
        params = self._confirm_params('cancel')
        params['op'] = 'cancel'
        params['cid'] = self.confirmation_id
        params['ck'] = self.data_key
        return await self._state.request('GET', url=f'{self.manager.BASE}/ajaxop', params=params)

    async def details(self):
        params = self._confirm_params(self.tag)
        resp = await self._state.request('GET', url=f'{self.manager.BASE}/details/{self.id}', params=params)
        return resp['html']


class ConfirmationManager:
    BASE = f'{URL.COMMUNITY}/mobileconf/conf'

    def __init__(self, state, id64):
        self._state = state
        self.identity_secret = state.client.identity_secret
        self.id64 = id64

    def _create_confirmation_params(self, tag):
        return {
            'p': generate_device_id(self.id64),
            'a': self.id64,
            'k': generate_confirmation_key(self.identity_secret, tag),
            't': int(time()),
            'm': 'android',
            'tag': tag
        }

    async def get_confirmations(self):
        params = self._create_confirmation_params('conf')
        headers = {'X-Requested-With': 'com.valvesoftware.android.steam.community'}
        resp = await self._state.request('GET', f'{self.BASE}/conf', params=params, headers=headers)
        if 'Oh nooooooes!' in resp:
            raise errors.ConfirmationError
        soup = BeautifulSoup(resp, 'html.parser')
        if soup.select('#mobileconf_empty'):
            return []
        to_confirm = []
        for confirmation in soup.select('#mobileconf_list .mobileconf_list_entry'):
            offer_id = confirmation['id']
            confirmation_id = confirmation['data-confid']
            key = confirmation['data-key']
            creator = confirmation.get('data-creator')
            to_confirm.append(Confirmation(self, self._state, offer_id, confirmation_id, key, creator))
        return to_confirm

    async def get_trade_confirmation(self, trade_id, confirmations=None):
        if confirmations is None:
            confirmations = await self.get_confirmations()
        for confirmation in confirmations:
            if confirmation.creator == trade_id:
                return confirmation
        return None