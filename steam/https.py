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

from . import __version__
from .enums import URL, Game
from .errors import LoginError, InvalidCredentials, HTTPException, Forbidden, NotFound, TooManyRequests
from .guard import generate_one_time_code
from .state import State
from .user import User, ClientUser

log = logging.getLogger(__name__)


async def json_or_text(response):
    text = await response.text(encoding='utf-8')
    if 'application/json' in response.headers['content-type']:
        return json.loads(text)
    return text


class HTTPClient:
    """The HTTP Client that interacts with the Steam web API."""

    def __init__(self, loop, session, client, api_key: str):  # TODO make things here raw-er
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
            1: ('trade', self._parse_trade),
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
                    raise TooManyRequests('We are being rate limited try again soon')
                # we've received a 500 or 502, unconditional retry
                if r.status in {500, 502}:
                    await asyncio.sleep(1 + tries * 2)
                    continue

                # the usual error cases
                if r.status == 403:
                    raise Forbidden(r, data)
                elif r.status == 404:
                    raise NotFound(r, data)
                else:
                    raise HTTPException(r, data)

            # we've run out of retries, raise.
        raise HTTPException(r, data)

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
            raise LoginError(e)
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
            await self._session.close()
            raise HTTPException(e)

    async def _perform_redirects(self, response_dict: dict):
        parameters = response_dict.get('transfer_parameters')
        if parameters is None:
            raise HTTPException('Cannot perform redirects after login, no parameters fetched. '
                                'The Steam API likely is down, please try again later.')
        for url in response_dict['transfer_urls']:
            await self._request('POST', url=url, data=parameters)

    async def _assert_valid_credentials(self, login_response: dict):
        if not login_response['success']:
            await self._session.close()
            raise InvalidCredentials(login_response['message'])
        home = await self._session.get(url=f'{URL.COMMUNITY}/my/home/')
        self.session_id = re.search(r'g_sessionID = "(?P<sessionID>.*?)";', await home.text()).group('sessionID')

    async def fetch_profile(self, user_id64: int):
        params = {
            "key": self.api_key,
            "steamids": user_id64
        }
        full_resp = await self._request('GET', url=f'{URL.API}/ISteamUser/GetPlayerSummaries/v0002/',
                                        params=params)
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

            full_resp = await self._request('GET', url=f'{URL.API}/ISteamUser/GetPlayerSummaries/v0002/',
                                            params=params)
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
            "sessionid": self.session_id,
            "steamid": user_id64,
            "block": 1
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def unblock_user(self, user_id64):
        """Unblock a Steam user"""
        data = {
            "sessionid": self.session_id,
            "steamid": user_id64,
            "block": 0
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/BlockUserAjax', data=data)

    async def accept_user_invite(self, user_id64):
        """Accept an invite from a Steam user"""
        data = {
            "sessionid": self.session_id,
            "steamid": user_id64,
            "accept_invite": 1
        }
        return await self._request('POST', url=f'{URL.COMMUNITY}/actions/AddFriendAjax', data=data)

    async def decline_user_invite(self, user_id64):
        """Decline an invite from a Steam user"""
        data = {
            "sessionid": self.session_id,
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

    async def fetch_user_inventory(self, user_id64, game: Game):
        """Fetch a Steam user's inventory for a game on steam"""
        return await self._request('GET', url=f'{URL.COMMUNITY}/inventory/{user_id64}/{game.app_id}/{game.context_id}')

    async def fetch_friends(self, user_id64):
        params = {
            "key": self.api_key,
            "steamid": user_id64,
            "relationship": 'friend'
        }
        friends = await self._request('GET', url=f'{URL.API}/ISteamUser/GetFriendList/v0001/', params=params)
        users = await self.fetch_profiles([friend['steamid'] for friend in friends['friendslist']['friends']])
        return [User(state=self._state, data=user) for user in users]

    async def send_trade_offer(self, user_id64, game: Game, items_to_send: list, items_to_receive: list,
                               offer_message: str):
        data = {
            "sessionID": self.session_id,
            "serverid": 1,
            "partner": user_id64,
            "tradeoffermessage": offer_message,
            "json_tradeoffer": {
                "newversion": True,
                "version": 2,
                "me": {
                    "assets": [
                        {
                            "app_id": game.app_id,
                            "context_id": game.context_id,
                            "asset_id": item.asset_id
                        }
                        for item in items_to_send
                    ],
                    "currency": [],
                    "ready": False
                },
                "them": {
                    "assets": [
                        {
                            "app_id": game.app_id,
                            "context_id": game.context_id,
                            "asset_id": item.asset_id
                        }
                        for item in items_to_receive
                    ],
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
                        parsed_notification = await event_parser()
                        self._client.dispatch(event_name, parsed_notification)
                cached_notifications = notifications

            await asyncio.sleep(5)

    async def _parse_trade(self):
        print('received trade')
        f'{URL.COMMUNITY}/id/{self._user.name}/tradeoffers/'

        """</div>	<div class="maincontent">
				<div class="profile_leftcol">
						
					<div class="tradeoffer" id="tradeofferid_3898383370">
													<a href="#" onclick="ReportTradeScam( '76561198400794682', &quot;GoBOT1234&quot; );" class="btn_grey_grey btn_medium ico_hover btn_report" title="Flag this as a suspected scam.">
								<span><i class="ico16 report"></i></span>
							</a>
							<div class="tradeoffer_partner">
								<div class="playerAvatar offline" data-miniprofile="440528954">
									<a href="https://steamcommunity.com/id/GoBOT12341">
										<img src="https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/8b/8bfe66f38592ad1f3e7f38b1e1b69830b7bb4b12.jpg">
									</a>
								</div>
							</div>
												<div class="tradeoffer_header">
							GoBOT1234 offered you a trade:						</div>
													<div class="tradeoffer_message">
								<div class="quote_arrow"></div>
								<div class="quote">
									Contact my owner Gobot12342 if you need help :D&nbsp;<span class="tooltip_hint"  data-tooltip-text="Steam user GoBOT1234 included this message with his or her trade offer." >(?)</span>								</div>
							</div>
												<div class="tradeoffer_items_ctn  inactive">
														<div class="tradeoffer_items primary">
								<div class="tradeoffer_items_avatar_ctn">
									<a class="tradeoffer_avatar playerAvatar tiny offline" href="https://steamcommunity.com/id/GoBOT12341" data-miniprofile="440528954">
										<img src="https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/8b/8bfe66f38592ad1f3e7f38b1e1b69830b7bb4b12.jpg">
									</a>
								</div>
								<div class="tradeoffer_items_header">
									GoBOT1234 offered:								</div>
								<div class="tradeoffer_item_list">
																			<div class="trade_item missing" style="" data-economy-item="classinfo/440/8943017">
																						<img src="https://steamcommunity-a.akamaihd.net/economy/image/class/440/8943017/96fx96f" srcset="https://steamcommunity-a.akamaihd.net/economy/image/class/440/8943017/96fx96f 1x, https://steamcommunity-a.akamaihd.net/economy/image/class/440/8943017/96fx96fdpx2x 2x">
																					</div>
																		<div style="clear: left;"></div>
								</div>
							</div>
															<div class="tradeoffer_items_banner ">
									Trade Offer Canceled 7 Feb, 2020								</div>
														<div class="tradeoffer_items secondary">
								<div class="tradeoffer_items_avatar_ctn">
									<a class="tradeoffer_avatar playerAvatar tiny offline" href="https://steamcommunity.com/id/Gobot1234" data-miniprofile="287788226">
										<img src="https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/ca/cae63f6471cab8223afdc9b6fdf7774fe1ccb181.jpg">
									</a>
								</div>
								<div class="tradeoffer_items_header">
									For your:								</div>
								<div class="tradeoffer_item_list">
																			<div class="trade_item " style="border-color: #7D6D00; background-color: #3C352E;" data-economy-item="classinfo/440/2674/11040547">
																						<img src="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsO1Mv6NGucF1Ygzt8ZQijJukFMiMrbhYDEwI1yRVKNfD6xorQ3qW3Jr6546DNPuou9IOVK4p4kWJaA/73fx73f" srcset="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsO1Mv6NGucF1Ygzt8ZQijJukFMiMrbhYDEwI1yRVKNfD6xorQ3qW3Jr6546DNPuou9IOVK4p4kWJaA/73fx73f 1x, https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsO1Mv6NGucF1Ygzt8ZQijJukFMiMrbhYDEwI1yRVKNfD6xorQ3qW3Jr6546DNPuou9IOVK4p4kWJaA/73fx73fdpx2x 2x">
																					</div>
																			<div class="trade_item " style="border-color: #7D6D00; background-color: #3C352E;" data-economy-item="classinfo/440/2675/11040547">
																						<img src="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f" srcset="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f 1x, https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73fdpx2x 2x">
																					</div>
																			<div class="trade_item " style="border-color: #7D6D00; background-color: #3C352E;" data-economy-item="classinfo/440/2675/11040547">
																						<img src="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f" srcset="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f 1x, https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73fdpx2x 2x">
																					</div>
																			<div class="trade_item " style="border-color: #7D6D00; background-color: #3C352E;" data-economy-item="classinfo/440/2675/11040547">
																						<img src="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f" srcset="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f 1x, https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73fdpx2x 2x">
																					</div>
																			<div class="trade_item " style="border-color: #7D6D00; background-color: #3C352E;" data-economy-item="classinfo/440/2675/11040547">
																						<img src="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f" srcset="https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73f 1x, https://steamcommunity-a.akamaihd.net/economy/image/fWFc82js0fmoRAP-qOIPu5THSWqfSmTELLqcUywGkijVjZULUrsm1j-9xgEbZQsUYhTkhzJWhsPZAfOeD-VOn4phtsdQ32ZtxFYoN7PkYmVmIgeaUKNaX_Rjpwy8UHMz6pcxAIfnovUWJ1t9nYFqYw/73fx73fdpx2x 2x">
																					</div>
																		<div style="clear: left;"></div>
								</div>
							</div>
						</div>
						<div 
						
						
					lass="tradeoffer_footer">"""

        r'<div class="tradeoffer" id="tradeofferid_(?P<offer_id>(\d+))">(?:.*)'
        r'onclick="ReportTradeScam\( \'(?P<user_id>(\d+))\',(?:.*)'
        r'<div class="quote">\W+(?P<comment>(?:.*?))&nbsp;'

        item_info = 'https://steamcommunity.com/economy/itemclasshover/440/2675/11040547?content_only=1'
        r'data-economy-item="classinfo/(?P<asset_id>(\d+))">'

    async def _parse_comment(self):
        print('received comment')

    async def _lol(self):
        print('chat message')

    async def _parse_item_receive(self):
        print('received items')

    async def _parse_invite_receive(self):
        print('received invite')

    async def _connect_to_chat(self):
        """
        1. find socket
            https://api.steampowered.com/ISteamDirectory/GetCMList/v1/?cellid=0

        2. post ping
            weird token is important needs some regex
            view-source:https://steamcommunity.com/chat/
            Ag1HXnEbE1YAAAAAAAAAAAAAAAAAAAAAAwAu8XjfGpqhJSotlOGJWn1p
            needs post for first ping i think

        3. listen time:
            https://steamcommunity-a.akamaihd.net/public/javascript/webui/steammessages.js
            https://cm2-iad1.cm.steampowered.com:27021/cmping/
        """
        f'{URL.API}/ISteamDirectory/GetCMList/v1/?cellid=1'
        resp = await self._session.get(f'{URL.COMMUNITY}/chat/clientjstoken')
        access_token = (await resp.json())['token']
        async with self._session.ws_connect(f'wss://cm-03-ams1.cm.steampowered.com/cmsocket/') as ws:
            async for msg in ws:
                print(msg)
