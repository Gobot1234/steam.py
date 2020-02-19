from collections import OrderedDict
from datetime import datetime

from .enums import Game, URL, ETradeOfferState
from .errors import ClientException


class TradeOffer:
    """Represents a Trade offer from a User"""
    # TODO add attrs and docstrings to methods

    __slots__ = ('partner', 'message', 'state', 'is_our_offer', 'id',
                 'expires', 'escrow', 'is_one_sided', 'to_give',
                 'to_receive', '_sent', '_counter', '_state')

    def __init__(self, state, data):
        self._state = state
        self._update(data)

    def _update(self, data):
        self.partner = data['partner']
        self.message = data['message'] or None
        self.state = data['tradeofferstate']
        self.is_our_offer = data['is_our_offer']

        self.id = int(data['tradeofferid'])
        self.expires = datetime.utcfromtimestamp(data['expiration_time']).now()
        self.escrow = datetime.utcfromtimestamp(data['escrow_end_date']).now() \
            if data['escrow_end_date'] != 0 else None
        self.partner = self._state.loop.create_task(
            self._state.client.fetch_user(data['accountid_other'] + 76561197960265728))
        # I'm not too sure about this one if anyone knows if this is correct or incorrect make a PR
        self.is_one_sided = True if 'items_to_give' not in data.keys() and 'items_to_receive' in data.keys() else False
        self.state = ETradeOfferState(data.get('trade_offer_state', 1))

        self.to_give = \
            self._state.loop.create_task(self.fetch_items(
                user_id64=self._state.client.user.id64,
                assets=data['items_to_give']
            )) if 'items_to_give' in data.keys() else []
        self.to_receive = \
            self._state.loop.create_task(self.fetch_items(
                user_id64=self._state.client.user.id64,
                assets=data['items_to_receive']
            )) if 'items_to_receive' in data.keys() else []
        self._counter = 0
        self._sent = True if self.id else False

    async def update(self):
        data = await self._state.http.fetch_trade(self.id)
        self._update(data)
        return self

    async def accept(self):
        if self.state != ETradeOfferState.Active:
            raise ClientException('This trade is not active')
        await self._state.http.accept_trade(self.id, )

    async def decline(self):
        if self.state != ETradeOfferState.Active and self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade is not active')
        elif self.is_our_offer:
            raise ClientException('You cannot decline an offer the ClientUser has made')

        data = {
            "key": self._state.http.api_key,
            "tradeofferid": self.id
        }
        await self._state.request('POST', url=f'{URL.API}/IEconService/DeclineTradeOffer/v1', data=data)

    async def cancel(self):
        if self.state != ETradeOfferState.Active and self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade is not active')
        if not self.is_our_offer:
            raise ClientException("Offer wasn't created by the ClientUser and therefore cannot be canceled")

        data = {
            "key": self._state.http.api_key,
            "tradeofferid": self.id
        }
        await self._state.request('POST', url=f'{URL.API}/IEconService/CancelTradeOffer/v1', data=data)

    async def fetch_items(self, user_id64, assets):
        items = []
        app_ids = list(OrderedDict.fromkeys([item['appid'] for item in assets]))  # remove duplicate  app_ids
        context_ids = list(OrderedDict.fromkeys([item['contextid'] for item in assets]))  # and ctx_ids without setting
        # as setting orders them
        for app_id, context_id in zip(app_ids, context_ids):
            inv = await self._state.request('GET', url=f'{URL.COMMUNITY}/inventory/{user_id64}/{app_id}/{context_id}')
            inventory = Inventory(state=self._state, data=inv, owner=await self._state.client.fetch_user(user_id64))
            items.extend(inventory.items)
        return items


class Inventory:
    """Represents a Users inventory"""

    __slots__ = ('items', 'owner', 'game', '_inventory', '_state')

    def __init__(self, state, data, owner):
        self._state = state
        self.owner = owner
        self._update(data)

    def __repr__(self):
        return "<Inventory game={0.game!r} owner={0.owner!r}>".format(self)

    def __len__(self):
        return self._inventory['total_inventory_count']

    def _update(self, data):
        self._inventory = data
        self.game = Game(app_id=int(list(data['rgDescriptions'].values())[0]['appid']), is_steam_game=False)
        self.items = []
        for _, item_id in data['rgInventory'].items():
            _id = f'{item_id["classid"]}_{item_id["instanceid"]}'
            item_desc = data['rgDescriptions'].get(_id)
            if item_desc is None:
                self.items.append(Item(data=item_id, missing=True))
                continue
            self.items.append(Item(data=self._merge_item(item_id, item_desc)))

    def _merge_item(self, item_id, desc):
        for key, value in item_id.items():
            desc[key] = value
        return desc

    def filter_items(self, item_name: str):
        """Filters items by name into a list of one type of item

        Parameters
        ----------
        item_name: `str`
            The item to filter

        Returns
        -------
        Items: :class:`list`
            List of `~steam.Item`s
        """
        return [item for item in self.items if item.name == item_name]

    def get_item(self, item_name: str):
        """Get an item by name from a :class:`~steam.Inventory`

        Parameters
        ----------
        item_name: `str`
            The item to get from the inventory

        Returns
        -------
        Item: :class:`~steam.Item`
            Returns the first found item with a matching name.
            This also removes the item from the inventory.
        """
        item = [item for item in self.items if item.name == item_name][0]
        self.items.remove(item)
        return item

    async def update_inventory(self):
        """|coro|
        Update an :class:`~steam.User`'s :class:`~steam.Inventory`

        Returns
        -------
        Inventory: :class:`~steam.Inventory`
        """
        resp = await self._state.request('GET', f'{URL.COMMUNITY}/inventory/{self.owner.id64}/'
                                                f'{self.game.app_id}/{self.game.context_id}')
        if not resp['success']:
            return None
        return Inventory(state=self._state, data=resp, owner=self.owner)


class Item:
    """Represents an item in an User's inventory"""

    __slots__ = ('name', 'asset_id', 'app_id', 'colour', 'market_name',
                 'descriptions', 'type', 'tags', 'class_id', 'game',
                 'icon_url', 'icon_url_large', 'marketable', 'tradable',
                 'missing', 'amount', 'instance_id')

    def __init__(self, data, missing: bool = False):
        self.missing = missing
        self._update(data)

    def __repr__(self):
        return "<Item name='{0.name}' asset_id={0.asset_id} game={0.game!r} tradable={0.tradable} " \
               "marketable={0.marketable}>".format(self)

    def _update(self, data):
        self.name = data['name']
        self.asset_id = data.get('id')
        self.app_id = data['appid']
        self.colour = int(data['name_color'], 16)
        self.market_name = data['market_name']
        self.descriptions = data['descriptions']
        self.type = data['type']
        self.tags = data['tags']
        self.class_id = int(data['classid'])
        self.tradable = bool(data['tradable'])
        self.marketable = bool(data['marketable'])
        self.amount = int(data['amount'])
        self.instance_id = data['instanceid']
        self.icon_url = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url"]}'
        self.icon_url_large = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url_large"]}'
        self.game = Game(app_id=data['appid'])
