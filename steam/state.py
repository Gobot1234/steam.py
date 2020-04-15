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

import aiohttp

from .enums import EChatEntryType, ETradeOfferState
from .protobufs import get_um, MsgProto, EMsg
from .trade import TradeOffer
from .user import User
from .utils import proto_fill_from_dict

log = logging.getLogger(__name__)


class State:

    def __init__(self, loop, client, http):
        self.loop = loop
        self.http = http
        self.request = http.request
        self.client = client
        self.dispatch = client.dispatch
        self.started_poll = False

        self._trades = dict()  # TODO add weakref
        self._users = dict()

        self._current_job_id = 0

    def _handle_ready(self):
        self.client._ready.set()

    async def send_um(self, name, params=None):
        proto = get_um(name)

        if proto is None:
            raise ValueError(f'Failed to find method named: {name}')

        message = MsgProto(EMsg.ServiceMethodCallFromClient)
        message.header.target_job_name = name
        message.body = proto()

        if params:
            proto_fill_from_dict(message.body, params)

        job_id = self._current_job_id = ((self._current_job_id + 1) % 10000) or 1

        if message.proto:
            message.header.jobid_source = job_id
        else:
            message.header.sourceJobID = job_id

        await self.client.ws.send(message)

    async def send_message(self, user_id64, content):
        await self.send_um(
            "FriendMessages.SendMessage#1",
            {
                'steamid': user_id64,
                'message': content,
                'chat_entry_type': EChatEntryType.ChatMsg,
            }
        )

    async def send_job(self, message, body_params=None):
        job_id = self._current_job_id = ((self._current_job_id + 1) % 10000) or 1

        if message.proto:
            message.header.jobid_source = job_id
        else:
            message.header.sourceJobID = job_id

        await self.client.ws.send(message, body_params)

    @property
    def users(self):
        return list(self._users.values())

    @property
    def trades(self):
        return list(self._trades.values())

    async def fetch_user(self, id64):
        resp = await self.http.fetch_profile(id64)
        data = resp['response']['players'][0] if resp['response']['players'] else None
        if data:
            return self._store_user(data)
        return None

    def get_user(self, id64):
        return self._users.get(id64)

    def _store_user(self, data):
        try:
            user = self._users[int(data['steamid'])]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id64] = user
        return user

    def get_trade(self, trade_id):
        return self._trades.get(trade_id)

    async def fetch_trade(self, trade_id):
        resp = await self.http.fetch_trade(trade_id)
        if resp.get('response'):
            trade = resp['response']['offer']
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
                return
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
                    ], return_when=asyncio.FIRST_COMPLETED, timeout=7.5)
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

    async def poll_trades(self):
        if self.started_poll:
            return
        else:
            self._trade_poll_loop = self.loop.create_task(self._poll_trades())

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
            self._trade_poll_loop = self.loop.create_task(self._poll_trades())
        finally:
            log.info('Closing polling of trades')
            self._trade_poll_loop.cancel()