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
from typing import TYPE_CHECKING, List, Optional, Tuple, Callable

from bs4 import BeautifulSoup
from stringcase import snakecase
from yarl import URL as _URL

from .abc import SteamID
from .channel import DMChannel, GroupChannel
from .enums import (
    EChatEntryType,
    EFriendRelationship,
    ETradeOfferState,
    EType,
)
from .errors import AuthenticatorError, InvalidCredentials
from .group import Group
from .guard import Confirmation, generate_confirmation_code, generate_device_id
from .message import *
from .models import ClanInvite, URL, UserInvite
from .protobufs import EMsg, MsgProto
from .protobufs.steammessages_chat import CChatRoom_IncomingChatMessage_Notification \
    as GroupMessageNotification
from .protobufs.steammessages_friendmessages import CFriendMessages_IncomingMessage_Notification \
    as UserMessageNotification
from .trade import TradeOffer
from .user import User

if TYPE_CHECKING:
    from .client import Client
    from .http import HTTPClient
    from .models import Comment

    from .protobufs.steammessages_chat import CChatRoom_GetMyChatRoomGroups_Response
    from .protobufs.steammessages_clientserver import CMsgClientCMList
    from .protobufs.steammessages_clientserver_2 import (
        CMsgClientCommentNotifications,
        CMsgClientUserNotifications
    )
    from .protobufs.steammessages_clientserver_friends import (
        CMsgClientPersonaState,
        CMsgClientPersonaStateFriend,
        CMsgClientFriendsList,
    )


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
    parsers = dict()  # we need this for @register

    def __init__(self, loop: asyncio.AbstractEventLoop, client: 'Client', http: 'HTTPClient'):
        self.loop = loop
        self.http = http
        self.request = http.request
        self.client = client
        self.dispatch = client.dispatch

        self._obj = None
        self._previous_iteration = 0
        self.user_slots = set(User.__slots__) - {'_state', '_data'}

        self._users = weakref.WeakValueDictionary()
        self._trades = dict()
        self._confirmations = dict()
        self.invites = []
        self.groups = []
        self._trades_to_watch = []

    async def __ainit__(self) -> None:
        self.market = self.client._market
        self._id64 = self.client.user.id64
        self._device_id = generate_device_id(str(self._id64))
        self.loop.create_task(self._poll_trades())

    @property
    def users(self) -> List[User]:
        return list(self._users.values())

    @property
    def trades(self) -> List[TradeOffer]:
        return list(self._trades.values())

    @property
    def confirmations(self) -> List[Confirmation]:
        return list(self._confirmations.values())

    def get_user(self, id64: int) -> Optional[User]:
        return self._users.get(id64)

    async def fetch_user(self, user_id64: int) -> Optional[User]:
        resp = await self.http.get_user(user_id64)
        players = resp['response']['players']
        return self._store_user(players[0]) if players else None

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

    def get_confirmation(self, id: int) -> Optional[Confirmation]:
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id: int) -> Optional[Confirmation]:
        await self._fetch_confirmations()
        return self._confirmations.get(id)

    def get_trade(self, id: int) -> Optional[TradeOffer]:
        return self._trades.get(id)

    async def fetch_trade(self, id: int) -> Optional[TradeOffer]:
        resp = await self.http.get_trade(id)
        if resp.get('response'):
            trade = [resp['response']['offer']]
            descriptions = resp['response'].get('descriptions', [])
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
            self._trades_to_watch.append(trade)
        else:
            if data['trade_offer_state'] != trade.state:
                trade.state = ETradeOfferState(data['trade_offer_state'])
                log.info(f'Trade #{trade.id} has updated its trade state to {trade.state}')
                states = {
                    ETradeOfferState.Accepted: 'accept',
                    ETradeOfferState.Countered: 'counter',
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
                    self._trades_to_watch.remove(trade)
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
        while self._trades_to_watch:
            await asyncio.sleep(1)
            try:
                resp = await self.http.get_trade_offers()
            except Exception:
                await asyncio.sleep(10)
                continue
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

    async def _parse_comment(self) -> 'Comment':
        # this isn't very efficient but I'm not sure if it can be done better
        resp = await self.request('GET', f'{URL.COMMUNITY}/my/commentnotifications')
        search = re.search(r'<div class="commentnotification_click_overlay">\s*<a href="(.*?)">', resp)
        steam_id = await SteamID.from_url(f'{URL.COMMUNITY}{_URL(search.group(1)).path}')
        if steam_id.type == EType.Clan:
            obj = await self.client.fetch_clan(steam_id.id64)
        else:
            obj = await self.fetch_user(steam_id.id64)

        if self._obj == obj:
            self._previous_iteration += 1
        else:
            self._obj = obj
            self._previous_iteration = 0
        comments = await obj.comments(limit=self._previous_iteration + 1).flatten()
        return comments[self._previous_iteration]

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

    async def _fetch_confirmations(self) -> Optional[dict]:
        params = self._create_confirmation_params('conf')
        headers = {"X-Requested-With": 'com.valvesoftware.android.steam.community'}
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

    def _generate_confirmation(self, tag: str, timestamp: int) -> str:
        return generate_confirmation_code(self.client.identity_secret, tag, timestamp)

    async def get_and_confirm_confirmation(self, trade_id: int) -> bool:
        if self.client.identity_secret:
            confirmation = self.get_confirmation(trade_id) or await self.fetch_confirmation(trade_id)
            if confirmation is not None:
                await confirmation.confirm()
                return True

        return False

    # ws stuff

    async def send_user_message(self, user_id64: int, content: str) -> None:
        await self.client.ws.send_um(
            "FriendMessages.SendMessage#1_Request",
            steamid=str(user_id64), message=content,
            chat_entry_type=EChatEntryType.ChatMsg,
        )
        proto = UserMessageNotification(
            steamid_friend=0.0, chat_entry_type=1,
            message=content, rtime32_server_timestamp=time()
        )
        channel = DMChannel(state=self, participant=self.get_user(user_id64))
        message = UserMessage(proto=proto, channel=channel)
        message.author = self.client.user
        self.dispatch('message', message)

    async def send_user_typing(self, user: 'User') -> None:
        await self.client.ws.send_um(
            "FriendMessages.SendMessage#1_Request",
            steamid=str(user.id64),
            chat_entry_type=EChatEntryType.Typing,
        )
        self.dispatch('typing', self.client.user, datetime.utcnow())

    async def send_group_message(self, ids: Tuple[int, int], content: str) -> None:
        return
        await self.client.ws.send_um(
            "ChatRoom.SendChatMessage#1_Request",
            chat_id=ids[0], chat_group_id=ids[1],
            message=content,
        )
        proto = GroupMessageNotification(
            chat_id=ids[0], chat_group_id=ids[1],
            steamid_sender=0.0, message=content, timestamp=int(time()),
        )
        group = [g for g in self.groups if g.id == ids[1]][0]
        channel = GroupChannel(state=self, notification=proto, group=group)
        message = GroupMessage(proto=proto, channel=channel, author=self.client.user)
        self.dispatch('message', message)

    # parsers

    @register(EMsg.ServiceMethod)
    def parse_service_method(self, msg: MsgProto) -> None:
        if msg.header.target_job_name == 'FriendMessagesClient.IncomingMessage#1':
            msg.body: 'UserMessageNotification'
            user = self.get_user(int(msg.body.steamid_friend))

            if msg.body.chat_entry_type == EChatEntryType.ChatMsg:
                channel = DMChannel(state=self, participant=user)
                message = UserMessage(proto=msg.body, channel=channel)
                self.dispatch('message', message)

            if msg.body.chat_entry_type == EChatEntryType.Typing:
                when = datetime.utcfromtimestamp(msg.body.rtime32_server_timestamp)
                self.dispatch('typing', user, when)

        if msg.header.target_job_name == 'ChatRoomClient.NotifyIncomingChatMessage#1':
            msg.body: 'GroupMessageNotification'
            sent_in = None
            for group in self.groups:
                for channel in group.channels:
                    if channel.id == int(msg.body.chat_id):
                        sent_in = group
            if sent_in is None:
                return
            channel = GroupChannel(state=self, notification=msg.body, group=sent_in)
            user_id64 = int(msg.body.steamid_sender)
            author = self.client.get_user(user_id64)
            message = GroupMessage(proto=msg.body, channel=channel, author=author)
            self.dispatch('message', message)

    @register(EMsg.ServiceMethodResponse)
    async def parse_service_method_response(self, msg: MsgProto) -> None:
        if msg.header.target_job_name == 'ChatRoom.GetMyChatRoomGroups#1':
            msg.body: 'CChatRoom_GetMyChatRoomGroups_Response'
            for group in msg.body.chat_room_groups:
                group = Group(state=self, proto=group.group_summary)
                await group.__ainit__()
                self.groups.append(group)

    @register(EMsg.ClientFriendsGroupsList)
    def ready(self, _) -> None:
        self.client._handle_ready()

    @register(EMsg.ClientCMList)
    def parse_cm_list_update(self, msg: MsgProto) -> None:
        msg.body: 'CMsgClientCMList'
        log.debug('Updating CM list')
        self.client.ws.cm_list.clear()
        self.client.ws.cm_list.merge_list(msg.body.cm_websocket_addresses)

    @register(EMsg.ClientPersonaState)
    async def parse_persona_state_update(self, msg: MsgProto) -> None:
        msg.body: 'CMsgClientPersonaState'
        for friend in msg.body.friends:
            data = friend.to_dict(snakecase)
            if not data:
                continue
            user_id64 = int(friend.friendid)
            if user_id64 == self._id64:
                continue
            before = after = self.get_user(user_id64)
            if after is None:  # they're private
                continue  # TODO maybe request from ws?

            try:
                data = self.patch_user_from_ws(data, friend)
            except (KeyError, TypeError):
                steam_id = SteamID(user_id64)
                invitee = await self.fetch_user(steam_id.id64) or steam_id
                invite = UserInvite(self, invitee)
                self.dispatch('user_invite', invite)

            old = [getattr(before, attr) for attr in self.user_slots]
            after._update(data)
            new = [getattr(after, attr) for attr in self.user_slots]
            if old != new:
                self._users[after.id64] = after
                self.dispatch('user_update', before, after)

    def patch_user_from_ws(self, data: dict, friend: 'CMsgClientPersonaStateFriend') -> dict:
        data['personaname'] = friend.player_name
        hash = (friend.avatar_hash.hex() if data['avatar_hash'] != '\x00' * 20
                else 'fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb')
        data['avatarfull'] = (f'https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/'
                              f'{hash[:2]}/{hash}_full.jpg')

        if friend.last_logoff:
            data['lastlogoff'] = friend.last_logoff
        data['gameextrainfo'] = friend.game_name if friend.game_name else None
        data['personastate'] = friend.persona_state
        data['personastateflags'] = friend.persona_state_flags
        return data

    @register(EMsg.ClientFriendsList)
    async def process_friends(self, msg: MsgProto) -> None:
        msg.body: 'CMsgClientFriendsList'
        for user in msg.body.friends:
            if user.efriendrelationship in (EFriendRelationship.RequestInitiator,
                                            EFriendRelationship.RequestRecipient):
                steam_id = SteamID(user.ulfriendid)
                if steam_id.type == EType.Individual:
                    invitee = await self.fetch_user(steam_id.id64) or steam_id
                    invite = UserInvite(self, invitee)
                    self.dispatch('user_invite', invite)
                    self.invites.append(invitee)
                if steam_id.type == EType.Clan:
                    resp = await self.request('GET', f'{URL.COMMUNITY}/my/groups/pending?ajax=1')
                    search = re.search(rf'data-miniprofile="(\d+)".*?\'group_accept\', \'{steam_id.id64}\',',
                                       resp, flags=re.S)
                    invitee = await self.client.fetch_user(search.group(1))
                    clan = await self.client.fetch_clan(steam_id.id64)
                    invite = ClanInvite(state=self, invitee=invitee, clan=clan)
                    self.dispatch('clan_invite', invite)
                    self.invites.append(clan)
            if user.efriendrelationship == EFriendRelationship.Friend:
                steam_id = SteamID(user.ulfriendid)
                if steam_id.type == EType.Individual:
                    invitee = await self.fetch_user(steam_id.id64) or steam_id
                    if invitee in self.invites:
                        self.dispatch('user_invite_accept', invitee)
                if steam_id.type == EType.Clan:
                    clan = await self.client.fetch_clan(steam_id.id64) or steam_id
                    if clan in self.invites:
                        self.dispatch('clan_invite_accept', clan)

    @register(EMsg.ClientCommentNotifications)
    async def handle_comments(self, msg: MsgProto) -> None:
        msg.body: 'CMsgClientCommentNotifications'
        for _ in range(msg.body.count_new_comments):
            comment = await self._parse_comment()
            self._obj = None
            self.dispatch('comment', comment)
        await self.http.clear_notifications()

    @register(EMsg.ClientUserNotifications)
    async def parse_notification(self, msg: MsgProto):
        msg.body: 'CMsgClientUserNotifications'
        for notification in msg.body.notifications:
            if notification.type == 1:  # received a trade offer
                self.loop.create_task(self._poll_trades())  # watch trades for changes
        await self.http.clear_notifications()
