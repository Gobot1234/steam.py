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
import re
import typing
from base64 import b64encode
from sys import version_info
from time import time

import aiohttp
import rsa

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
        self._loop = loop
        self._session = session
        self._client = client
        self._state = State(loop=loop, http=self)

        self.username = None
        self.password = None
        self.shared_secret = None
        self._one_time_code = None

        self.session_id = None
        self._steam_id = None
        self._user = None
        self._logged_in = False
        self._user_agent = \
            f'steam.py/{__version__} bot (https://github.com/Gobot1234/steam.py), ' \
            f'Python/{version_info[0]}.{version_info[1]}, aiohttp/{aiohttp.__version__}'

    def recreate(self):
        if self._session.closed:
            self._session = aiohttp.ClientSession(loop=self._loop)

    async def login(self, username: str, password: str, shared_secret: str):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        login_response = await self._send_login_request()
        if 'captcha_needed' in login_response.keys():
            raise LoginError('A captcha code is required, please try again later')

        await self._assert_valid_credentials(login_response)
        await self._perform_redirects(login_response)

        self._logged_in = True
        self._client.dispatch('login')

        self._steam_id = SteamID(login_response['transfer_parameters']['steamid'])
        data = await self.mini_profile(self._steam_id)
        self._user = ClientUser(self._state, data)
        await self._final_check()

        return self._session

    def code(self):
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        else:
            return input('Please enter a Steam guard code: ')

    async def logout(self):
        log.debug('Logging out of session')
        await self._session.post(f'{URL.STORE}/login/logout/')
        await self._session.close()
        self._logged_in = False
        self._client.dispatch('logout')

    async def _send_login_request(self):
        rsa_params, rsa_timestamp = await self._fetch_rsa_params()
        encrypted_password = \
            b64encode(rsa.encrypt(self.password.encode('utf-8'), rsa_params['rsa_key'])).decode()

        return await self._send_login(rsa_timestamp, encrypted_password)

    async def _fetch_rsa_params(self, current_repetitions: int = 0) -> tuple:
        maximum_repetitions = 5
        data = {'username': self.username,
                'donotcache': str(int(time() * 1000))}
        try:
            request = await self._session.post(f'{URL.STORE}/login/getrsakey/', data=data)
        except Exception as e:
            await self._session.close()
            raise LoginError(e)
        try:
            key_response = await request.json()
        except aiohttp.ContentTypeError as e:
            raise HTTPException(f'The Steam API likely is down, please '
                                f'try again later {" ".join(e.args)}')
        try:
            rsa_mod = int(key_response['publickey_mod'], 16)
            rsa_exp = int(key_response['publickey_exp'], 16)
            rsa_timestamp = key_response['timestamp']
            return rsa.PublicKey(rsa_mod, rsa_exp), rsa_timestamp
        except KeyError:
            if current_repetitions < maximum_repetitions:
                return await self._fetch_rsa_params(current_repetitions + 1)
            else:
                raise ValueError('Could not obtain rsa-key')

    async def _send_login(self, rsa_timestamp: str, encrypted_password: str):
        data = {
            'username': self.username,
            'password': encrypted_password,
            "emailauth": '',
            "emailsteamid": '',
            "twofactorcode": self._one_time_code or '',
            "captchagid": '-1',
            "captcha_text": '',
            "loginfriendlyname": self._user_agent,
            "rsatimestamp": rsa_timestamp,
            "remember_login": 'true',
            "donotcache": str(int(time() * 1000)),
        }
        try:
            post = await self._session.post(f'{URL.STORE}/login/dologin/', data=data)
            login_response = await post.json()

            if login_response['requires_twofactor']:
                self._one_time_code = self.code()
                return await self._send_login_request()
            return login_response

        except Exception as e:
            await self._session.close()
            raise HTTPException(e)

    async def _perform_redirects(self, response_dict: dict):
        parameters = response_dict.get('transfer_parameters')
        if parameters is None:
            raise HTTPException('Cannot perform redirects after login, no parameters fetched. '
                                'The Steam API likely is down, please try again later ')
        for url in response_dict['transfer_urls']:
            await self._session.post(url, data=parameters)

    async def _assert_valid_credentials(self, login_response: dict):
        if not login_response['success']:
            await self._session.close()
            raise InvalidCredentials(login_response['message'])

    async def _final_check(self):
        async with self._session.get(f'{URL.COMMUNITY}/my/home/') as resp:
            self.session_id = re.search(r'g_sessionID = "(?P<sessionID>(?:.*?))";',
                                        await resp.text()).group('sessionID')

    async def mini_profile(self, user: typing.Union[User, SteamID]) -> dict:
        post = await self._session.get(
            url=f'{URL.COMMUNITY}/miniprofile/{user.as_steam3[5:-1]}/json')
        resp = await post.json()
        return resp if resp['persona_name'] else None

    async def add_user(self, user: User) -> aiohttp.ClientResponse:
        """Add a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 0
        }
        return await self._session.post(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def remove_user(self, user: User) -> aiohttp.ClientResponse:
        """Remove a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
        }
        return await self._session.post(url=f'{URL.COMMUNITY}/actions/RemoveFriendAjax', data=data)

    async def block_user(self, user: User) -> aiohttp.ClientResponse:
        """Block a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 1
        }
        return await self._session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def unblock_user(self, user: User) -> aiohttp.ClientResponse:
        """Unblock a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 0
        }
        return await self._session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def accept_user_invite(self, user: User):
        """Accept an invite from a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 1
        }
        return await self._session.post(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def decline_user_invite(self, user: User):
        """Decline an invite from a :class:`~steam.User`"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 0
        }
        return await self._session.post(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)
