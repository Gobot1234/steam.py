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

import logging
from asyncio import AbstractEventLoop
from base64 import b64encode
from binascii import hexlify
from os import urandom as random_bytes
from time import time

import rsa
from Cryptodome.Hash import SHA1
from aiohttp import ClientSession, ClientResponse, CookieJar

from . import __version__
from .enums import URL
from .errors import LoginError, InvalidCredentials, HTTPException
from .guard import generate_one_time_code
from .state import State
from .user import User, ClientUser, SteamID

log = logging.getLogger(__name__)


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    def __init__(self, loop: AbstractEventLoop, session: ClientSession, client):
        self.loop = loop
        self.session = session

        self.username = None
        self.password = None
        self.shared_secret = None
        self.one_time_code = None
        self.session_id = None

        self._steam_id = None
        self._user = None

        self.state = State(loop=loop, http=self)
        self.client = client

    def recreate(self):
        if self.session.closed:
            self.session = ClientSession(
                loop=self.loop, cookie_jar=CookieJar(),
                headers={"User-Agent": f'steam.py/{__version__}'})

    async def login(self, username: str, password: str, shared_secret: str):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        login_response = await self._send_login_request()
        await self._check_for_captcha(login_response)
        login_response = await self._enter_steam_guard_if_necessary(login_response)
        await self._assert_valid_credentials(login_response)
        await self._perform_redirects(login_response)

        self.session_id = hexlify(SHA1.new(random_bytes(32)).digest())[:32].decode('ascii')
        self.session.cookie_jar.update_cookies(cookies={'sessionid': self.session_id})
        self.client.dispatch('login')

        self._steam_id = SteamID(login_response['transfer_parameters']['steamid'])
        data = await self.mini_profile(self._steam_id.as_steam3)
        self._user = ClientUser(self.state, data)

    async def logout(self) -> None:
        log.debug('Logging out of session')
        await self.session.post(f'{URL.COMMUNITY}/login/logout/')
        await self.session.close()
        self.client.dispatch('logout')

    async def _send_login_request(self) -> dict:
        rsa_params = await self._fetch_rsa_params()
        rsa_timestamp = rsa_params['rsa_timestamp']
        login_request = await self._send_login(rsa_params, rsa_timestamp)
        return await login_request.json()

    async def _fetch_rsa_params(self, current_repetitions: int = 0) -> dict:
        maximum_repetitions = 5
        data = {'username': self.username,
                'donotcache': int(time() * 1000)}
        try:
            request = await self.session.post(f'{URL.COMMUNITY}/login/getrsakey/',
                                              data=data, timeout=15)
        except Exception as e:
            await self.session.close()
            raise LoginError(e)

        key_response = await request.json()
        try:
            rsa_mod = int(key_response['publickey_mod'], 16)
            rsa_exp = int(key_response['publickey_exp'], 16)
            rsa_timestamp = key_response['timestamp']
            return {'rsa_key': rsa.PublicKey(rsa_mod, rsa_exp),
                    'rsa_timestamp': rsa_timestamp}
        except KeyError:
            if current_repetitions < maximum_repetitions:
                return await self._fetch_rsa_params(current_repetitions + 1)
            else:
                raise ValueError('Could not obtain rsa-key')

    async def _send_login(self, rsa_params: dict, rsa_timestamp: str):
        data = {
            'username': self.username,
            'password': b64encode(rsa.encrypt(self.password.encode('utf-8'), rsa_params['rsa_key'])).decode(),
            "emailauth": '',
            "emailsteamid": '',
            "twofactorcode": self.one_time_code or '',
            "captchagid": '-1',
            "captcha_text": '',
            "loginfriendlyname": 'steam.py bot',
            "rsatimestamp": rsa_timestamp,
            "remember_login": 'true',
            "donotcache": int(time() * 1000),
        }
        try:
            return await self.session.post(f'{URL.COMMUNITY}/login/dologin/', data=data, timeout=15)
        except Exception as e:
            await self.session.close()
            raise HTTPException(e)

    async def _enter_steam_guard_if_necessary(self, login_response: dict) -> dict:
        if login_response['requires_twofactor']:
            self.one_time_code = generate_one_time_code(self.shared_secret)
            return await self._send_login_request()
        return login_response

    async def _perform_redirects(self, response_dict: dict) -> None:
        parameters = response_dict.get('transfer_parameters')
        if parameters is None:
            raise Exception('Cannot perform redirects after login, no parameters fetched')
        for url in response_dict['transfer_urls']:
            await self.session.post(url, data=parameters)

    async def _check_for_captcha(self, login_response: dict) -> None:
        try:
            if login_response['captcha_needed']:
                await self.session.close()
                raise LoginError('Captcha required')
        except KeyError:
            pass

    async def _assert_valid_credentials(self, login_response: dict) -> None:
        if not login_response['success']:
            await self.session.close()
            raise InvalidCredentials(login_response['message'])

    async def _fetch_home_page(self) -> ClientResponse:
        return await self.session.post(f'{URL.COMMUNITY}/my/home/')

    async def block(self, user: User) -> ClientResponse:
        """Block a user using there Steam ID"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 1
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def unblock(self, user: User) -> ClientResponse:
        """Unblock a user using there Steam ID"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 0
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def add_friend(self, user: User) -> ClientResponse:
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 0
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def remove_friend(self, user: User) -> ClientResponse:
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/RemoveFriendAjax', data=data)

    async def mini_profile(self, ID3: str) -> dict:
        post = await self.session.get(
            url=f'https://steamcommunity.com/miniprofile/{ID3[5:-1]}/json')
        return await post.json()
