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

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar, Union

from typing_extensions import TypedDict

from .enums import TradeOfferState
from .errors import ClientException, ConfirmationError
from .game import Game

if TYPE_CHECKING:
    from .state import ConnectionState
    from .user import BaseUser, User


__all__ = (
    "Item",
    "Asset",
    "Inventory",
    "TradeOffer",
)

Items = Union["Item", "Asset"]
I = TypeVar("I", "Item", "Asset")


class AssetToDict(TypedDict):
    assetid: str
    amount: int
    appid: str
    contextid: str


class AssetDict(AssetToDict):
    instanceid: str
    classid: str
    missing: bool


class DescriptionDict(TypedDict, total=False):
    instanceid: str
    classid: str
    market_name: str
    currency: int
    name: str
    market_hash_name: str
    name_color: str
    background_color: str  # hex code
    type: str
    descriptions: dict[str, str]
    market_actions: list[dict[str, str]]
    tags: list[dict[str, str]]
    actions: list[dict[str, str]]
    icon_url: str
    icon_url_large: str
    tradable: bool  # 1 vs 0
    marketable: bool  # same as above
    commodity: int  # might be a bool


class ItemDict(AssetDict, DescriptionDict):
    """We combine Assets with their matching Description to form items."""


class InventoryDict(TypedDict):
    assets: list[AssetDict]
    descriptions: list[DescriptionDict]
    total_inventory_count: int
    success: int  # Result
    rwgrsn: int  # p. much always -2


class TradeOfferDict(TypedDict):
    tradeofferid: str
    tradeid: str  # no clue what this is (its not the useful one)
    accountid_other: int
    message: str
    trade_offer_state: int  # TradeOfferState
    expiration_time: int  # unix timestamps
    time_created: int
    time_updated: int
    escrow_end_date: int
    items_to_give: list[ItemDict]
    items_to_receive: list[ItemDict]
    is_our_offer: bool
    from_real_time_trade: bool
    confirmation_method: int  # 2 is mobile 1 might be email? not a clue what other values are


class Asset:
    """Base most version of an item. This class should only be received when Steam fails to find a matching item for
    its class and instance IDs.

    .. container:: operations

        .. describe:: x == y

            Checks if two assets are equal.

    Attributes
    -------------
    game: :class:`~steam.Game`
        The game the item is from.
    asset_id: :class:`str`
        The assetid of the item.
    amount: :class:`int`
        The amount of the same asset there are in the inventory.
    instance_id: :class:`str`
        The instanceid of the item.
    class_id: :class:`str`
        The classid of the item.
    """

    __slots__ = ("game", "amount", "class_id", "asset_id", "instance_id", "name")

    def __init__(self, data: AssetDict):
        self.asset_id = int(data["assetid"])
        self.game = Game(id=data["appid"])
        self.amount = int(data["amount"])
        self.instance_id = int(data["instanceid"])
        self.class_id = int(data["classid"])
        self.name = None  # so we don't raise AttributeError

    def __repr__(self) -> str:
        attrs = (
            "game",
            "amount",
            "class_id",
            "asset_id",
            "instance_id",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Asset {' '.join(resolved)}>"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Asset) and self.instance_id == other.instance_id and self.class_id == other.class_id

    def to_dict(self) -> AssetToDict:
        return {
            "assetid": str(self.asset_id),
            "amount": self.amount,
            "appid": str(self.game.id),
            "contextid": str(self.game.context_id),
        }


class Item(Asset):
    """Represents an item in an User's inventory.

    .. container:: operations

        .. describe:: x == y

            Checks if two items are equal.

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

    __slots__ = (
        "name",
        "type",
        "tags",
        "colour",
        "icon_url",
        "display_name",
        "descriptions",
        "_is_tradable",
        "_is_marketable",
    )

    def __init__(self, data: ItemDict):
        super().__init__(data)
        self._from_data(data)

    def __repr__(self) -> str:
        asset_repr = super().__repr__()[7:-1]
        attrs = ("name",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        resolved.append(asset_repr)
        return f"<Item {' '.join(resolved)}>"

    def _from_data(self, data: ItemDict) -> None:
        self.name = data.get("market_name")
        self.display_name = data.get("name")
        self.colour = int(data["name_color"], 16) if "name_color" in data else None
        self.descriptions = data.get("descriptions")
        self.type = data.get("type")
        self.tags = data.get("tags")
        self.icon_url = (
            f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url_large"]}'
            if "icon_url_large" in data
            else None
        )
        self._is_tradable = bool(data.get("tradable", False))
        self._is_marketable = bool(data.get("marketable", False))

    def is_tradable(self) -> bool:
        """:class:`bool`: Whether the item is tradable."""
        return self._is_tradable

    def is_marketable(self) -> bool:
        """:class:`bool`: Whether the item is marketable."""
        return self._is_marketable


class Inventory(Generic[I]):
    """Represents a User's inventory.

    .. container:: operations

        .. describe:: len(x)

            Returns how many items are in the inventory.

        .. describe:: iter(x)

            Iterates over the inventory's items.

        .. describe:: y in x

            Determines if an item is in the inventory based off of its :attr:`class_id` and :attr:`instance_id`.


    Attributes
    -------------
    items: list[Union[:class:`Item`, :class:`Asset`]]
        A list of the inventory's items.
    owner: :class:`~steam.User`
        The owner of the inventory.
    game: Optional[:class:`steam.Game`]
        The game the inventory the game belongs to.
    """

    __slots__ = ("game", "items", "owner", "_state", "_total_inventory_count")

    items: list[I]
    game: Optional[Game]

    def __init__(self, state: ConnectionState, data: InventoryDict, owner: BaseUser):
        self._state = state
        self.owner = owner
        self.items = []
        self._update(data)

    def __repr__(self) -> str:
        attrs = ("owner", "game")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __len__(self) -> int:
        return self._total_inventory_count

    def __iter__(self) -> Iterator[I]:
        return iter(self.items)

    def __contains__(self, item: Asset) -> bool:
        if not isinstance(item, Asset):
            raise TypeError(
                f"unsupported operand type(s) for 'in': {item.__class__.__qualname__!r} and {self.__class__.__name__!r}"
            )
        return item in self.items

    def _update(self, data: InventoryDict) -> None:
        try:
            self.game = Game(id=int(data["assets"][0]["appid"]))
        except KeyError:  # they don't have an inventory in this game
            self.game = None
            self.items = []
            self._total_inventory_count = 0
        else:
            for asset in data["assets"]:
                for item in data["descriptions"]:
                    if item["instanceid"] == asset["instanceid"] and item["classid"] == asset["classid"]:
                        item.update(asset)
                        self.items.append(Item(data=item))
                        break
                else:
                    self.items.append(Asset(data=asset))
            self._total_inventory_count = data["total_inventory_count"]

    async def update(self) -> None:
        """|coro|
        Re-fetches the inventory.
        """
        data = await self._state.http.get_user_inventory(self.owner.id64, self.game.id, self.game.context_id)
        self._update(data)

    def filter_items(self, *names: str, limit: Optional[int] = None) -> list[I]:
        """A helper function that filters items by name from the inventory.

        Parameters
        ------------
        *names: :class:`str`
            The names of the items to filter for.
        limit: Optional[:class:`int`]
            The maximum amount of items to return. Checks from the front of the items.

        Raises
        -------
        :exc:`ValueError`
            You passed a limit and multiple item names.

        Returns
        ---------
        list[:class:`Item`]
            The matching items.
        """
        if len(names) > 1 and limit:
            raise ValueError("Cannot pass a limit with multiple items")
        items = [item for item in self if item.name in names]
        return items if limit is None else items[:limit]

    def get_item(self, name: str) -> Optional[I]:
        """A helper function that gets an item by name from the inventory.

        Parameters
        ----------
        name: :class:`str`
            The item to get from the inventory.

        Returns
        -------
        Optional[:class:`Item`]
            Returns the first item found with a matching name. Could be ``None`` if no matching item is found.
        """
        item = self.filter_items(name, limit=1)
        return item[0] if item else None


class TradeOffer:
    """Represents a trade offer from/to send to a User.
    This can also be used in :meth:`steam.User.send`.

    Parameters
    ----------
    item_to_send: Optional[:class:`steam.Item`]
        The item to send with the trade offer.
    item_to_receive: Optional[:class:`steam.Item`]
        The item to receive with the trade offer.
    items_to_send: Optional[list[:class:`steam.Item`]]
        The items you are sending to the other user.
    items_to_receive: Optional[list[:class:`steam.Item`]]
        The items you are sending to the other user.
    token: Optional[:class:`str`]
        The the trade token used to send trades to users who aren't on the ClientUser's friend's list.
    message: Optional[:class:`str`]
         The offer message to send with the trade.

    Attributes
    ----------
    partner: Union[:class:`~steam.User`, :class:`~steam.SteamID`]
        The trade offer partner. This should only ever be a :class:`~steam.SteamID` if the partner's profile is private.
    items_to_send: Union[list[:class:`Item`]]
        A list of items to send to the partner.
    items_to_receive: Union[list[:class:`Item`]]
        A list of items to receive from the partner.
    state: :class:`~steam.TradeOfferState`
        The offer state of the trade for the possible types see :class:`~steam.ETradeOfferState`.
    message: :class:`str`
        The message included with the trade offer.
    id: :class:`int`
        The trade's offer ID.
    expires: :class:`datetime.datetime`
        The time at which the trade automatically expires.
    escrow: Optional[:class:`datetime.timedelta`]
        The time at which the escrow will end. Can be ``None`` if there is no escrow on the trade.

        Warning
        -------
        This isn't likely to be accurate, use :meth:`User.escrow` instead if possible.
    """

    __slots__ = (
        "id",
        "state",
        "escrow",
        "partner",
        "message",
        "token",
        "expires",
        "items_to_send",
        "items_to_receive",
        "_has_been_sent",
        "_state",
        "_is_our_offer",
    )

    def __init__(
        self,
        *,
        message: Optional[str] = None,
        token: Optional[str] = None,
        item_to_send: Optional[Items] = None,
        item_to_receive: Optional[Items] = None,
        items_to_send: Optional[list[Items]] = None,
        items_to_receive: Optional[list[Items]] = None,
    ):
        self.items_to_receive: list[Items] = items_to_receive or []
        self.items_to_send: list[Items] = items_to_send or []
        if item_to_receive:
            self.items_to_receive.append(item_to_receive)
        if item_to_send:
            self.items_to_send.append(item_to_send)
        self.message: str = message if message is not None else ""
        self.token: Optional[str] = token
        self._has_been_sent = False
        self.partner: Optional[User] = None
        self.state = TradeOfferState.Invalid

    @classmethod
    async def _from_api(cls, state: ConnectionState, data: TradeOfferDict) -> TradeOffer:
        trade = cls()
        trade._has_been_sent = True
        trade._state = state
        trade._update(data)
        trade.partner = int(data["accountid_other"])
        return trade

    def __repr__(self) -> str:
        attrs = ("id", "state", "partner")
        resolved = [f"{attr}={getattr(self, attr, None)!r}" for attr in attrs]
        return f"<TradeOffer {' '.join(resolved)}>"

    def _update(self, data: TradeOfferDict) -> None:
        self.message = data.get("message") or None
        self.id = int(data["tradeofferid"])
        expires = data.get("expiration_time")
        escrow = data.get("escrow_end_date")
        self.expires = datetime.utcfromtimestamp(expires) if expires else None
        self.escrow = datetime.utcfromtimestamp(escrow) - datetime.utcnow() if escrow else None
        self.state = TradeOfferState(data.get("trade_offer_state", 1))
        self.items_to_send = [Item(data=item) for item in data.get("items_to_give", [])]
        self.items_to_receive = [Item(data=item) for item in data.get("items_to_receive", [])]
        self._is_our_offer = data.get("is_our_offer", False)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, TradeOffer) and self._has_been_sent and other._has_been_sent and self.id == other.id

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
        self._check_active()
        if self.is_gift():
            return  # no point trying to confirm it
        if not await self._state.get_and_confirm_confirmation(self.id):
            raise ConfirmationError("No matching confirmation could be found for this trade")
        del self._state._confirmations[self.id]

    async def accept(self) -> None:
        """|coro|
        Accepts the :class:`TradeOffer`.

        Note
        ----
        This also calls :meth:`confirm` (if necessary) so you don't have to.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already accepted or not from the ClientUser.
        :exc:`~steam.ConfirmationError`
            No matching confirmation could not be found.
        """
        if self.state == TradeOfferState.Accepted:
            raise ClientException("This trade has already been accepted")
        if self.is_our_offer():
            raise ClientException("You cannot accept an offer the ClientUser has made")
        self._check_active()
        resp = await self._state.http.accept_user_trade(self.partner.id64, self.id)
        if resp.get("needs_mobile_confirmation", False):
            for tries in range(5):
                try:
                    await self.confirm()
                except ConfirmationError:
                    break
                except ClientException:
                    await asyncio.sleep(tries * 2)

    async def decline(self) -> None:
        """|coro|
        Declines the :class:`TradeOffer`.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active, already declined or not from the ClientUser.
        """
        if self.state == TradeOfferState.Declined:
            raise ClientException("This trade has already been declined")
        if self.is_our_offer():
            raise ClientException("You cannot decline an offer the ClientUser has made")
        self._check_active()
        await self._state.http.decline_user_trade(self.id)

    async def cancel(self) -> None:
        """|coro|
        Cancels the :class:`TradeOffer`

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade is either not active or already cancelled.
        """
        if self.state == TradeOfferState.Canceled:
            raise ClientException("This trade has already been cancelled")
        self._check_active()
        await self._state.http.cancel_user_trade(self.id)

    async def counter(self, trade: TradeOffer) -> None:
        """|coro|
        Counters a trade offer from an :class:`User`.

        Parameters
        -----------
        trade: :class:`TradeOffer`
            The trade offer to counter with.

        Raises
        ------
        :exc:`~steam.ClientException`
            The trade from the ClientUser or it isn't active.
        """
        self._check_active()
        if self.is_our_offer():
            raise ClientException("You cannot counter an offer the ClientUser has made")

        to_send = [item.to_dict() for item in trade.items_to_send]
        to_receive = [item.to_dict() for item in trade.items_to_receive]
        resp = await self._state.http.send_trade_offer(
            self.partner, to_send, to_receive, trade.token, trade.message, trade_id=self.id
        )
        if resp.get("needs_mobile_confirmation", False):
            await self._state.get_and_confirm_confirmation(int(resp["tradeofferid"]))

    def is_gift(self) -> bool:
        """:class:`bool`: Helper method that checks if an offer is a gift to the :class:`~steam.ClientUser`"""
        return self.items_to_receive and not self.items_to_send

    def is_our_offer(self) -> bool:
        """:class:`bool`: Whether the offer was created by the :class:`~steam.ClientUser`."""
        return self._is_our_offer

    def _check_active(self) -> None:
        if self.state not in (TradeOfferState.Active, TradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException("This trade is not active")
