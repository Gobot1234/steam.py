import re
from datetime import datetime

from .enums import Game, URL, ETradeOfferState
from .errors import ClientException


class TradeOffer:
    """Represents a Trade offer from a User.

    Attributes
    -------------
    partner: class:`~steam.User`
        The trade offer partner.
    items_to_give: List[`Item`]
        A list of items to give to the trade partner.
    items_to_receive: List[`Item`]
        A list of items to receive from the.
    state:
        The offer state of the trade for the possible types see
        :class:`~enums.ETradeOfferState`.
    message: :class:`str`
        The message included with the trade offer.
    is_our_offer: :class:`bool`
        Whether the offer was created by the ClientUser.
    id: :class:`int`
        The trade offer id of the trade.
    expires: :class:`datetime.datetime`
        The time at which the trade automatically expires.
    escrow: Optional[class:`datetime.datetime`]
        The time at which the escrow will end. Can be None
        if there is no escrow on the trade.
    is_one_sided: :class:`bool`
        Whether the offer is one sided towards the user.
    """

    __slots__ = ('partner', 'message', 'state', 'is_our_offer', 'id',
                 'expires', 'escrow', 'is_one_sided', 'items_to_give',
                 'items_to_receive', '_sent', '_counter', '_state', '_data')

    def __init__(self, state, data):
        self._state = state
        self._data = data
        self._update(data)

    def _update(self, data):
        self.message = data['message'] or None
        self.is_our_offer = data['is_our_offer']

        self.id = int(data['tradeofferid'])
        self.expires = datetime.utcfromtimestamp(data['expiration_time'])
        self.escrow = datetime.utcfromtimestamp(data['escrow_end_date']) \
            if data['escrow_end_date'] != 0 else None
        self.partner = self._state.loop.run_until_complete(self._fetch_partner())
        self.is_one_sided = True if 'items_to_give' not in data.keys() and 'items_to_receive' in data.keys() else False
        self.state = ETradeOfferState(data.get('trade_offer_state', 1))

        self.items_to_give = \
            self._state.loop.run_until_complete(self.fetch_items(
                user_id64=self._state.client.user.id64,
                assets=data['items_to_give']
            )) if 'items_to_give' in data.keys() else []
        self.items_to_receive = \
            self._state.loop.run_until_complete(self.fetch_items(
                user_id64=self.partner.id64,
                assets=data['items_to_receive']
            )) if 'items_to_receive' in data.keys() else []
        self._counter = 0
        self._sent = True if self.id else False

    async def _fetch_partner(self):
        resp = await self._state.request('GET', url=f'{URL.COMMUNITY}/tradeoffer/{self.id}')
        user_id = re.search(r"var g_ulTradePartnerSteamID = '(?:.*?)';", resp)
        return await self._state.client.fetch_user(user_id)

    async def update(self):
        data = await self._state.http.fetch_trade(self.id)
        self._update(data)
        return self

    async def accept(self):
        if self.state != ETradeOfferState.Active:
            raise ClientException('This trade is not active')
        await self._state.http.accept_trade(self.id)
        self.state = ETradeOfferState.Accepted
        self._state.dispatch('trade_accept', self)

    async def decline(self):
        if self.state != ETradeOfferState.Active and self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade is not active')
        elif self.is_our_offer:
            raise ClientException('You cannot decline an offer the ClientUser has made')
        await self._state.http.decline_user_trade(self.id)
        self.state = ETradeOfferState.Declined
        self._state.dispatch('trade_decline', self)

    async def cancel(self):
        if self.state != ETradeOfferState.Active and self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade is not active')
        if not self.is_our_offer:
            raise ClientException("Offer wasn't created by the ClientUser and therefore cannot be canceled")
        await self._state.http.cancel_user_trade(self.id)
        self.state = ETradeOfferState.Canceled
        self._state.dispatch('trade_cancel', self)

    async def fetch_items(self, user_id64, assets):
        return await self._state.http.fetch_user_items(user_id64=user_id64, assets=assets)


class Inventory:
    """Represents a User's inventory.

    Attributes
    -------------
    items: List[class:`Item`]
        A list of the inventories owner's items.
    owner: class:`~steam.User`
        The owner of the inventory.
    game: class:`steam.Game`
        The game the inventory the game belongs to.
    """

    __slots__ = ('items', 'owner', 'game', '_data', '_state')

    def __init__(self, state, data, owner):
        self._state = state
        self.owner = owner
        self.items = []
        self._update(data)

    def __repr__(self):
        return "<Inventory game={0.game!r} owner={0.owner!r} len={1}>".format(self, len(self))

    def __len__(self):
        return self._data['total_inventory_count']

    def _update(self, data):
        self._data = data
        self.game = Game(app_id=int(data['assets'][0]['appid']), is_steam_game=False)
        for raw_item in data['assets']:
            instance_id = raw_item['instanceid']
            for item_desc in data['descriptions']:
                if raw_item['instanceid'] == instance_id:
                    self.items.append(Item(data=self._merge_item(raw_item, item_desc)))
                    continue
            self.items.append(Item(data=raw_item, missing=True))
            continue

    def _merge_item(self, raw_item, desc):
        for key, value in raw_item.items():
            desc[key] = value
        return desc

    def filter_items(self, item_name: str):
        """Filters items by name into a list of one type of item

        Parameters
        ------------
        item_name: `str`
            The item to filter

        Returns
        ---------
        Items: :class:`list`
            List of `Item`s
        """
        return [item for item in self.items if item.name == item_name]

    def get_item(self, item_name: str):
        """Get an item by name from a :class:`Inventory`

        Parameters
        ----------
        item_name: `str`
            The item to get from the inventory

        Returns
        -------
        Item: :class:`Item`
            Returns the first found item with a matching name.
            This also removes the item from the inventory.
        """
        item = [item for item in self.items if item.name == item_name][0]
        self.items.remove(item)
        return item

    async def update_inventory(self):
        """|coro|
        Update an :class:`~steam.User`'s :class:`Inventory`

        Returns
        -------
        Inventory: :class:`Inventory`
        """
        resp = await self._state.request('GET', f'{URL.COMMUNITY}/inventory/{self.owner.id64}/'
                                                f'{self.game.app_id}/{self.game.context_id}')
        if not resp['success']:
            return None
        return Inventory(state=self._state, data=resp, owner=self.owner)


class Asset:
    __slots__ = ('id', 'game', 'app_id', 'class_id', 'amount', 'instance_id')

    def __init__(self, data):
        self.id = data['assetid']
        self.game = Game(app_id=data['appid'])
        self.app_id = data['appid']
        self.amount = int(data['amount'])
        self.instance_id = data['instanceid']
        self.class_id = data['classid']

    def __repr__(self):
        return "<Asset id={0.id} app_id={0.app_id} amount={0.amount} instance_id={0.instance_id} " \
               "class_id={0.class_id} game={0.game!r}>".format(self)

    def __iter__(self):
        for key, value in zip(('assetid', 'amount', 'appid', 'contextid'),
                              (self.id, self.amount, self.game.app_id, str(self.game.context_id))):
            yield (key, value)


class Item(Asset):
    """Represents an item in an User's inventory.

    Attributes
    -------------
    name: class:`str`
        The name of the item.
    asset: class:`Asset`
        The item as an asset.
    game: class:`~steam.Game`
        The game the item is from.
    asset_id: class:`str`
        The assetid of the item.
    app_id: class:`str`
        The appid of the item.
    amount: class:`int`
        The amount of the item the inventory contains.
    instance_id: class:`str`
        The instanceid of the item.
    class_id: class:`str`
        The classid of the item.
    colour: Optional[class:`int`]
        The colour of the item.
    market_name: Optional[class:`str`]
        The market_name of the item.
    descriptions: Optional[class:`str`]
        The descriptions of the item.
    type: Optional[class:`str`]
        The type of the item.
    tags: Optional[class:`str`]
        The tags of the item.
    is_tradable: Optional[class:`bool`]
        Whether or not the item is tradable.
    is_marketable: Optional[class:`bool`]
        Whether or not the item is marketable.
    icon_url: Optional[class:`str`]
        The icon_url of the item.
    icon_url_large: Optional[class:`str`]
        The icon_url_large of the item.

    """

    __slots__ = ('name', 'game', 'asset', 'asset_id', 'app_id', 'colour', 'market_name',
                 'descriptions', 'type', 'tags', 'class_id', 'is_tradable',
                 'is_marketable', 'amount', 'instance_id', 'icon_url',
                 'icon_url_large', 'missing')

    def __init__(self, data, missing: bool = False):
        super().__init__(data)
        self.missing = missing
        self._update(data)

    def __repr__(self):
        return "<Item name='{0.name}' asset={0.asset!r} is_tradable={0.is_tradable} " \
               "is_marketable={0.is_marketable}>".format(self)

    def _update(self, data):
        self.asset = Asset(data)
        self.game = self.asset.game
        self.asset_id = self.asset.id
        self.app_id = self.asset.app_id
        self.amount = self.asset.amount
        self.instance_id = self.asset.instance_id
        self.class_id = self.asset.class_id

        self.name = data.get('name')
        self.colour = int(data['name_color'], 16) if 'name_color' in data.keys() else None
        self.market_name = data.get('market_name')
        self.descriptions = data.get('descriptions')
        self.type = data.get('type')
        self.tags = data.get('tags')
        self.is_tradable = bool(data['tradable']) if 'tradable' in data.keys() else None
        self.is_marketable = bool(data['marketable']) if 'marketable' in data.keys() else None
        self.icon_url = f'https://steamcommunity-a.akamaihd.net/economy/image/{data.get("icon_url")}' \
            if 'icon_url' in data.keys() else None
        self.icon_url_large = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url_large"]}' \
            if 'icon_url_large' in data.keys() else None
