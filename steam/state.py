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

from .enums import EChatEntryType, ETradeOfferState
from .protobufs import get_um, MsgProto, EMsg
from .trade import TradeOffer
from .user import User
from .utils import proto_fill_from_dict


class State:
    __slots__ = ('loop', 'http', 'client', 'dispatch', 'confirmation_manager', 'request', '_users', '_trades')

    def __init__(self, loop, client, http):
        self.loop = loop
        self.http = http
        self.request = http.request
        self.client = client
        self.dispatch = client.dispatch
        self.confirmation_manager = http._confirmation_manager

        self._trades = dict()  # TODO add weakref
        self._users = dict()

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

        return await self.send_job(message)

    @property
    def users(self):
        return list(self._users.values())

    @property
    def trades(self):
        return list(self._trades.values())

    async def fetch_user(self, id64):
        resp = await self.http.fetch_profile(id64)
        data = resp['response']['players'][0] if resp['response']['players'][0] else None
        if data:
            return self._store_user(data)
        return None

    def get_user(self, id64):
        return self._users.get(id64)

    async def ensure_user(self, id64):
        return self.get_user(id64) or await self.fetch_user(id64)

    def _store_user(self, data):
        try:
            return self._users[int(data['steamid'])]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id64] = user
            return user

    def get_trade(self, trade_id):
        return self._trades.get(trade_id)

    async def fetch_trade(self, trade_id):
        data = await self.http.fetch_trade(trade_id)
        data = data['response']['offer']
        if data:
            trade = self._store_trade(data)
            await trade.__ainit__()
            return trade
        return None

    def _store_trade(self, data):
        try:
            trade = self._trades[data['tradeofferid']]
        except KeyError:
            trade = TradeOffer(state=self, data=data, partner=None)
            self._trades[trade.id] = trade
        else:
            if data['trade_offer_state'] != trade.state:
                trade.state = ETradeOfferState(data['trade_offer_state'])
                name = trade.state.name.lower()
                event_name = name[:-2] if name != 'declined' else 'decline'
                self.dispatch(event_name, trade)
        return trade

    def send_message(self, steam_id, content):
        self.send_um(
            "FriendMessages.SendMessage#1",
            {
                'steamid': steam_id,
                'message': content,
                'chat_entry_type': EChatEntryType.ChatMsg,
            }
        )
