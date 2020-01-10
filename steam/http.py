import base64
from time import time

import rsa
import logging
from aiohttp import ClientSession, ClientResponse, CookieJar
from .utils.guard import generate_one_time_code
from .errors import LoginError

log = logging.getLogger(__name__)

BASE = 'api.steampowered.com'
COMMUNITY_BASE = 'https://steamcommunity.com'
STORE_BASE = 'https://store.steampowered.com'


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API"""

    def __init__(self, username: str, password: str, shared_secret: str):
        self.username = username
        self.password = password
        self.one_time_code = ''
        self.shared_secret = shared_secret
        self.connector = None
        self.session = ClientSession(cookie_jar=CookieJar())

    def recreate(self):
        if self.session.closed:
            self.session = ClientSession(cookie_jar=CookieJar())

    async def login(self) -> ClientSession:
        login_response = await self._send_login_request()
        await self._check_for_captcha(login_response)
        login_response = await self._enter_steam_guard_if_necessary(login_response)
        await self._assert_valid_credentials(login_response)
        await self._perform_redirects(await login_response.json())
        await self.set_session_id_cookies()
        return self.session

    async def _send_login_request(self) -> ClientResponse:
        rsa_params = self._fetch_rsa_params()
        encrypted_password = self._encrypt_password(rsa_params)
        rsa_timestamp = rsa_params['rsa_timestamp']
        request_data = self._prepare_login_request_data(encrypted_password, rsa_timestamp)
        return await self.session.post(f'{COMMUNITY_BASE}/login/dologin', data=request_data)

    async def set_session_id_cookies(self):
        session_id = await self.session.cookie_jar.filter_cookies('https://steamcommunity.com/')['sessionid']
        community_domain = COMMUNITY_BASE[8:]
        store_domain = STORE_BASE[8:]
        community_cookie = self._create_session_id_cookie(session_id, community_domain)
        store_cookie = self._create_session_id_cookie(session_id, store_domain)
        await self.session.cookie_jar.update_cookies(**community_cookie)
        await self.session.cookie_jar.update_cookies(**store_cookie)

    def _fetch_rsa_params(self, current_number_of_repetitions: int = 0) -> dict:
        maximal_number_of_repetitions = 5
        key_response = await self.session.post(f'{COMMUNITY_BASE}/login/getrsakey/',
                                               data={'username': self.username})
        try:
            rsa_mod = int((await key_response.json())['publickey_mod'], 16)
            rsa_exp = int((await key_response.json())['publickey_exp'], 16)
            rsa_timestamp = (await key_response.json())['timestamp']
            return {'rsa_key': rsa.PublicKey(rsa_mod, rsa_exp),
                    'rsa_timestamp': rsa_timestamp}
        except KeyError:
            if current_number_of_repetitions < maximal_number_of_repetitions:
                return self._fetch_rsa_params(current_number_of_repetitions + 1)
            else:
                raise ValueError('Could not obtain rsa-key')

    def _encrypt_password(self, rsa_params: dict) -> str:
        return base64.b64encode(rsa.encrypt(self.password.encode('utf-8'), rsa_params['rsa_key']))

    def _prepare_login_request_data(self, encrypted_password: str, rsa_timestamp: str) -> dict:
        return {
            'password': encrypted_password,
            'username': self.username,
            'twofactorcode': self.one_time_code,
            'emailauth': '',
            'loginfriendlyname': '',
            'captchagid': '-1',
            'captcha_text': '',
            'emailsteamid': '',
            'rsatimestamp': rsa_timestamp,
            'remember_login': 'true',
            'donotcache': str(int(time() * 1000))
        }

    async def _enter_steam_guard_if_necessary(self, login_response: ClientResponse) -> ClientResponse:
        if (await login_response.json())['requires_twofactor']:
            self.one_time_code = generate_one_time_code(self.shared_secret)
            return await self._send_login_request()
        return login_response

    async def _perform_redirects(self, response_dict: dict) -> None:
        parameters = response_dict.get('transfer_parameters')
        if parameters is None:
            raise Exception('Cannot perform redirects after login, no parameters fetched')
        for url in response_dict['transfer_urls']:
            await self.session.post(url, data=parameters)

    @staticmethod
    def _create_session_id_cookie(session_id: str, domain: str) -> dict:
        return {"name": "sessionid", "value": session_id, "domain": domain}

    @staticmethod
    async def _check_for_captcha(login_response: ClientResponse) -> None:
        if not (await login_response.json())['captcha_needed']:
            raise LoginError('Captcha required')

    @staticmethod
    async def _assert_valid_credentials(login_response: ClientResponse) -> None:
        if not (await login_response.json())['success']:
            raise (await login_response.json())['message']

    @staticmethod
    async def _fetch_home_page(session: ClientSession) -> ClientResponse:
        return await session.post(f'{COMMUNITY_BASE}/my/home/')
