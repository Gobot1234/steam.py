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

from datetime import datetime
from typing import List, Optional, TYPE_CHECKING, Iterable

from . import utils
from .enums import ETradeOfferState
from .errors import ClientException, ConfirmationError
from .game import Game

if TYPE_CHECKING:
    from .market import PriceOverview
    from .state import ConnectionState
    from .abc import BaseUser

__all__ = (
    'Item',
    'Asset',
    'Inventory',
    'TradeOffer',
)


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

    def __init__(self, data: dict):
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
        return isinstance(other, Asset) and self.instance_id == other.instance_id and self.class_id == other.class_id

    def to_dict(self) -> dict:
        return {
            "assetid": str(self.asset_id),
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
    name: Optional[:class:`str`]
        The market_name of the item.
    display_name: Optional[:class:`str`]
        The displayed name of the item. This could be different to
        :attr:`Item.name` if the item is user re-nameable.
    colour: Optional[:class:`int`]
        The colour of the item.
    descriptions: Optional[:class:`str`]
        The descriptions of the item.
    type: Optional[:class:`str`]
        The type of the item.
    tags: Optional[:class:`str`]
        The tags of the item.
    icon_url: Optional[:class:`str`]
        The icon_url of the item. Uses the large (184x184 px) image url.
    """

    __slots__ = ('name', 'type', 'tags', 'colour', 'missing',
                 'icon_url', 'display_name', 'descriptions',
                 '_state', '_is_tradable', '_is_marketable')

    def __init__(self, state: 'ConnectionState', data: dict, missing: bool = False):
        super().__init__(data)
        self._state = state
        self.missing = missing
        self._from_data(data)

    def __repr__(self):
        attrs = ('name',) + Asset.__slots__
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Item {' '.join(resolved)}>"

    def _from_data(self, data) -> None:
        self.name = data.get('market_name')
        self.display_name = data.get('name')
        self.colour = int(data['name_color'], 16) if 'name_color' in data else None
        self.descriptions = data.get('descriptions')
        self.type = data.get('type')
        self.tags = data.get('tags')
        self.icon_url = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url_large"]}' \
            if 'icon_url_large' in data else None
        self._is_tradable = bool(data.get('tradable', False))
        self._is_marketable = bool(data.get('marketable', False))

    async def fetch_price(self) -> 'PriceOverview':
        """|coro|
        Fetches the price and volume sales of an item.

        Returns
        -------
        :class:`PriceOverview`
            The item's price overview.
        """
        return await self._state.client.fetch_price(self.name, self.game)

    def is_tradable(self) -> bool:
        """:class:`bool`: Whether the item is tradable."""
        return self._is_tradable

    def is_marketable(self) -> bool:
        """:class:`bool`: Whether the item is marketable."""
        return self._is_marketable

    def is_asset(self) -> bool:
        """:class:`bool`: Whether the item is an :class:`Asset` just wrapped in an :class:`Item`."""
        return self.missing


class Inventory:
    """Represents a User's inventory.

    .. container:: operations

        .. describe:: len(x)

            Returns how many items are in the inventory.

        .. describe:: iter(x)

            Iterates over the inventory's items.

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

    def __init__(self, state: 'ConnectionState', data: dict, owner: 'BaseUser'):
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

    def __iter__(self) -> Iterable[Item]:
        return (item for item in self.items)

    def _update(self, data) -> None:
        try:
            self.game = Game(app_id=int(data['assets'][0]['appid']))
        except KeyError:  # they don't have an inventory for this game
            self.game = None
            self.items = []
            self._total_inventory_count = 0
        else:
            for asset in data['assets']:
                found = False
                for item in data['descriptions']:
                    if item['instanceid'] == asset['instanceid'] and item['classid'] == asset['classid']:
                        item.update(asset)
                        self.items.append(Item(state=self._state, data=item))
                        found = True
                if not found:
                    self.items.append(Item(state=self._state, data=asset, missing=True))
            self._total_inventory_count = data['total_inventory_count']

    async def update(self) -> 'Inventory':
        """|coro|
        Re-fetches the :class:`~steam.User`'s inventory.

        Returns
        ---------
        :class:`~steam.Inventory`
            The refreshed inventory.
        """
        data = await self._state.http.get_user_inventory(self.owner.id64, self.game.app_id, self.game.context_id)
        self._update(data)
        return self

    def filter_items(self, item_name: str, *, limit: int = None) -> List[Item]:
        """Filters items by name into a list of one type of item.

        Parameters
        ------------
        item_name: :class:`str`
            The item's name to filter for.
        limit: Optional[:class:`int`]
            The maximum amount of items to filter.

        Returns
        ---------
        List[:class:`Item`]
            List of :class:`Item`.
            Could be an empty if no matching items are found.
            This also removes the item from the inventory, if possible.
        """
        items = [item for item in self if item.name == item_name]
        items = items if limit is None else items[:limit]
        for item in items:
            self.items.remove(item)
        return items

    def get_item(self, item_name: str) -> Optional[Item]:
        """Get an item by name from a :class:`Inventory`.

        Parameters
        ----------
        item_name: :class:`str`
            The item to get from the inventory.

        Returns
        -------
        Optional[:class:`Item`]
            Returns the first found item with a matching name.
            Can be ``None`` if no matching item is found.
            This also removes the item from the inventory, if possible.
        """
        item = utils.get(self.items, name=item_name)
        if item:
            self.items.remove(item)
        return item


class TradeOffer:
    """Represents a trade offer from/to send to a User.
    This can also be used in :meth:`steam.User.send`.

    Parameters
    ----------
        items_to_send: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        items_to_receive: Optional[List[:class:`steam.Item`]]
            The items you are sending to the other user.
        token: Optional[:class:`str`]
            The the trade token used to send trades to users who aren't
            on the ClientUser's friend's list.
        message: Optional[:class:`str`]
             The offer message to send with the trade.

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

    __slots__ = ('id', 'state', 'escrow', 'partner', 'message', 'token',
                 'expires', 'items_to_send', 'items_to_receive',
                 '_has_been_sent', '_id_other', '_state', '_is_our_offer', '__weakref__')

    def __init__(self, *, message: str = None, token: str = None,
                 items_to_send: List[Item] = None, items_to_receive: List[Item] = None):
        if isinstance(items_to_receive, Item):
            self.items_to_receive = [items_to_receive]
        elif isinstance(items_to_receive, list):
            self.items_to_receive = items_to_receive
        else:
            self.items_to_receive = []
        if isinstance(items_to_send, Item):
            self.items_to_send = [items_to_send]
        elif isinstance(items_to_send, list):
            self.items_to_send = items_to_send
        else:
            self.items_to_send = []
        self.message = message if message is not None else ''
        self.token = token
        self._has_been_sent = False

    @classmethod
    async def _from_api(cls, state: 'ConnectionState', data: dict) -> 'TradeOffer':
        self = cls(items_to_send=None, items_to_receive=None)
        self._has_been_sent = True
        self._state = state
        self._update(data)
        self.partner = await self._state.client.fetch_user(self._id_other)
        return self

    def __repr__(self):
        attrs = (
            'id', 'state', 'partner'
        )
        resolved = [f'{attr}={repr(getattr(self, attr, None))}' for attr in attrs]
        return f"<TradeOffer {' '.join(resolved)}>"

    def _update(self, data) -> None:
        self.message = data.get('message') or None
        self.id = int(data['tradeofferid'])
        self.expires = datetime.utcfromtimestamp(data['expiration_time']) if 'expiration_time' in data else None
        self.escrow = datetime.utcfromtimestamp(data['escrow_end_date']) \
            if 'escrow_end_date' in data and data['escrow_end_date'] != 0 else None
        self.state = ETradeOfferState(data.get('trade_offer_state', 1))
        self.items_to_send = [Item(state=self._state, data=item) for item in data.get('items_to_give', [])]
        self.items_to_receive = [Item(state=self._state, data=item) for item in data.get('items_to_receive', [])]
        self._is_our_offer = data.get('is_our_offer', False)
        self._id_other = data['accountid_other']

    async def confirm(self) -> None:
        """|coro|
        Confirms the :class:`TradeOffer`.
        This rarely needs to be called as the client handles most of these.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is not active.
        :exc:`~steam.ConfirmationError`
            No matching confirmation could not be found.
        """
        if self.is_gift():
            return  # no point trying to confirm it
        if self.state not in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException('This trade cannot be confirmed')
        if not await self._state.get_and_confirm_confirmation(self.id):
            raise ConfirmationError('No matching confirmation could be found for this trade')

    async def accept(self) -> None:
        """|coro|
        Accepts the :class:`TradeOffer`.

        .. note::
            This also calls :meth:`TradeOffer.confirm` (if necessary) so you don't have to.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already accepted or not from the ClientUser.
        :exc:`~steam.ConfirmationError`
            No matching confirmation could not be found.
        """
        if self.state not in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException('This trade is not active')
        if self.state == ETradeOfferState.Accepted:
            raise ClientException('This trade has already been accepted')
        if self.is_our_offer():
            raise ClientException('You cannot accept an offer the ClientUser has made')
        resp = await self._state.http.accept_user_trade(self.partner.id64, self.id)
        if resp.get('needs_mobile_confirmation', False):
            await self.confirm()

    async def decline(self) -> None:
        """|coro|
        Declines the :class:`TradeOffer`.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already declined or not from the ClientUser.
        """
        if self.state not in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException('This trade is not active')
        if self.state == ETradeOfferState.Declined:
            raise ClientException('This trade has already been declined')
        if self.is_our_offer():
            raise ClientException('You cannot decline an offer the ClientUser has made')
        await self._state.http.decline_user_trade(self.id)

    async def cancel(self) -> None:
        """|coro|
        Cancels the :class:`TradeOffer`

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already cancelled or is from the ClientUser.
        """
        if self.state not in (ETradeOfferState.Active, ETradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException('This trade is not active')
        if self.state == ETradeOfferState.Canceled:
            raise ClientException('This trade has already been cancelled')
        if not self.is_gift():
            raise ClientException("Offer wasn't created by the ClientUser and therefore cannot be canceled")
        await self._state.http.cancel_user_trade(self.id)

    async def counter(self, *, items_to_send: List[Item] = None,
                      items_to_receive: List[Item] = None,
                      token: str = None, message: str = None) -> None:
        """|coro|
        Counters a trade offer from an :class:`User`.

        Parameters
        -----------
        items_to_send: Optional[Union[List[:class:`steam.Item`], List[:class:`steam.Asset`]]
            The items you are sending to the other user.
        items_to_receive: Optional[Union[List[:class:`steam.Item`], List[:class:`steam.Asset`]]
            The items you are sending to the other user.
        token: Optional[:class:`str`]
            The the trade token used to send trades to users who aren't
            on the ClientUser's friend's list.
        message: Optional[:class:`str`]
             The offer message to send with the trade.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade from the ClientUser or it isn't active.
        """
        if not self._has_been_sent:
            raise ClientException("This trade isn't active")
        if self.is_our_offer():
            raise ClientException('You cannot counter an offer the ClientUser has made')
        if type(items_to_receive) is Item:
            items_to_receive = [items_to_receive]
        elif type(items_to_receive) is list:
            items_to_receive = items_to_receive
        else:
            items_to_receive = []
        if type(items_to_send) is Item:
            items_to_send = [items_to_send]
        elif type(items_to_send) is list:
            items_to_send = items_to_send
        else:
            items_to_send = []
        message = message if message is not None else ''
        resp = await self._state.http.send_counter_trade_offer(self.id, self.partner.id64, self.partner.id,
                                                               items_to_send, items_to_receive, token, message)
        if resp.get('needs_mobile_confirmation', False):
            await self._state.get_and_confirm_confirmation(int(resp['tradeofferid']))

    def is_gift(self) -> bool:
        """:class:`bool`: Checks if an offer is a gift to the ClientUser"""
        return True if self.items_to_receive and not self.items_to_send else False

    def is_one_sided(self) -> bool:
        """:class:`bool`: Checks if an offer is one-sided."""
        return True if not self.items_to_receive and self.items_to_send \
                       or self.items_to_receive and not self.items_to_send else False

    def is_our_offer(self) -> bool:
        """:class:`bool`: Whether the offer was created by the ClientUser."""
        return self._is_our_offer
