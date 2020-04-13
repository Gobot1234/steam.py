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
import json
import logging
import re
from base64 import b64encode
from sys import version_info
from time import time

import aiohttp
import rsa

from . import __version__, errors
from .guard import generate_one_time_code, ConfirmationManager
from .models import URL
from .user import ClientUser

log = logging.getLogger(__name__)


async def json_or_text(response):
    text = await response.text(encoding='utf-8')
    try:
        if 'application/json' in response.headers['content-type']:  # thanks steam very cool
            return json.loads(text)
    except KeyError:  # this should only really happen if steam is down
        pass
    return text


def Route(api, call, version='v1'):
    """Used for formatting API request URLs"""
    return f'{URL.API}/{api}/{call}/{version}'


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""
    SUCCESS_LOG = '{method} {url} has received {text}'
    REQUEST_LOG = '{method} {url} with {data}{params}has returned {status}'
    DATA_REQUEST = '\nDATA: {}\n'
    PARAMS_REQUEST = '\nPARAMS: {}\n'

    def __init__(self, loop, session, client):
        self._loop = loop
        self._session = session
        self._client = client
        self._state = None
        self._lock = asyncio.Lock()

        self.username = None
        self.password = None
        self.api_key = None
        self.shared_secret = None
        self.identity_secret = None
        self._one_time_code = None

        self.session_id = None
        self.user = None
        self.logged_in = False
        self._steam_id = None
        self._confirmation_manager = None
        self.user_agent = f'steam.py/{__version__} client (https://github.com/Gobot1234/steam.py), ' \
                          f'Python/{version_info[0]}.{version_info[1]}, aiohttp/{aiohttp.__version__}'

    def recreate(self):
        if self._session.closed:
            self._session = aiohttp.ClientSession(loop=self._loop)

    def code(self):
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        else:
            return input('Please enter a Steam guard code\n>>> ')

    async def request(self, method, url, **kwargs):  # adapted from d.py
        headers = {
            'User-Agent': self.user_agent,
        }
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])

        # some checking if it's a JSON request
        if 'data' in kwargs:
            headers['Content-Type'] = 'application/json'
        async with self._lock:
            for tries in range(5):
                async with self._session.request(method, url, **kwargs) as r:
                    data = kwargs.get('data')
                    params = kwargs.get('params')
                    log.debug(self.REQUEST_LOG.format(
                        method=method,
                        url=url,
                        connective="with" if data or params else '',
                        data=self.DATA_REQUEST.format(data) if data else '',
                        params=self.PARAMS_REQUEST.format(params) if params else '',
                        status=r.status)
                    )

                    # even errors have text involved in them so this is safe to call
                    data = await json_or_text(r)

                    # the request was successful so just return the text/json
                    if 300 > r.status >= 200:
                        log.debug(f'{method} {url} has received {data}')
                        return data

                    # we are being rate limited
                    if r.status == 429:
                        # I haven't been able to get a 429 from the API but we should probably still handle it
                        try:
                            await asyncio.sleep(float(r.headers['X-Retry-After']))
                        except KeyError:
                            await asyncio.sleep(3 ** tries)

                        continue

                    # we've received a 500 or 502, unconditional retry
                    if r.status in {500, 502}:
                        await asyncio.sleep(1 + tries * 3)
                        continue

                    if r.status == 401:
                        # api key either got revoked or it was never valid
                        if 'Access is denied. Retrying will not help. Please verify your <pre>key=</pre>' in data:
                            # time to fetch a new key
                            self.api_key = await self.fetch_api_key()
                            kwargs['key'] = self.api_key
                            continue  # retry with our new key

                    # the usual error cases
                    if r.status == 403:
                        raise errors.Forbidden(r, data)
                    elif r.status == 404:
                        raise errors.NotFound(r, data)
                    else:
                        raise errors.HTTPException(r, data)

            # we've run out of retries, raise
            raise errors.HTTPException(r, data)

    async def login(self, username: str, password: str, api_key: str, shared_secret: str, identity_secret: str = None):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        login_response = await self._send_login_request()

        if 'captcha_needed' in login_response:
            await self._client.close()
            raise errors.LoginError('A captcha code is required, please try again later')

        if not login_response['success']:
            await self._client.close()
            raise errors.InvalidCredentials(login_response['message'])

        parameters = login_response.get('transfer_parameters')
        if parameters is None:
            raise errors.LoginError('Cannot perform redirects after login, no parameters fetched. '
                                    'The Steam API likely is down, please try again later.')

        for url in login_response['transfer_urls']:
            await self.request('POST', url=url, data=parameters)

        self._client.api_key = api_key or await self.fetch_api_key()
        self.api_key = self._client.api_key
        self._state = self._client._connection

        self.logged_in = True
        id64 = login_response['transfer_parameters']['steamid']
        resp = await self.fetch_profile(id64)
        user = resp['response']['players'][0]
        self.user = ClientUser(state=self._state, data=user)
        await self.user.__ainit__()
        if self.identity_secret:
            self._confirmation_manager = ConfirmationManager(state=self._state, id64=id64)

        self._client.dispatch('login')

    def logout(self):
        log.debug('Logging out of session')
        self.logged_in = False
        self._client.dispatch('logout')
        return self.request('GET', url=f'{URL.COMMUNITY}/login/logout/')

    async def _fetch_rsa_params(self, current_repetitions: int = 0):
        maximum_repetitions = 5
        data = {
            'username': self.username,
            'donotcache': int(time() * 1000)
        }
        try:
            key_response = await self.request('POST', url=f'{URL.COMMUNITY}/login/getrsakey', data=data)
        except Exception as e:
            await self._session.close()
            raise errors.LoginError(e)
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

    async def _send_login_request(self):
        rsa_key, rsa_timestamp = await self._fetch_rsa_params()
        encrypted_password = b64encode(rsa.encrypt(self.password.encode('utf-8'), rsa_key)).decode()
        data = {
            'username': self.username,
            'password': encrypted_password,
            "emailauth": '',
            "emailsteamid": '',
            "twofactorcode": self._one_time_code or '',
            "captchagid": '-1',
            "captcha_text": '',
            "loginfriendlyname": self.user_agent,
            "rsatimestamp": rsa_timestamp,
            "remember_login": True,
            "donotcache": int(time() * 1000),
        }
        try:
            login_response = await self.request('POST', url=f'{URL.COMMUNITY}/login/dologin', data=data)
            if login_response['requires_twofactor']:
                self._one_time_code = self.code()
                return await self._send_login_request()
            return login_response
        except Exception as e:
            raise errors.HTTPException from e

    def fetch_profile(self, user_id64: int):
        params = {
            "key": self.api_key,
            "steamids": user_id64
        }
        return self.request('GET', url=Route('ISteamUser', 'GetPlayerSummaries', 'v2'), params=params)

    async def fetch_profiles(self, user_id64s):
        ret = []

        def chunk():  # chunk the list into 100 element sublists for the requests
            for i in range(0, len(user_id64s), 100):
                yield user_id64s[i:i + 100]

        for sublist in chunk():
            for _ in sublist:
                params = {
                    "key": self.api_key,
                    "steamids": ','.join([str(user_id) for user_id in sublist])
                }

            full_resp = await self.request('GET', Route('ISteamUser', 'GetPlayerSummaries', 'v2'), params=params)
            ret.extend([user for user in full_resp['response']['players']])
        return ret

    def add_user(self, user_id64):
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    def remove_user(self, user_id64):
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/actions/RemoveFriendAjax', data=data)

    def block_user(self, user_id64):
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "block": 1
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    def unblock_user(self, user_id64):
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "block": 0
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    def accept_user_invite(self, user_id64):
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 1
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    def decline_user_invite(self, user_id64):
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/actions/IgnoreFriendInviteAjax', data=data)

    def fetch_user_games(self, user_id64):
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "include_appinfo": 1,
            "include_played_free_games": 1
        }
        return self.request('GET', url=Route('IPlayerService', 'GetOwnedGames'), params=params)

    def fetch_user_inventory(self, user_id64, app_id, context_id):
        params = {
            "count": 5000,
        }
        return self.request('GET', url=f'{URL.COMMUNITY}/inventory/{user_id64}/{app_id}/{context_id}', params=params)

    def fetch_user_escrow(self, user_id):
        trade_offer_url = f'{URL.COMMUNITY}/tradeoffer/new/?partner={user_id}'
        headers = {
            'Referer': trade_offer_url,
            'Origin': URL.COMMUNITY
        }
        return self.request('GET', url=trade_offer_url, headers=headers)

    async def fetch_friends(self, user_id64):
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "relationship": 'friend'
        }
        friends = await self.request('GET', url=Route('ISteamUser', 'GetFriendList'), params=params)
        return await self.fetch_profiles([friend['steamid'] for friend in friends['friendslist']['friends']])

    def fetch_trade_offers(self, active_only=True, sent=True, received=True):
        params = {
            "key": self.api_key,
            "active_only": int(active_only),
            "get_sent_offers": int(sent),
            "get_descriptions": 1,
            "get_received_offers": int(received)
        }
        return self.request('GET', url=Route('IEconService', 'GetTradeOffers'), params=params)

    def fetch_trade(self, trade_id):
        params = {
            "key": self.api_key,
            "tradeofferid": trade_id,
            "get_descriptions": 1
        }
        return self.request('GET', url=Route('IEconService', 'GetTradeOffer'), params=params)

    async def accept_user_trade(self, user_id64, trade_id):
        data = {
            'sessionid': self.session_id,
            'tradeofferid': trade_id,
            'serverid': 1,
            'partner': user_id64,
            'captcha': ''
        }
        headers = {'Referer': f'{URL.COMMUNITY}/tradeoffer/{trade_id}'}

        resp = await self.request('POST', url=f'{URL.COMMUNITY}/tradeoffer/{trade_id}/accept',
                                  data=data, headers=headers)
        if resp.get('needs_mobile_confirmation', False):
            if self.identity_secret:
                for _ in range(3):
                    conf = await self._confirmation_manager.get_trade_confirmation(trade_id)
                    await conf.confirm()
            else:
                raise errors.ClientException('Accepting trades requires an identity_secret')
        return resp

    def decline_user_trade(self, trade_id):
        data = {
            "sessionid": self.session_id
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/tradeoffer/{trade_id}/decline', data=data)

    def cancel_user_trade(self, trade_id):
        data = {
            "sessionid": self.session_id
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/tradeoffer/{trade_id}/cancel', data=data)

    def send_trade_offer(self, user_id64, user_id, to_send, to_receive, offer_message, **kwargs):
        data = {
            "sessionid": self.session_id,
            "serverid": 1,
            "partner": user_id64,
            "tradeoffermessage": offer_message,
            "json_tradeoffer": json.dumps({
                "newversion": True,
                "version": 4,
                "me": {
                    "assets": [item.to_dict() for item in to_send],
                    "currency": [],
                    "ready": False
                },
                "them": {
                    "assets": [item.to_dict() for item in to_receive],
                    "currency": [],
                    "ready": False
                }
            }),
            "captcha": '',
            "trade_offer_create_params": {}
        }
        data.update(**kwargs)
        headers = {'Referer': f'{URL.COMMUNITY}/tradeoffer/new/?partner={user_id}'}
        return self.request('POST', url=f'{URL.COMMUNITY}/tradeoffer/new/send', data=data, headers=headers)

    def send_counter_trade_offer(self, trade_id, user_id64, user_id, to_send, to_receive, offer_message):
        return self.send_trade_offer(user_id64, user_id, to_send, to_receive, offer_message, trade_id=trade_id)

    def fetch_cm_list(self, cell_id):
        params = {
            "cellid": cell_id
        }
        return self.request('GET', url=Route('ISteamDirectory', 'GetCMList'), params=params)

    def fetch_comments(self, id64, limit=None):
        params = {
            "start": 0,
            "totalcount": 9999999999
        }
        if limit is None:
            params["count"] = 9999999999
        else:
            params["count"] = limit
        return self.request('GET', f'{URL.COMMUNITY}/comment/Profile/render/{id64}', params=params)

    def post_comment(self, user_id64, comment):
        data = {
            "sessionid": self.session_id,
            "comment": comment,
        }
        return self.request('POST', url=f'{URL.COMMUNITY}/comment/Profile/post/{user_id64}', data=data)

    def report_comment(self, user_id, comment_id):
        params = {
            "gidcomment": comment_id,
            "hide": 1
        }
        return self.request('POST', f'{URL.COMMUNITY}/comment/Profile/hideandreport/{user_id}', params=params)

    def delete_comment(self, user_id, comment_id):
        params = {
            "gidcomment": comment_id,
        }
        return self.request('POST', f'{URL.COMMUNITY}/comment/Profile/delete/{user_id}', params=params)

    async def fetch_api_key(self):
        resp = await self.request('GET', url=f'{URL.COMMUNITY}/dev/apikey')
        error = 'You must have a validated email address to create a Steam Web API key'
        if error in resp:
            raise errors.LoginError(error)

        match = re.findall(r'<p>Key: ([0-9A-F]+)</p>', resp)
        if match:
            search = re.search(r'g_sessionID = "(?P<sessionID>.*?)";', resp)
            if search:
                self.session_id = search.group('sessionID')
            return match[0]
        else:
            data = {
                "domain": URL.COMMUNITY,
                "agreeToTerms": 'agreed',
                "sessionid": self.session_id,
                "Submit": 'Register'
            }
            await self.request('POST', url=f'{URL.COMMUNITY}/dev/registerkey', data=data)
            return await self.fetch_api_key()