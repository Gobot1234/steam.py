import logging
from asyncio import AbstractEventLoop
from base64 import b64encode
from binascii import hexlify
from time import time
from os import urandom as random_bytes

import rsa
from Cryptodome.Hash import SHA1
from aiohttp import ClientSession, ClientResponse, CookieJar

from .errors import LoginError, InvalidCredentials, HTTPException
from .state import State
from .utils import generate_one_time_code
from .utils.models import URL


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
        self.steam_id = None
        self.session_id = None

        self.state = State(loop, self.session)
        self.client = client

    def recreate(self):
        if self.session.closed:
            self.session = ClientSession(loop=self.loop, cookie_jar=CookieJar(),
                                         headers={"User-Agent": f'steam.py/{__import__("steam").__version__}'})

    async def login(self, username: str, password: str, shared_secret: str):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        login_response = await self._send_login_request()
        await self._check_for_captcha(login_response)
        login_response = await self._enter_steam_guard_if_necessary(login_response)
        await self._assert_valid_credentials(login_response)
        await self._perform_redirects(login_response)

        self.steam_id = login_response['transfer_parameters']['steamid']
        self.session_id = hexlify(SHA1.new(random_bytes(32)).digest())[:32].decode('ascii')

        #await self._set_cookies()
        self.client.dispatch('login')

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

    async def _send_login_request(self) -> dict:
        rsa_params = await self._fetch_rsa_params()
        rsa_timestamp = rsa_params['rsa_timestamp']
        rsa_request = await self._send_login(rsa_params, rsa_timestamp)
        return await rsa_request.json()

    async def logout(self) -> None:
        log.debug('Logging out of session')
        await self.session.post(f'{URL.COMMUNITY}/login/logout/')
        await self.session.close()
        self.client.dispatch('logout')

    async def _fetch_rsa_params(self, current_repetitions: int = 0) -> dict:
        maximum_repetitions = 5
        try:
            request = await self.session.post(f'{URL.COMMUNITY}/login/getrsakey/',
                                              data={'username': self.username,
                                                  'donotcache': int(time() * 1000)},
                                              timeout=15)
        except Exception as e:
            await self.session.close()
            raise LoginError(e)

        key_response = await request.json()
        try:
            rsa_mod = int(key_response['publickey_mod'], 16)
            rsa_exp = int(key_response['publickey_exp'], 16)
            rsa_timestamp = key_response['timestamp']
            return {
                'rsa_key': rsa.PublicKey(rsa_mod, rsa_exp),
                'rsa_timestamp': rsa_timestamp
            }
        except KeyError:
            if current_repetitions < maximum_repetitions:
                return await self._fetch_rsa_params(current_repetitions + 1)
            else:
                raise ValueError('Could not obtain rsa-key')

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

    @property
    def code(self):
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        self.loop.run_until_complete(self.logout())
        raise LoginError('You are not currently logged in')

    async def block(self, user):
        """Block a user using there Steam ID"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 1
        }
        await self.session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def unblock(self, user):
        """Unblock a user using there Steam ID"""
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "block": 0
        }
        await self.session.post(url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def add_friend(self, user):
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
            "accept_invite": 0
        }
        await self.session.post(url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def remove_friend(self, user) -> ClientResponse:
        data = {
            "sessionID": self.session_id,
            "steamid": user.id64,
        }
        return await self.session.post(url=f'{URL.COMMUNITY}/actions/RemoveFriendAjax', data=data)

    async def mini_profile(self, ID3: str) -> dict:
        post = await self.session.get(
            url=f'https://steamcommunity.com/miniprofile/{ID3[:]}/json')  # TODO check the slices needed
        return await post.json()
