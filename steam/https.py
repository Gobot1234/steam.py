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

from steam.trade import Item
from . import __version__, errors
from .enums import URL
from .guard import generate_one_time_code
from .state import State
from .user import ClientUser

log = logging.getLogger(__name__)


async def json_or_text(response):
    text = await response.text(encoding='utf-8')
    if 'application/json' in response.headers['content-type']:  # thanks steam very cool
        return json.loads(text)
    return text


def Route(api, call, version='v1'):
    """Used for formatting API request URLs"""
    return f'{URL.API}/{api}/{call}/{version}'


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    def __init__(self, loop, session, client, api_key: str):
        self._loop = loop
        self._session = session
        self._client = client
        self.api_key = api_key
        self._state = State(loop=loop, client=client, http=self)

        self.username = None
        self.password = None
        self.shared_secret = None
        self._one_time_code = None

        self.session_id = None
        self._steam_id = None
        self._user = None
        self._logged_in = False
        self._login_friendly_name = \
            f'steam.py/{__version__} bot (https://github.com/Gobot1234/steam.py), ' \
            f'Python/{version_info[0]}.{version_info[1]}, aiohttp/{aiohttp.__version__}'

        self._notifications = {
            4: ('comment', self._parse_comment),
            5: ('receive_items', self._parse_item_receive),
            6: ('receive_invite', self._parse_invite_receive),
            8: ('receive_gift', self._parse_item_receive),
        }

    def recreate(self):
        if self._session.closed:
            self._session = aiohttp.ClientSession(loop=self._loop)

    def code(self):
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        else:
            return input('Please enter a Steam guard code\n> ')

    async def _request(self, method, url, **kwargs):
        for tries in range(5):
            async with self._session.request(method, url, **kwargs) as r:
                data = f'\nDATA: {kwargs.get("data")}\n'
                params = f'\nPARAMS: {kwargs.get("params")}\n'
                log.debug(f'{method} {url} '
                          f'{"with" if kwargs.get("data") or kwargs.get("params") else ""}'
                          f'{data if kwargs.get("data") else ""}'
                          f'{params if kwargs.get("params") else ""}'
                          f'has returned {r.status}')

                data = await json_or_text(r)
                # the request was successful so just return the text/json
                if 300 > r.status >= 200:
                    log.debug(f'{method} {url} has received {data}')
                    return data

                # we are being rate limited
                if r.status == 429:
                    await asyncio.sleep(5 + tries * 2)
                    raise errors.TooManyRequests('We are being rate limited try again soon')
                # we've received a 500 or 502, unconditional retry
                if r.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 2)
                    continue

                # the usual error cases
                if r.status == 403:
                    raise errors.Forbidden(r, data)
                elif r.status == 404:
                    raise errors.NotFound(r, data)
                else:
                    raise errors.HTTPException(r, data)

            # we've run out of retries, raise.
        raise errors.HTTPException(r, data)

    async def login(self, username: str, password: str, shared_secret: str):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        login_response = await self._send_login_request()
        if 'captcha_needed' in login_response.keys():
            raise errors.LoginError('A captcha code is required, please try again later')

        await self._assert_valid_credentials(login_response)
        await self._perform_redirects(login_response)

        self._logged_in = True
        self._client.dispatch('login')

        data = await self.fetch_profile(login_response['transfer_parameters']['steamid'])
        self._user = ClientUser(state=self._state, data=data)
        # self._loop.create_task(self._poll_notifications())

    async def logout(self):
        log.debug('Logging out of session')
        await self._session.get(url=f'{URL.STORE}/login/logout/')
        await self._session.close()
        self._logged_in = False
        self._client.dispatch('logout')

    async def _send_login_request(self):
        rsa_key, rsa_timestamp = await self._fetch_rsa_params()
        encrypted_password = \
            b64encode(rsa.encrypt(self.password.encode('utf-8'), rsa_key)).decode()
        return await self._send_login(rsa_timestamp, encrypted_password)

    async def _fetch_rsa_params(self, current_repetitions: int = 0) -> tuple:
        maximum_repetitions = 5
        data = {
            'username': self.username,
            'donotcache': int(time() * 1000)
        }
        try:
            key_response = await self._request('POST', url=f'{URL.STORE}/login/getrsakey/', data=data)
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

    async def _send_login(self, rsa_timestamp: str, encrypted_password: str):
        data = {
            'username': self.username,
            'password': encrypted_password,
            "emailauth": '',
            "emailsteamid": '',
            "twofactorcode": self._one_time_code or '',
            "captchagid": '-1',
            "captcha_text": '',
            "loginfriendlyname": self._login_friendly_name,
            "rsatimestamp": rsa_timestamp,
            "remember_login": True,
            "donotcache": int(time() * 1000),
        }
        try:
            login_response = await self._request('POST', url=f'{URL.STORE}/login/dologin/', data=data)
            if login_response['requires_twofactor']:
                self._one_time_code = self.code()
                return await self._send_login_request()
            return login_response
        except Exception as e:
            raise errors.HTTPException(e)

    async def _perform_redirects(self, response_dict: dict):
        parameters = response_dict.get('transfer_parameters')
        if parameters is None:
            raise errors.HTTPException('Cannot perform redirects after login, no parameters fetched. '
                                       'The Steam API likely is down, please try again later.')
        for url in response_dict['transfer_urls']:
            await self._request('POST', url=url, data=parameters)

    async def _assert_valid_credentials(self, login_response: dict):
        if not login_response['success']:
            await self._session.close()
            raise errors.InvalidCredentials(login_response['message'])
        home = await self._session.get(url=f'{URL.COMMUNITY}/my/home/')
        self.session_id = re.search(r'g_sessionID = "(?P<sessionID>.*?)";', await home.text()).group('sessionID')

    async def fetch_profile(self, user_id64: int):
        params = {
            "key": self.api_key,
            "steamids": user_id64
        }
        full_resp = await self._request('GET', url=Route('ISteamUser', 'GetPlayerSummaries', 'v2'), params=params)
        resp = full_resp['response']['players'][0]
        return resp if resp else None

    async def fetch_profiles(self, id64s: list):
        ids = []
        to_ret = []

        for id64 in id64s:  # generate the larger list
            ids.append(id64)

        def chunk():  # chunk the list into 100 element sublists for the requests
            for i in range(0, len(id64s), 100):
                yield ids[i:i + 100]

        chunked_user_ids = list(chunk())
        for sublist in chunked_user_ids:  # make the requests
            for _ in sublist:
                params = {
                    "key": self.api_key,
                    "steamids": ','.join([user_id for user_id in sublist])
                }

            full_resp = await self._request('GET', Route('ISteamUser', 'GetPlayerSummaries', 'v2'), params=params)
            to_ret.extend([user for user in full_resp['response']['players']])
        return to_ret

    async def add_user(self, user_id64):
        """Add a Steam user to your friends list"""
        data = {
            "sessionid": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def remove_user(self, user_id64):
        """Remove a Steam user from your friends list"""
        data = {
            "sessionid": self.session_id,
            "steamid": user_id64,
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/RemoveFriendAjax', data=data)

    async def block_user(self, user_id64):
        """Block a Steam user"""
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "block": 1
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def unblock_user(self, user_id64):
        """Unblock a Steam user"""
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "block": 0
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def accept_user_invite(self, user_id64):
        """Accept an invite from a Steam user"""
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 1
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def decline_user_invite(self, user_id64):
        """Decline an invite from a Steam user"""
        data = {
            "sessionID": self.session_id,
            "steamid": user_id64,
            "accept_invite": 0
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/IgnoreFriendInviteAjax', data=data)

    async def post_comment(self, user_id64, comment):
        """Post a comment on a user's profile"""
        data = {
            "sessionid": self.session_id,
            "comment": comment,
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/comment/Profile/post/{user_id64}/', data=data)

    async def fetch_user_inventory(self, user_id64, app_id, context_id):
        """Fetch a Steam user's inventory for a game on steam"""
        return await self._request('GET',
                                   url=f'{URL.COMMUNITY}/profiles/{user_id64}/inventory/json/{app_id}/{context_id}')

    async def fetch_friends(self, user_id64):
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "relationship": 'friend'
        }
        friends = await self._request('GET', url=Route('ISteamUser', 'GetFriendList'), params=params)
        return await self.fetch_profiles([friend['steamid'] for friend in friends['friendslist']['friends']])

    async def send_trade_offer(self, user_id64, to_send, to_receive, offer_message):
        def get_ids(item: Item):
            return {
                'assetid': str(item.asset_id),
                'amount': int(item.amount),
                'appid': int(item.game.app_id),
                'contextid': str(item.game.context_id)
            }

        data = {
            "sessionid": self.session_id,
            "serverid": 1,
            "partner": user_id64,
            "tradeoffermessage": offer_message,
            "jsontradeoffer": {
                "newversion": True,
                "version": 4,
                "me": {
                    "assets": [get_ids(item) for item in to_send],
                    "currency": [],
                    "ready": False
                },
                "them": {
                    "assets": [get_ids(item) for item in to_receive],
                    "currency": [],
                    "ready": False
                }
            },
            "captcha": '',
            "trade_offer_create_params": {}
        }
        post = await self._request('POST', url=f'{URL.COMMUNITY}/tradeoffer/new/send', data=data)
        return post

    async def _poll_notifications(self):
        request = await self._request('GET', url=f'{URL.COMMUNITY}/actions/GetNotificationCounts')
        cached_notifications = request['notifications']
        await asyncio.sleep(5)
        while 1:
            request = await self._request('GET', url=f'{URL.COMMUNITY}/actions/GetNotificationCounts')
            notifications = request['notifications']
            if notifications != cached_notifications:
                for cached_notification, notification in zip(cached_notifications, notifications):
                    if notification in self._notifications.keys() and \
                            cached_notifications[cached_notification] != notifications[notification]:
                        event_name, event_parser = self._notifications[notification]
                        log.debug(f'Received raw event {event_name} from the notifications')
                        parsed_notification = await event_parser()
                        self._client.dispatch(event_name, parsed_notification)
                cached_notifications = notifications

            await asyncio.sleep(5)

    async def _parse_comment(self):
        print('received comment')

    async def _parse_item_receive(self):
        print('received items')

    async def _parse_invite_receive(self):
        print('received invite')
