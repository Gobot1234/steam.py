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
import struct
from hashlib import sha1
from time import time

from bs4 import BeautifulSoup

from . import utils
from .errors import InvalidCredentials, AuthenticatorError
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


def generate_confirmation_code(identity_secret: str, tag: str, timestamp: int = int(time())) -> str:
    """Generate a trade confirmation code.

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
    :class:`str`
        Confirmation code for the set timestamp.
    """
    buffer = struct.pack('>Q', timestamp) + tag.encode('ascii')
    return base64.b64encode(hmac.new(base64.b64decode(identity_secret), buffer, digestmod=sha1).digest()).decode()


def generate_device_id(id64: str) -> str:
    """
    Parameters
    -----------
    id64: :class:`str`
        The 64 bit steam id to generate the device id for.

    Returns
    --------
    :class:`str`
        The device id
    """
    # It works, however it's different that one generated from mobile app

    hexed_steam_id = sha1(id64.encode('ascii')).hexdigest()
    partial_id = [
        hexed_steam_id[:8],
        hexed_steam_id[8:12],
        hexed_steam_id[12:16],
        hexed_steam_id[16:20],
        hexed_steam_id[20:32]
    ]
    return f'android:{"-".join(partial_id)}'


class Confirmation:
    def __init__(self, state, id, data_confid, data_key, manager, creator):
        self.state = state
        self.id = id.split('conf')[1]
        self.data_confid = data_confid
        self.data_key = data_key
        self.tag = f'details{self.id}'
        self.manager = manager
        self.creator = creator

    def __repr__(self):
        return f"<Confirmation id={self.id}>"

    def _confirm_params(self, tag):
        timestamp = int(time())
        return {
            'p': self.manager.device_id,
            'a': str(self.manager.id64),
            'k': self.manager.generate_confirmation(tag, timestamp),
            't': timestamp,
            'm': 'android',
            'tag': tag
        }

    def confirm(self):
        params = self._confirm_params('allow')
        params['op'] = 'allow'
        params['cid'] = self.data_confid
        params['ck'] = self.data_key
        return self.state.request('GET', f'{self.manager.BASE}/ajaxop', params=params)

    def cancel(self):
        params = self._confirm_params('cancel')
        params['op'] = 'cancel'
        params['cid'] = self.data_confid
        params['ck'] = self.data_key
        return self.state.request('GET', f'{self.manager.BASE}/ajaxop', params=params)

    def details(self):  # need to do ['html'] for the good stuff
        params = self._confirm_params(self.tag)
        return self.state.request('GET', f'{self.manager.BASE}/details/{self.id}', params=params)


class ConfirmationManager:
    BASE = f'{URL.COMMUNITY}/mobileconf'

    def __init__(self, state):
        self.state = state
        self.identity_secret = state.client.identity_secret
        self.id64 = state.client.user.id64
        self.confirmations = []

    def create_confirmation_params(self, tag):
        timestamp = int(time())
        return {
            'p': self.device_id,
            'a': self.id64,
            'k': self.generate_confirmation(tag, timestamp),
            't': timestamp,
            'm': 'android',
            'tag': tag
        }

    async def get_confirmations(self):
        params = self.create_confirmation_params('conf')
        headers = {'X-Requested-With': 'com.valvesoftware.android.steam.community'}
        confs = await self.state.request('GET', f'{self.BASE}/conf', params=params, headers=headers)

        if 'incorrect Steam Guard codes.' in confs:
            raise InvalidCredentials('identity secret is incorrect, or time is de-synced')
        elif 'Oh nooooooes!' in confs:
            raise AuthenticatorError

        soup = BeautifulSoup(confs, 'html.parser')
        if soup.select('#mobileconf_empty'):
            return []
        for confirmation in soup.select('#mobileconf_list .mobileconf_list_entry'):
            id = confirmation['id']
            confid = confirmation['data-confid']
            key = confirmation['data-key']
            creator = confirmation.get('data-creator')
            self.confirmations.append(Confirmation(self.state, id, confid, key, self, creator))
        return self.confirmations

    async def get_confirmation(self, id):
        if id in [int(confirmation.creator) for confirmation in self.confirmations]:
            return utils.find(lambda c: int(c.creator) == id, self.confirmations)
        await self.get_confirmations()
        if id in [int(confirmation.creator) for confirmation in self.confirmations]:
            return utils.find(lambda c: int(c.creator) == id, self.confirmations)
        return None

    @property
    def device_id(self):
        return generate_device_id(str(self.id64))

    def generate_confirmation(self, tag, timestamp):
        return generate_confirmation_code(self.identity_secret, tag, timestamp)
