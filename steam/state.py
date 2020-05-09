# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

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
from time import time

import aiohttp
from bs4 import BeautifulSoup
from yarl import URL as _URL

from .abc import SteamID
from .enums import ETradeOfferState, EType, EMarketListingState, EChatEntryType
from .errors import HTTPException, AuthenticatorError, InvalidCredentials
from .game import Game
from .guard import generate_device_id, generate_confirmation_code, Confirmation
from .models import URL, Invite
from .protobufs import MsgProto, EMsg
from .trade import TradeOffer
from .user import User
from .utils import get

log = logging.getLogger(__name__)


class ConnectionState:

    def __init__(self, loop, client, http):
        self.loop = loop
        self.http = http
        self.request = http.request
        self.client = client
        self.dispatch = client.dispatch

        self.started_trade_poll = False
        self.started_notification_poll = False
        self.started_listings_poll = False
        self._obj = None
        self._previous_iteration = 0

        self._trades = dict()  # TODO add weakref
        self._users = dict()
        self._confirmations = dict()

        self._current_job_id = 0

    async def __ainit__(self):
        self.market = self.client._market
        self._id64 = self.client.user.id64
        self.loop.create_task(self._poll_trades())
        self.loop.create_task(self._poll_listings())
        self.loop.create_task(self._poll_notifications())

    def _handle_ready(self):
        self.client._ready.set()

    async def send_message(self, user_id64, content):
        proto = MsgProto(
            EMsg.ClientFriendMsg,
            steamid=user_id64,
            message=content,
            chat_entry_type=EChatEntryType.ChatMsg.value
        )
        await self.client.ws.send_as_proto(proto)

    @property
    def users(self):
        return list(self._users.values())

    @property
    def trades(self):
        return list(self._trades.values())

    @property
    def listings(self):
        return list(self._listings_cache.values())

    @property
    def confirmations(self):
        return list(self._confirmations.values())

    async def fetch_user(self, user_id64):
        resp = await self.http.fetch_profile(user_id64)
        data = resp['response']['players'][0] if resp['response']['players'] else None
        if data:
            return self._store_user(data)
        return None

    def get_user(self, user_id64):
        return self._users.get(user_id64)

    def _store_user(self, data):
        try:
            user = self._users[int(data['steamid'])]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id64] = user
        return user

    def get_listing(self, listing_id):
        return get(self._listings_cache, id=listing_id)

    def get_confirmation(self, id):
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id):
        confirmations = await self._fetch_confirmations()
        return get(confirmations, creator=str(id))

    def get_trade(self, trade_id):
        return self._trades.get(trade_id)

    async def fetch_trade(self, trade_id):
        resp = await self.http.fetch_trade(trade_id)
        if resp.get('response'):
            trade = [resp['response']['offer']]
            descriptions = resp['response']['descriptions']
            return (await self._process_trades(trade, descriptions))[0]
        return None

    async def _store_trade(self, data):
        try:
            trade = self._trades[int(data['tradeofferid'])]
        except KeyError:
            log.info(f'Received trade #{data["tradeofferid"]}')
            trade = TradeOffer(state=self, data=data)
            await trade.__ainit__()
            self._trades[trade.id] = trade
            if trade.state not in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed):
                return trade
            if trade.is_our_offer():
                self.client.dispatch('trade_send', trade)
            else:
                self.client.dispatch('trade_receive', trade)
        else:
            if data['trade_offer_state'] != trade.state:
                trade.state = ETradeOfferState(data['trade_offer_state'])
                log.info(f'Trade #{trade.id} has updated its trade state to {trade.state}')
                if trade.state == ETradeOfferState.Countered:
                    done, pending = await asyncio.wait([
                        self.client.wait_for('trade_send', check=lambda t: t.partner == trade.partner),
                        self.client.wait_for('trade_receive', check=lambda t: t.partner == trade.partner)
                    ], return_when=asyncio.FIRST_COMPLETED, timeout=3)
                    if done:
                        after = done.pop().result()
                        before = trade
                        self.dispatch('trade_counter', before, after)
                    for future in pending:
                        future.cancel()
                    if not done:
                        return trade

                states = {
                    ETradeOfferState.Accepted: 'accept',
                    ETradeOfferState.Expired: 'expire',
                    ETradeOfferState.Canceled: 'cancel',
                    ETradeOfferState.Declined: 'decline',
                    ETradeOfferState.CanceledBySecondaryFactor: 'cancel',
                }
                try:
                    event_name = states[trade.state]
                except KeyError:
                    pass
                else:
                    self.dispatch(f'trade_{event_name}', trade)
        return trade

    # this will be going when I get cms working

    async def _process_trades(self, trades, descriptions):
        ret = []
        for trade in trades:
            for item in descriptions:
                for asset in trade.get('items_to_receive', []):
                    if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                        asset.update(item)
                for asset in trade.get('items_to_give', []):
                    if item['classid'] == asset['classid'] and item['instanceid'] == asset['instanceid']:
                        asset.update(item)
            ret.append(await self._store_trade(trade))
        return ret

    async def _poll_trades(self):
        create_task = self.loop.create_task
        resp = await self.http.fetch_trade_offers()
        trades = resp['response']
        self._trades_received_cache = trades.get('trade_offers_received', [])
        self._trades_sent_cache = trades.get('trade_offers_sent', [])
        self._descriptions_cache = trades.get('descriptions', [])
        create_task(self._process_trades(self._trades_received_cache, self._descriptions_cache))
        create_task(self._process_trades(self._trades_sent_cache, self._descriptions_cache))

        try:
            while 1:
                await asyncio.sleep(5)
                resp = await self.http.fetch_trade_offers()
                trades = resp['response']
                descriptions = trades.get('descriptions', [])
                trades_received = trades.get('trade_offers_received', [])
                trades_sent = trades.get('trade_offers_sent', [])

                new_received_trades = [trade for trade in trades_received if trade not in self._trades_received_cache]
                new_sent_trades = [trade for trade in trades_sent if trade not in self._trades_sent_cache]
                new_descriptions = [item for item in descriptions if item not in self._descriptions_cache]
                create_task(self._process_trades(new_received_trades, new_descriptions))
                create_task(self._process_trades(new_sent_trades, new_descriptions))

                self._trades_received_cache = trades_received
                self._trades_sent_cache = trades_sent
                self._descriptions_cache = descriptions
        except (asyncio.TimeoutError, aiohttp.ClientError):
            self.loop.create_task(self._poll_trades())
        except HTTPException as e:
            print(repr(e.message))
            await asyncio.sleep(10)
            self.loop.create_task(self._poll_trades())

    async def _poll_notifications(self):
        notification_mapping = {
            "4": ('comment', self._parse_comment),
            "6": ('invite', self._parse_invite)
        }

        resp = await self.request('GET', url=f'{URL.COMMUNITY}/actions/GetNotificationCounts')
        self._cached_notifications = resp['notifications']
        try:
            while 1:
                await asyncio.sleep(5)
                resp = await self.request('GET', url=f'{URL.COMMUNITY}/actions/GetNotificationCounts')
                notifications = resp['notifications']
                if notifications != self._cached_notifications:
                    for notification in notifications:
                        if self._cached_notifications[notification] != notifications[notification]:
                            if notifications[notification] == 0:
                                continue
                            non_cached_count = notifications[notification]
                            cached_count = self._cached_notifications[notification]
                            for i in range(non_cached_count - cached_count):
                                try:
                                    event_name, event_parser = notification_mapping[notification]
                                except KeyError:
                                    break
                                else:
                                    log.debug(f'Received {event_name} notification')
                                    parsed_notification = await event_parser(i)
                                    self.dispatch(event_name, parsed_notification)
                            self._obj = None
                    self._cached_notifications = notifications
        except (asyncio.TimeoutError, aiohttp.ClientError):
            self.loop.create_task(self._poll_trades())
        except HTTPException:
            await asyncio.sleep(10)
            self.loop.create_task(self._poll_trades())

    async def _parse_comment(self, _):  # this isn't very efficient but I'm not sure if it can be done better
        resp = await self.request('GET', f'{self.client.user.community_url}/commentnotifications')
        search = re.search(r'<div class="commentnotification_click_overlay">\s*<a href="(.*?)">', resp)
        group = search.group(1)
        steam_id = await SteamID.from_url(group.strip(f'?{_URL(group).query_string}'))
        if steam_id.type == EType.Clan:
            obj = await self.client.fetch_group(steam_id.id64)
        else:
            obj = await self.client.fetch_user(steam_id.id64)

        if self._obj == obj:
            self._previous_iteration += 1
        else:
            self._obj = obj
            self._previous_iteration = 0
        comments = await obj.comments(limit=self._previous_iteration + 1).flatten()
        return comments[self._previous_iteration]

    async def _parse_invite(self, loop):
        params = {
            "ajax": 1
        }
        resp = await self.request('GET', f'{self.client.user.community_url}/friends/pending', params=params)
        soup = BeautifulSoup(resp, 'html.parser')
        invites = soup.find_all('div', attrs={"class": 'invite_row'})
        if not invites:
            resp = await self.request('GET', f'{self.client.user.community_url}/groups/pending', params=params)
            soup = BeautifulSoup(resp, 'html.parser')
            invites = soup.find_all('div', attrs={"class": 'invite_row'})
            data = invites[loop]
        else:
            data = invites[loop]
        invite = Invite(state=self, data=data)
        await invite.__ainit__()
        return invite

    async def _poll_listings(self):
        self._listings_cache = await self.client.fetch_listings()
        try:
            while 1:
                await asyncio.sleep(300)  # we really don't want to spam these
                listings = await self.client.fetch_listings()
                new_listings = [listing for listing in listings if listing not in self._listings_cache]
                removed_listings = [listing for listing in listings
                                    if listing in self._listings_cache and listing not in listings]

                for listing in new_listings:
                    self.dispatch('listing_create', listing)
                if removed_listings:
                    all_previous_listings = await self.client.listing_history().flatten()

                for listing in removed_listings:
                    listing = get(all_previous_listings, id=listing.id)
                    if listing.state == EMarketListingState.Bought:
                        if listing in self.client.user.fetch_inventory(Game(listing.app_id)):
                            self.dispatch('listing_buy', listing)
                        else:
                            self.dispatch('listing_sell', listing)
                    elif listing.state == EMarketListingState.Cancelled:
                        self.dispatch('listing_cancel', listing)
                self._listings_cache = listings

        except (asyncio.TimeoutError, aiohttp.ClientError):
            self.loop.create_task(self._poll_listings())
        except HTTPException:
            await asyncio.sleep(60)
            self.loop.create_task(self._poll_listings())

    # confirmations

    def _create_confirmation_params(self, tag):
        timestamp = int(time())
        return {
            'p': self._device_id,
            'a': self.id64,
            'k': self._generate_confirmation(tag, timestamp),
            't': timestamp,
            'm': 'android',
            'tag': tag
        }

    async def _fetch_confirmations(self):
        params = self._create_confirmation_params('conf')
        headers = {'X-Requested-With': 'com.valvesoftware.android.steam.community'}
        resp = await self.request('GET', f'{URL.COMMUNITY}/mobileconf/conf', params=params, headers=headers)

        if 'incorrect Steam Guard codes.' in resp:
            raise InvalidCredentials('identity secret is incorrect, or time is de-synced')
        elif 'Oh nooooooes!' in resp:
            raise AuthenticatorError

        soup = BeautifulSoup(resp, 'html.parser')
        if soup.select('#mobileconf_empty'):
            return []
        for confirmation in soup.select('#mobileconf_list .mobileconf_list_entry'):
            id = confirmation['id']
            confid = confirmation['data-confid']
            key = confirmation['data-key']
            creator = confirmation.get('data-creator')
            self._confirmations[int(creator)] = Confirmation(self, id, confid, key, creator)
        return self._confirmations

    @property
    def _device_id(self):
        return generate_device_id(str(self.id64))

    def _generate_confirmation(self, tag, timestamp):
        return generate_confirmation_code(self.client.identity_secret, tag, timestamp)

    async def get_and_confirm_confirmation(self, id):
        if state.client.identity_secret:
            confirmation = self.get_confirmation(id) or await self.fetch_confirmation(id)
            if confirmation is not None:
                await confirmation.confirm()
                return True

        return False
