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

from datetime import datetime
from typing import List

from .enums import ETradeOfferState
from .errors import ClientException
from .models import Game


class TradeOffer:
    """Represents a Trade offer from a User.

    Attributes
    -------------
    partner: :class:`~steam.User`
        The trade offer partner.
    items_to_send: List[:class:`Item`]
        A list of items to send to the partner.
    items_to_receive: List[:class:`Item`]
        A list of items to receive from the partner.
    state: :class:`~steam.ETradeOfferState`
        The offer state of the trade for the possible types see
        :class:`~steam.ETradeOfferState`.
    message: :class:`str`
        The message included with the trade offer.
    id: :class:`int`
        The trade offer id of the trade.
    expires: :class:`datetime.datetime`
        The time at which the trade automatically expires.
    escrow: Optional[:class:`datetime.datetime`]
        The time at which the escrow will end. Can be None
        if there is no escrow on the trade.
    """

    __slots__ = ('id', 'state', 'escrow', 'partner', 'message',
                 'expires', 'items_to_send', 'items_to_receive',
                 '_id_other', '_state', '_is_our_offer', '__weakref__')

    def __init__(self, state, data):
        self._state = state
        self._update(data)

    def __repr__(self):
        attrs = (
            'id', 'state', 'partner'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<TradeOffer {' '.join(resolved)}>"

    def _update(self, data):
        self.message = data['message'] or None
        self.id = int(data['tradeofferid'])
        self.expires = datetime.utcfromtimestamp(data['expiration_time'])
        self.escrow = datetime.utcfromtimestamp(data['escrow_end_date']) if data['escrow_end_date'] != 0 else None
        self.state = ETradeOfferState(data.get('trade_offer_state', 1))
        self.items_to_send = [Item(data=item) for item in data.get('items_to_give', [])]
        self.items_to_receive = [Item(data=item) for item in data.get('items_to_receive', [])]
        self._is_our_offer = data['is_our_offer']
        self._id_other = data['accountid_other']

    async def __ainit__(self):
        self.partner = await self._state.client.fetch_user(self._id_other)

    async def confirm(self):
        """|coro|
        Confirms the :class:`TradeOffer`.
        This rarely needs to be called as the client handles most of these.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is not active.
        """
        if self.state != ETradeOfferState.ConfirmationNeed:
            raise ClientException('This trade cannot be confirmed')
        if self.is_one_sided():  # we don't need to confirm gifts
            return
        confirmation = await self._state.confirmation_manager.get_trade_confirmation(self.id)
        await confirmation.confirm()

    async def accept(self):
        """|coro|
        Accepts the :class:`TradeOffer`.
        This also calls :meth:`TradeOffer.confirm`.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already accepted or not from the ClientUser.
        """
        if self.state != ETradeOfferState.Active:
            raise ClientException('This trade is not active')
        if self.state == ETradeOfferState.Accepted:
            raise ClientException('This trade has already been accepted')
        if self.is_our_offer():
            raise ClientException('You cannot accept an offer the ClientUser has made')
        await self._state.http.accept_trade(self.id)
        confirmation = await self._state.confirmation_manager.get_trade_confirmation(self.id)
        await confirmation.confirm()

    async def decline(self):
        """|coro|
        Declines the :class:`TradeOffer`

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already declined or not from the ClientUser.
        """
        if self.state not in (ETradeOfferState.Active or ETradeOfferState.ConfirmationNeed):
            raise ClientException('This trade is not active')
        if self.state == ETradeOfferState.Declined:
            raise ClientException('This trade has already been declined')
        if self.is_our_offer():
            raise ClientException('You cannot decline an offer the ClientUser has made')
        await self._state.http.decline_user_trade(self.id)

    async def cancel(self):
        """|coro|
        Cancels the :class:`TradeOffer`

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already cancelled or is from the ClientUser.
        """
        if self.state not in (ETradeOfferState.Active or ETradeOfferState.ConfirmationNeed):
            raise ClientException('This trade is not active')
        if self.state == ETradeOfferState.Canceled:
            raise ClientException('This trade has already been cancelled')
        if not self.is_our_offer():
            raise ClientException("Offer wasn't created by the ClientUser and therefore cannot be canceled")
        await self._state.http.cancel_user_trade(self.id)

    async def counter(self, items_to_send=None, items_to_receive=None, *, message: str = None):
        """|coro|
        Counters a trade offer from an :class:`~steam.User`.

        Parameters
        -----------
        items_to_send: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        items_to_receive: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        message: :class:`str`
             The offer message to send with the trade.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade from the ClientUser.
        """
        if self.is_our_offer():
            raise ClientException('You cannot counter an offer the ClientUser has made')
        items_to_send = [] if items_to_send is None else items_to_send
        items_to_receive = [] if items_to_receive is None else items_to_receive
        message = message if message is not None else ''
        resp = await self._state.http.send_counter_trade_offer(self.id, self.partner.id64, self.partner.id,
                                                               items_to_send, items_to_receive, message)
        if resp.get('needs_mobile_confirmation', False):
            confirmation = await self._state.confirmation_manager.get_trade_confirmation(int(resp['tradeofferid']))
            await confirmation.confirm()

    def is_one_sided(self):
        """:class:`bool`: Checks if an offer is one-sided towards the ClientUser"""
        return True if self.items_to_receive is not None and self.items_to_send else False

    def is_our_offer(self):
        """:class:`bool`: Whether the offer was created by the ClientUser."""
        return self._is_our_offer


class Inventory:
    """Represents a User's inventory.

    .. container:: operations

        .. describe:: len(x)

            Returns how many items are in the inventory.

    Attributes
    -------------
    items: List[:class:`Item`]
        A list of the inventories owner's items.
    owner: :class:`~steam.User`
        The owner of the inventory.
    game: :class:`steam.Game`
        The game the inventory the game belongs to.
    """

    __slots__ = ('game', 'items', 'owner', '_state', '_total_inventory_count')

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
        return self._total_inventory_count

    def _update(self, data):
        try:
            self.game = Game(app_id=int(data['assets'][0]['appid']), is_steam_game=True)
        except KeyError:  # they don't have an inventory for this game
            self.game = None
            self.items = []
            self._total_inventory_count = 0
            return
        else:
            for asset in data['assets']:
                for item in data['descriptions']:
                    if item['instanceid'] == asset['instanceid'] and item['classid'] == asset['classid']:
                        item.update(asset)
                        self.items.append(Item(data=item))
                self.items.append(Item(data=asset, missing=True))
            self._total_inventory_count = data['total_inventory_count']

    async def update(self):
        """|coro|
        Re-fetches the :class:`~steam.User`'s inventory.

        Returns
        ---------
        :class:`~steam.Inventory`
            The refreshed inventory.
        """
        data = await self._state.http.fetch_user_inventory(self.owner.id64, self.game.app_id, self.game.context_id)
        self._update(data)
        return self

    def filter_items(self, item_name: str, *, limit: int = None):
        """Filters items by name into a list of one type of item.

        Parameters
        ------------
        item_name: :class:`str`
            The item to filter.
        limit: Optional[:class:`int`]
            The maximum amount of items to filter.

        Returns
        ---------
        Optional[List[:class:`Item`]]
            List of :class:`Item`.
            Can be an empty list if no matching items are found.
            This also removes the item from the inventory, if possible.
        """
        items = [item for item in self.items if item.name == item_name]
        items = items[:len(items) - 1 if limit is not None else limit]
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
        Optional[:class:`Item`]
            Returns the first found item with a matching name.
            Can be ``None`` if no matching item is found.
            This also removes the item from the inventory, if possible
        """
        item = [item for item in self.items if item.name == item_name]
        if item:
            self.items.remove(item[0])
            return item[0]
        return None


class Asset:
    """A striped down version of an item.

    .. container:: operations

        .. describe:: x == y

            Checks if two assets are equal.

        .. describe:: x != y

            Checks if two assets are not equal.

    Attributes
    -------------
    game: :class:`~steam.Game`
        The game the item is from.
    asset_id: :class:`str`
        The assetid of the item.
    app_id: :class:`str`
        The appid of the item.
    amount: :class:`int`
        The amount of the same asset there are in the inventory.
    instance_id: :class:`str`
        The instanceid of the item.
    class_id: :class:`str`
        The classid of the item.
    """
    __slots__ = ('game', 'amount', 'app_id', 'class_id', 'asset_id', 'instance_id')

    def __init__(self, data):
        self.asset_id = int(data['assetid'])
        self.game = Game(app_id=data['appid'])
        self.app_id = int(data['appid'])
        self.amount = int(data['amount'])
        self.instance_id = int(data['instanceid'])
        self.class_id = int(data['classid'])

    def __repr__(self):
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in self.__slots__]
        return f"<Asset {' '.join(resolved)}>"

    def __eq__(self, other):
        return isinstance(other, Asset) and \
               False not in [getattr(self, attr) == getattr(other, attr) for attr in self.__slots__]

    def __ne__(self, other):
        return not self.__eq__(other)

    def to_dict(self):
        return {
            "assetid": str(self.id),
            "amount": self.amount,
            "appid": str(self.app_id),
            "contextid": str(self.game.context_id)
        }


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

    __slots__ = ('name', 'type', 'tags', 'colour', 'missing',
                 'icon_url', 'market_name', 'descriptions',
                 'icon_url_large', '_is_tradable', '_is_marketable') + Asset.__slots__

    def __init__(self, data, missing: bool = False):
        super().__init__(data)
        self.missing = missing
        self._from_data(data)

    def __repr__(self):
        attrs = (
                    'name',
                ) + Asset.__slots__
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Item {' '.join(resolved)}>"

    def _from_data(self, data):
        self.name = data.get('name')
        self.colour = int(data['name_color'], 16) if 'name_color' in data else None
        self.market_name = data.get('market_name')
        self.descriptions = data.get('descriptions')
        self.type = data.get('type')
        self.tags = data.get('tags')
        self.icon_url = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url"]}' \
            if 'icon_url' in data else None
        self.icon_url_large = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url_large"]}' \
            if 'icon_url_large' in data else None
        self._is_tradable = bool(data.get('tradable', False))
        self._is_marketable = bool(data.get('marketable', False))

    def is_tradable(self):
        """:class:`bool`: Whether the item is tradable."""
        return self._is_tradable

    def is_marketable(self):
        """:class:`bool`: Whether the item is marketable."""
        return self._is_marketable

    def is_asset(self):
        """:class:`bool`: Whether the item is an :class:`Asset` just wrapped in an :class:`Item`."""
        return self.name is None
