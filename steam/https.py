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

import asyncio
import logging
from base64 import b64encode
from binascii import hexlify
from os import urandom as random_bytes
from time import time
from typing import Union

import aiohttp
import rsa
from Cryptodome.Hash import SHA1
from yarl import URL as URL_CONVERTER

from . import __version__
from .enums import URL
from .errors import LoginError, InvalidCredentials, HTTPException
from .guard import generate_one_time_code
from .state import State
from .user import User, ClientUser, SteamID

log = logging.getLogger(__name__)


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    def __init__(self, loop: asyncio.AbstractEventLoop, session: aiohttp.ClientSession, client):
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
            self.session = aiohttp.ClientSession(
                loop=self.loop,
                headers={"User-Agent": f'steam.py/{__version__}'}
            )

    async def login(self, username: str, password: str, shared_secret: str):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        login_response = await self._send_login_request()
        await self._check_for_captcha(login_response)
        login_response = await self._enter_steam_guard_if_necessary(login_response)
        await self._assert_valid_credentials(login_response)

        self.session_id = hexlify(SHA1.new(random_bytes(24)).digest())[:24].decode('ascii')
        await self._perform_redirects(login_response)

        new_cookies = self._copy_cookies(URL.STORE[8:], URL.COMMUNITY[8:])
        self.session.cookie_jar.update_cookies(new_cookies, URL_CONVERTER(URL.COMMUNITY))
        self.client.dispatch('login')
        self.session.cookie_jar.filter_cookies(URL.COMMUNITY)

        self._steam_id = SteamID(login_response['transfer_parameters']['steamid'])
        data = await self.mini_profile(self._steam_id)
        self._user = ClientUser(self.state, data)

    def _copy_cookies(self, prev_domain, new_domain):
        prev_cookies = self.session.cookie_jar.filter_cookies(prev_domain)

        self.session.cookie_jar.update_cookies(cookies={'sessionid': self.session_id})
        for cookie in prev_cookies:
            cookie['domain'] = new_domain
        return prev_cookies

    async def logout(self) -> None:
        log.debug('Logging out of session')
        await self.session.post(f'{URL.STORE}/login/logout/')
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
            request = await self.session.post(f'{URL.STORE}/login/getrsakey/',
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
            return await self.session.post(f'{URL.STORE}/login/dologin/', data=data, timeout=15)
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

    async def _fetch_home_page(self) -> aiohttp.ClientResponse:
        return await self.session.post(f'{URL.COMMUNITY}/my/home/')

    async def mini_profile(self, user: Union[User, SteamID]) -> dict:
        post = await self.session.get(
            url=f'{URL.COMMUNITY}/miniprofile/{user.as_steam3[5:-1]}/json')
        return await post.json()

    async def add_user(self, user: User) -> aiohttp.ClientResponse:
        """Add a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 0
        }
        return await self.session.get(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', params=data)

    async def remove_user(self, user: User) -> aiohttp.ClientResponse:
        """Remove a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/RemoveFriendAjax', params=data)

    async def block_user(self, user: User) -> aiohttp.ClientResponse:
        """Block a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 1
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', params=data)

    async def unblock(self, user: User) -> aiohttp.ClientResponse:
        """Unblock a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 0
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', params=data)

    async def accept_user_invite(self, user: User):
        """Accept an invite from a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 1
        }
        resp = await self.session.get(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', params=data)
        return resp

    async def decline_user_invite(self, user: User):
        """Decline an invite from a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 0
        }
        return await self.session.get(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', params=data)
