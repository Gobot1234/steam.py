from datetime import datetime

from .enums import Game, ETradeOfferState
from .errors import ClientException


class TradeOffer:
    """Represents a Trade offer from a User.

    Attributes
    -------------
    partner: :class:`~steam.User`
        The trade offer partner.
    items_to_give: List[:class:`Item`]
        A list of items to give to the partner.
    items_to_receive: List[:class:`Item`]
        A list of items to receive from the partner.
    state: :class:`~steam.ETradeOfferState`
        The offer state of the trade for the possible types see
        :class:`~steam.ETradeOfferState`.
    message: :class:`str`
        The message included with the trade offer.
    is_our_offer: :class:`bool`
        Whether the offer was created by the ClientUser.
    id: :class:`int`
        The trade offer id of the trade.
    expires: :class:`datetime.datetime`
        The time at which the trade automatically expires.
    escrow: Optional[:class:`datetime.datetime`]
        The time at which the escrow will end. Can be None
        if there is no escrow on the trade.
    """

    __slots__ = ('partner', 'message', 'state', 'is_our_offer', 'id',
                 'expires', 'escrow', 'items_to_give', 'items_to_receive',
                 '_state', '_data', '__weakref__')

    def __init__(self, state, data, partner):
        self._state = state
        self.partner = partner
        self._update(data)

    def __repr__(self):
        attrs = (
            'id', 'partner'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<TradeOffer {' '.join(resolved)}>"

    def _update(self, data):
        self.message = data['message'] or None
        self.is_our_offer = data['is_our_offer']
        self.id = int(data['tradeofferid'])
        self.expires = datetime.utcfromtimestamp(data['expiration_time'])
        self.escrow = datetime.utcfromtimestamp(data['escrow_end_date']) if data['escrow_end_date'] != 0 else None
        self.state = ETradeOfferState(data.get('trade_offer_state', 1))
        self._data = data

    async def __ainit__(self):
        if self.partner is None:  # not great cause this can be your account sometimes
            self.partner = await self._state.client.fetch_user(self._data['accountid_other'])
        self.items_to_give = await self.fetch_items(
            user_id64=self._state.client.user.id64,
            assets=self._data['items_to_receive']
        ) if 'items_to_receive' in self._data else []

        self.items_to_receive = await self.fetch_items(
            user_id64=self.partner.id64,
            assets=self._data['items_to_give']
        ) if 'items_to_give' in self._data else []

    async def update(self):
        data = await self._state.http.fetch_trade(self.id)
        await self.__ainit__()
        self._update(data)
        return self

    async def confirm(self):
        """|coro|
        Confirm a :class:`TradeOffer`"""
        if self.state != ETradeOfferState.Active:
            raise ClientException('This trade is not active')
        confirmation = await self._state.confirmation_manager.get_trade_confirmation(self.id)
        await confirmation.confirm()

    async def accept(self):
        """|coro|
        Accept a :class:`TradeOffer`"""
        if self.state != ETradeOfferState.Active:
            raise ClientException('This trade is not active')
        await self._state.http.accept_trade(self.id)
        self.state = ETradeOfferState.Accepted
        self._state.dispatch('trade_accept', self)

    async def decline(self):
        """|coro|
        Decline a :class:`TradeOffer`"""
        if self.state != ETradeOfferState.Active and self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade is not active')
        elif self.is_our_offer:
            raise ClientException('You cannot decline an offer the ClientUser has made')
        await self._state.http.decline_user_trade(self.id)
        self.state = ETradeOfferState.Declined
        self._state.dispatch('trade_decline', self)

    async def cancel(self):
        """|coro|
        Cancel a :class:`TradeOffer`"""
        if self.state != ETradeOfferState.Active and self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade is not active')
        if not self.is_our_offer:
            raise ClientException("Offer wasn't created by the ClientUser and therefore cannot be canceled")
        await self._state.http.cancel_user_trade(self.id)
        self.state = ETradeOfferState.Canceled
        self._state.dispatch('trade_cancel', self)

    async def fetch_items(self, user_id64, assets):
        items_ = await self._state.http.fetch_trade_items(user_id64=user_id64, assets=assets)
        items = []
        for asset in assets:
            for item in items_:
                if item.asset_id == asset['assetid'] and item.class_id == asset['classid'] \
                        and item.instance_id == asset['instanceid']:
                    ignore = False
                    if item.name is None:
                        # this is awful I am aware but it is necessary to not get identical items and assets
                        for item_ in items:
                            if item.asset == item_.asset:
                                ignore = True
                    if not ignore:  # this is equally dumb
                        items.append(item)
                    continue
        return items

    def is_one_sided(self):
        """Checks if an offer is one-sided towards the ClientUser"""
        return True if self.items_to_receive and not self.items_to_give else False


class Inventory:
    """Represents a User's inventory.

    .. container:: operations

        .. describe:: len(x)

            Returns how large the inventory is.

    Attributes
    -------------
    items: List[:class:`Item`]
        A list of the inventories owner's items.
    owner: :class:`~steam.User`
        The owner of the inventory.
    game: :class:`steam.Game`
        The game the inventory the game belongs to.
    """

    __slots__ = ('items', 'owner', 'game', '_data', '_state')

    def __init__(self, state, data, owner):
        self._state = state
        self.owner = owner
        self.items = []
        self._update(data)

    def __repr__(self):
        attrs = (
            'owner', 'game'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Inventory {' '.join(resolved)}>"

    def __len__(self):
        return self._data['total_inventory_count']

    def _update(self, data):
        self._data = data
        self.game = Game(app_id=int(data['assets'][0]['appid']), is_steam_game=False)
        for asset in data['assets']:
            for item in data['descriptions']:
                if item['instanceid'] == asset['instanceid'] and item['classid'] == asset['classid']:
                    item.update(asset)
                    self.items.append(Item(data=item))
                    continue
            self.items.append(Item(data=asset, missing=True))
            continue

    def filter_items(self, item_name: str):
        """Filters items by name into a list of one type of item.

        Parameters
        ------------
        item_name: :class:`str`
            The item to filter.

        Returns
        ---------
        Items: List[:class:`Item`]
            List of :class:`Item`s. This also removes the item from the inventory.
        """
        items = [item for item in self.items if item.name == item_name]
        for item in items:
            self.items.remove(item)
        return items

    def get_item(self, item_name: str):
        """Get an item by name from a :class:`Inventory`.

        Parameters
        ----------
        item_name: `str`
            The item to get from the inventory.

        Returns
        -------
        Item: :class:`Item`
            Returns the first found item with a matching name.
            This also removes the item from the inventory.
        """
        item = [item for item in self.items if item.name == item_name][0]
        self.items.remove(item)
        return item


class Asset:
    __slots__ = ('id', 'app_id', 'class_id', 'amount', 'instance_id', 'game')

    def __init__(self, data):
        self.id = data['assetid']
        self.game = Game(app_id=data['appid'])
        self.app_id = data['appid']
        self.amount = int(data['amount'])
        self.instance_id = data['instanceid']
        self.class_id = data['classid']

    def __repr__(self):
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in self.__slots__]
        return f"<Asset {' '.join(resolved)}>"

    def __iter__(self):
        steam_names = ('assetid', 'amount', 'appid', 'contextid')
        pythonic_names = (self.id, self.amount, self.game.app_id, str(self.game.context_id))
        for key, value in zip(steam_names, pythonic_names):
            yield (key, value)

    def __eq__(self, other):
        return isinstance(other, Asset) and \
               False not in [getattr(self, attr) == getattr(other, attr) for attr in self.__slots__]

    def __ne__(self, other):
        return not self.__eq__(other)


class Item(Asset):
    """Represents an item in an User's inventory.

    .. container:: operations

        .. describe:: x == y

            Checks if two items are equal.

        .. describe:: x != y

            Checks if two items are not equal.

    Attributes
    -------------
    name: `str`
        The name of the item.
    asset: :class:`Asset`
        The item as an asset.
    game: :class:`~steam.Game`
        The game the item is from.
    asset_id: :class:`str`
        The assetid of the item.
    app_id: :class:`str`
        The appid of the item.
    amount: :class:`int`
        The amount of the item the inventory contains.
    instance_id: :class:`str`
        The instanceid of the item.
    class_id: :class:`str`
        The classid of the item.
    colour: Optional[:class:`int`]
        The colour of the item.
    market_name: Optional[:class:`str`]
        The market_name of the item.
    descriptions: Optional[:class:`str`]
        The descriptions of the item.
    type: Optional[:class:`str`]
        The type of the item.
    tags: Optional[:class:`str`]
        The tags of the item.
    icon_url: Optional[:class:`str`]
        The icon_url of the item.
    icon_url_large: Optional[:class:`str`]
        The icon_url_large of the item.
    """

    __slots__ = ('name', 'game', 'asset', 'asset_id', 'app_id', 'colour', 'market_name',
                 'descriptions', 'type', 'tags', 'class_id', 'amount', 'instance_id',
                 'icon_url', 'icon_url_large', 'missing', '_data')

    def __init__(self, data, missing: bool = False):
        super().__init__(data)
        self.missing = missing
        self._from_data(data)

    def __repr__(self):
        attrs = (
            'name', 'asset',
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Item {' '.join(resolved)}>"

    def _from_data(self, data):
        self.asset = Asset(data)
        self.game = self.asset.game
        self.asset_id = self.asset.id
        self.app_id = self.asset.app_id
        self.amount = self.asset.amount
        self.instance_id = self.asset.instance_id
        self.class_id = self.asset.class_id

        self.name = data.get('name')
        self.colour = int(data['name_color'], 16) if 'name_color' in data else None
        self.market_name = data.get('market_name')
        self.descriptions = data.get('descriptions')
        self.type = data.get('type')
        self.tags = data.get('tags')
        self.icon_url = f'https://steamcommunity-a.akamaihd.net/economy/image/{data.get("icon_url")}' \
            if 'icon_url' in data else None
        self.icon_url_large = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url_large"]}' \
            if 'icon_url_large' in data else None
        self._data = data

    def is_tradable(self) -> bool:
        """Whether or not the item is tradable."""
        return bool(self._data.get('tradable', False))

    def is_marketable(self) -> bool:
        """Whether or not the item is marketable."""
        bool(self._data.get('marketable', False))
