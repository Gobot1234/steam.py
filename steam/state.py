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
import weakref
from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Callable, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from stringcase import snakecase
from yarl import URL as _URL

from .abc import SteamID
from .channel import DMChannel
from .enums import EChatEntryType, EMarketListingState, ETradeOfferState, EType
from .errors import AuthenticatorError, HTTPException, InvalidCredentials
from .game import Game
from .guard import Confirmation, generate_confirmation_code, generate_device_id
from .message import Message
from .models import URL, Invite
from .protobufs import EMsg, MsgProto
from .protobufs.steammessages_friendmessages import (
    CFriendMessages_IncomingMessage_Notification as MessageNotification
)
from .trade import TradeOffer
from .user import User
from .utils import get

if TYPE_CHECKING:
    from .client import Client
    from .http import HTTPClient
    from .market import Listing
    from .models import Comment

    from .protobufs.steammessages_clientserver_friends import CMsgClientPersonaState

log = logging.getLogger(__name__)


def register(emsg: EMsg):
    class wrapper:
        __slots__ = ('func',)

        def __init__(self, func: Callable):
            self.func = func

        def __set_name__(self, state: 'ConnectionState', _):
            state.parsers[emsg] = self.func

    return wrapper


class ConnectionState:
    parsers = dict()

    def __init__(self, loop: asyncio.AbstractEventLoop, client: 'Client', http: 'HTTPClient'):
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

        self._trades = dict()  # ¯\_(ツ)_/¯ I think the values aren't referenced anywhere
        self._users = weakref.WeakValueDictionary()
        self._confirmations = weakref.WeakValueDictionary()

    async def __ainit__(self) -> None:
        self.market = self.client._market
        self._id64 = self.client.user.id64
        self.loop.create_task(self._poll_trades())
        self.loop.create_task(self._poll_listings())
        self.loop.create_task(self._poll_notifications())

    @property
    def users(self) -> List[User]:
        return list(self._users.values())

    @property
    def trades(self) -> List[TradeOffer]:
        return list(self._trades.values())

    @property
    def listings(self) -> List['Listing']:
        return list(self._listings.values())

    @property
    def confirmations(self) -> List[Confirmation]:
        return list(self._confirmations.values())

    def get_user(self, id64: int) -> Optional[User]:
        return self._users.get(id64)

    async def fetch_user(self, user_id64: int) -> Optional[User]:
        resp = await self.http.get_user(user_id64)
        user = resp['response']['players'][0] if resp['response']['players'] else None
        return self._store_user(user) if user else None

    async def fetch_users(self, user_id64s: List[int]) -> List[Optional[User]]:
        resp = await self.http.get_users(user_id64s)
        return [self._store_user(user) for user in resp]

    def _store_user(self, data: dict) -> User:
        try:
            user = self._users[int(data['steamid'])]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id64] = user
        return user

    def get_listing(self, id: int) -> Optional['Listing']:
        return self._listings.get(id)

    def get_confirmation(self, id: int) -> Optional[Confirmation]:
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id: int) -> Optional[Confirmation]:
        await self._fetch_confirmations()
        return get(self._confirmations, trade_id=id)

    def get_trade(self, id: int) -> Optional[TradeOffer]:
        return self._trades.get(id)

    async def fetch_trade(self, id: int) -> Optional[TradeOffer]:
        resp = await self.http.get_trade(id)
        if resp.get('response'):
            trade = [resp['response']['offer']]
            descriptions = resp['response']['descriptions']
            trade = await self._process_trades(trade, descriptions)
            return trade[0]
        return None

    async def _store_trade(self, data: dict) -> TradeOffer:
        try:
            trade = self._trades[int(data['tradeofferid'])]
        except KeyError:
            log.info(f'Received trade #{data["tradeofferid"]}')
            trade = await TradeOffer._from_api(state=self, data=data)
            self._trades[trade.id] = trade
            if trade.state not in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed):
                return trade
            if trade.is_our_offer():
                self.dispatch('trade_send', trade)
            else:
                self.dispatch('trade_receive', trade)
        else:
            if data['trade_offer_state'] != trade.state:
                trade.state = ETradeOfferState(data['trade_offer_state'])
                log.info(f'Trade #{trade.id} has updated its trade state to {trade.state}')
                states = {
                    ETradeOfferState.Accepted: 'accept',
                    ETradeOfferState.Countered: 'countered',
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

    async def _process_trades(self, trades: List[dict], descriptions: List[dict]) -> List[TradeOffer]:
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

    async def _poll_trades(self) -> None:
        resp = await self.http.get_trade_offers()
        trades = resp['response']
        self._trades_received_cache = trades.get('trade_offers_received', [])
        self._trades_sent_cache = trades.get('trade_offers_sent', [])
        self._descriptions_cache = trades.get('descriptions', [])
        await self._process_trades(self._trades_received_cache, self._descriptions_cache)
        await self._process_trades(self._trades_sent_cache, self._descriptions_cache)

        try:
            while 1:
                await asyncio.sleep(1)
                resp = await self.http.get_trade_offers()
                trades = resp['response']
                descriptions = trades.get('descriptions', [])
                trades_received = trades.get('trade_offers_received', [])
                trades_sent = trades.get('trade_offers_sent', [])

                new_received_trades = [trade for trade in trades_received
                                       if trade not in self._trades_received_cache]
                new_sent_trades = [trade for trade in trades_sent
                                   if trade not in self._trades_sent_cache]
                new_descriptions = [item for item in descriptions
                                    if item not in self._descriptions_cache]
                await self._process_trades(new_received_trades, new_descriptions)
                await self._process_trades(new_sent_trades, new_descriptions)

                self._trades_received_cache = trades_received
                self._trades_sent_cache = trades_sent
                self._descriptions_cache = descriptions
        except (asyncio.TimeoutError, aiohttp.ClientError):
            self.loop.create_task(self._poll_trades())
        except HTTPException:
            await asyncio.sleep(10)
            self.loop.create_task(self._poll_trades())

    # this will be going when I get cms working

    async def _poll_notifications(self) -> None:
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
                                    if parsed_notification:
                                        self.dispatch(event_name, parsed_notification)
                            self._obj = None
                    self._cached_notifications = notifications
        except (asyncio.TimeoutError, aiohttp.ClientError):
            self.loop.create_task(self._poll_trades())
        except HTTPException:
            await asyncio.sleep(10)
            self.loop.create_task(self._poll_trades())

    async def _parse_comment(self, _) -> 'Comment':
        # this isn't very efficient but I'm not sure if it can be done better
        resp = await self.request('GET', f'{URL.COMMUNITY}/me/commentnotifications')
        search = re.search(r'<div class="commentnotification_click_overlay">\s*<a href="(.*?)">', resp)
        steam_id = await SteamID.from_url(f'{URL.COMMUNITY}{_URL(search.group(1)).path}')
        if steam_id.type == EType.Clan:
            obj = await self.client.fetch_group(steam_id.id64)
        else:
            obj = await self.fetch_user(steam_id.id64)

        if self._obj == obj:
            self._previous_iteration += 1
        else:
            self._obj = obj
            self._previous_iteration = 0
        comments = await obj.comments(limit=self._previous_iteration + 1).flatten()
        return comments[self._previous_iteration]

    async def _parse_invite(self, loop: int) -> Invite:
        params = {
            "ajax": 1
        }
        resp = await self.request('GET', f'{URL.COMMUNITY}/me/friends/pending', params=params)
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

    async def _poll_listings(self) -> None:
        self._listings = {listing.id: listing for listing in await self.client.fetch_listings()}
        try:
            while 1:
                await asyncio.sleep(300)  # we really don't want to spam these
                listings = {listing.id: listing for listing in await self.client.fetch_listings()}

                polled_values = listings.values()
                cached_values = self._listings.values()
                new_listings = [listing for listing in polled_values if listing not in cached_values]
                removed_listings = [listing for listing in cached_values if listing not in polled_values]

                for listing in new_listings:
                    self.dispatch('listing_create', listing)

                for listing in removed_listings:
                    if listing.state == EMarketListingState.Bought:
                        if listing in self.client.user.fetch_inventory(Game(listing.app_id)):
                            self.dispatch('listing_buy', listing)
                        else:
                            self.dispatch('listing_sell', listing)
                    elif listing.state == EMarketListingState.Cancelled:
                        self.dispatch('listing_cancel', listing)
                self._listings = listings

        except (asyncio.TimeoutError, aiohttp.ClientError):
            self.loop.create_task(self._poll_listings())
        except HTTPException:
            await asyncio.sleep(60)
            self.loop.create_task(self._poll_listings())

    # confirmations

    def _create_confirmation_params(self, tag: str) -> dict:
        timestamp = int(time())
        return {
            'p': self._device_id,
            'a': self._id64,
            'k': self._generate_confirmation(tag, timestamp),
            't': timestamp,
            'm': 'android',
            'tag': tag
        }

    async def _fetch_confirmations(self) -> Optional[weakref.WeakValueDictionary]:
        params = self._create_confirmation_params('conf')
        headers = {'X-Requested-With': 'com.valvesoftware.android.steam.community'}
        resp = await self.request('GET', f'{URL.COMMUNITY}/mobileconf/conf', params=params, headers=headers)

        if 'incorrect Steam Guard codes.' in resp:
            raise InvalidCredentials('identity_secret is incorrect')
        if 'Oh nooooooes!' in resp:
            raise AuthenticatorError

        soup = BeautifulSoup(resp, 'html.parser')
        if soup.select('#mobileconf_empty'):
            return None
        for confirmation in soup.select('#mobileconf_list .mobileconf_list_entry'):
            id = confirmation['id']
            confid = confirmation['data-confid']
            key = confirmation['data-key']
            trade_id = int(confirmation.get('data-creator', 0))
            self._confirmations[trade_id] = Confirmation(self, id, confid, key, trade_id)
        return self._confirmations

    def _device_id(self) -> str:
        return generate_device_id(str(self._id64))

    def _generate_confirmation(self, tag: str, timestamp: int) -> str:
        return generate_confirmation_code(self.client.identity_secret, tag, timestamp)

    async def get_and_confirm_confirmation(self, id: int) -> bool:
        if self.client.identity_secret:
            confirmation = self.get_confirmation(id) or await self.fetch_confirmation(id)
            if confirmation is not None:
                await confirmation.confirm()
                return True

        return False

    # ws stuff

    async def send_user_message(self, user: 'User', content: str) -> None:
        await self.client.ws.send_um(
            "FriendMessages.SendMessage#1_Request",
            steamid=str(user.id64), message=content,
            chat_entry_type=EChatEntryType.ChatMsg.value,
        )
        proto = MessageNotification(
            steamid_friend=0.0, chat_entry_type=1,
            message=content, rtime32_server_timestamp=time()
        )
        channel = DMChannel(state=self, participant=user)
        message = Message(state=self, proto=proto, channel=channel)
        message.author = self.client.user
        self.dispatch('message', message)

    # parsers

    @register(EMsg.ServiceMethod)
    def message_create(self, msg: MsgProto):
        if msg.header.target_job_name == 'FriendMessagesClient.IncomingMessage#1':
            msg.body: MessageNotification
            if msg.body.chat_entry_type == 1:  # normal chat message
                channel = DMChannel(state=self, participant=self.get_user(int(msg.body.steamid_friend)))
                message = Message(state=self, proto=msg.body, channel=channel)
                self.dispatch('message', message)
            if msg.body.chat_entry_type == 2:  # typing notification
                user = self.get_user(int(msg.body.steamid_friend))
                when = datetime.utcfromtimestamp(msg.body.rtime32_server_timestamp)
                self.dispatch('typing', user, when)

    """
    @register(EMsg.ClientUserNotifications)
    def parse_notification(self, msg: MsgProto):
        if msg.body:
            print(msg, msg.body)
    """

    @register(EMsg.ClientFriendsGroupsList)  # this appears to be one the last multi you receive
    def ready(self, _):
        self.client._handle_ready()

    @register(EMsg.ClientCMList)
    def handle_cm_list_update(self, msg: MsgProto):
        log.debug("Updating CM list")
        self.client.ws.cm_list.clear()
        self.client.ws.cm_list.merge_list(msg.body.cm_websocket_addresses)

    @register(EMsg.ClientPersonaState)
    def parse_persona_state_update(self, msg: MsgProto):
        msg.body: 'CMsgClientPersonaState'
        for friend in msg.body.friends:
            data = friend.to_dict(snakecase)
            user_id64 = int(data['friendid'])
            if user_id64 == self._id64:
                continue
            data = self.patch_user_from_ws(data)
            before = after = self.get_user(user_id64)
            after._update(data)
            old = [getattr(before, attr) for attr in dir(before)]
            new = [getattr(after, attr) for attr in dir(after)]
            if old != new:
                self._store_user(data)
                self.dispatch('user_update', before, after)

    def patch_user_from_ws(self, data) -> dict:
        data['personaname'] = data['player_name']
        data['avatarfull'] = data['avatar_hash']

        """
        if data['avatar_hash'] != '\x00' * 20:
            avatar_hash = data['avatar_hash'].encode('utf-8').hex()  # this is wrong
        else:
            avatar_hash = 'fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb'
        data['avatarfull'] = f'https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/' \
                             f'{avatar_hash[:2]}/{avatar_hash}_full.jpg'
        """

        if 'last_logoff' in data:
            data['lastlogoff'] = data['last_logoff']
        data['personstateflags'] = data.get('persona_state_flags', 0)
        return data
