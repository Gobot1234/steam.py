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
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from typing_extensions import TypeAlias, TypedDict

from .enums import TradeOfferState
from .errors import ClientException, ConfirmationError
from .game import Game, StatefulGame

if TYPE_CHECKING:
    from typing_extensions import Required

    from .abc import BaseUser, SteamID
    from .state import ConnectionState
    from .user import User


__all__ = (
    "Item",
    "Asset",
    "Inventory",
    "TradeOffer",
)

Items: TypeAlias = "Item | Asset"
I = TypeVar("I", bound="Item")


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
    instanceid: Required[str]
    classid: Required[str]
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
    fraudwarnings: list[str]


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
    game
        The game the item is from.
    asset_id
        The assetid of the item.
    amount
        The amount of the same asset there are in the inventory.
    instance_id
        The instanceid of the item.
    class_id
        The classid of the item.
    """

    __slots__ = ("game", "amount", "class_id", "asset_id", "instance_id")
    REPR_ATTRS = __slots__

    def __init__(self, data: AssetDict):
        self.asset_id = int(data["assetid"])
        self.game = Game(id=data["appid"])
        self.amount = int(data["amount"])
        self.instance_id = int(data["instanceid"])
        self.class_id = int(data["classid"])

    def __repr__(self) -> str:
        cls = self.__class__
        resolved = [f"{attr}={getattr(self, attr, None)!r}" for attr in cls.REPR_ATTRS]
        return f"<{cls.__name__} {' '.join(resolved)}>"

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
    name
        The market_name of the item.
    display_name
        The displayed name of the item. This could be different to :attr:`Item.name` if the item is user re-nameable.
    colour
        The colour of the item.
    descriptions
        The descriptions of the item.
    type
        The type of the item.
    tags
        The tags of the item.
    icon_url
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
        "fraud_warnings",
        "_is_tradable",
        "_is_marketable",
    )
    REPR_ATTRS = ("name", *Asset.REPR_ATTRS)

    def __init__(self, data: ItemDict):
        super().__init__(data)
        self._from_data(data)

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
        self.fraud_warnings = data.get("fraudwarnings", [])
        self._is_tradable = bool(data.get("tradable", False))
        self._is_marketable = bool(data.get("marketable", False))

    def is_tradable(self) -> bool:
        """Whether the item is tradable."""
        return self._is_tradable

    def is_marketable(self) -> bool:
        """Whether the item is marketable."""
        return self._is_marketable


class BaseInventory(Generic[I]):
    """Base for all inventories."""

    __slots__ = ("game", "items", "owner", "_state")

    def __init__(self, state: ConnectionState, data: InventoryDict, owner: BaseUser, game: Game):
        self._state = state
        self.owner = owner
        self.game = StatefulGame(state, id=game.id, name=game.name)
        self._update(data)

    def __repr__(self) -> str:
        attrs = ("owner", "game")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator[I]:
        return iter(self.items)

    def __contains__(self, item: Asset) -> bool:
        if not isinstance(item, Asset):
            raise TypeError(
                f"unsupported operand type(s) for 'in': {item.__class__.__qualname__!r} and {self.__class__.__name__!r}"
            )
        return item in self.items

    def _update(self, data: InventoryDict) -> None:
        self.items: Sequence[I] = []
        for asset in data.get("assets", ()):
            for item in data["descriptions"]:
                if item["instanceid"] == asset["instanceid"] and item["classid"] == asset["classid"]:
                    item.update(asset)
                    self.items.append(Item(data=item))  # type: ignore
                    break
            else:
                self.items.append(Asset(data=asset))  # type: ignore

    async def update(self) -> None:
        """Re-fetches the inventory."""
        if not self.game:
            return
        data = await self._state.http.get_user_inventory(self.owner.id64, self.game.id, self.game.context_id)
        self._update(data)

    def filter_items(self, *names: str, limit: int | None = None) -> list[I]:
        """A helper function that filters items by name from the inventory.

        Parameters
        ------------
        names
            The names of the items to filter for.
        limit
            The maximum amount of items to return. Checks from the front of the items.

        Raises
        -------
        :exc:`ValueError`
            You passed a limit and multiple item names.

        Returns
        ---------
        The matching items.
        """
        if len(names) > 1 and limit:
            raise ValueError("Cannot pass a limit with multiple items")
        items = [item for item in self if item.name in names]
        return items if limit is None else items[:limit]

    def get_item(self, name: str) -> I | None:
        """A helper function that gets an item or ``None`` if no matching item is found by name from the inventory.

        Parameters
        ----------
        name
            The item to get from the inventory.
        """
        item = self.filter_items(name, limit=1)
        return item[0] if item else None


class Inventory(BaseInventory[Item]):
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
    items
        A list of the inventory's items.
    owner
        The owner of the inventory.
    game
        The game the inventory the game belongs to.
    """

    __slots__ = ()


class TradeOffer:
    """Represents a trade offer from/to send to a User.
    This can also be used in :meth:`steam.User.send`.

    Parameters
    ----------
    item_to_send
        The item to send with the trade offer.
    item_to_receive
        The item to receive with the trade offer.
    items_to_send
        The items you are sending to the other user.
    items_to_receive
        The items you are receiving from the other user.
    token
        The the trade token used to send trades to users who aren't on the ClientUser's friend's list.
    message
         The offer message to send with the trade.

    Attributes
    ----------
    partner
        The trade offer partner. This should only ever be a :class:`~steam.SteamID` if the partner's profile is private.
    items_to_send
        A list of items to send to the partner.
    items_to_receive
        A list of items to receive from the partner.
    state
        The offer state of the trade for the possible types see :class:`~steam.TradeOfferState`.
    message
        The message included with the trade offer.
    id
        The trade's offer ID.
    created_at
        The time at which the trade was created.
    updated_at
        The time at which the trade was last updated.
    expires
        The time at which the trade automatically expires.
    escrow
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
        "updated_at",
        "created_at",
        "items_to_send",
        "items_to_receive",
        "_has_been_sent",
        "_state",
        "_is_our_offer",
    )

    def __init__(
        self,
        *,
        message: str | None = None,
        token: str | None = None,
        item_to_send: Items | None = None,
        item_to_receive: Items | None = None,
        items_to_send: list[Items] | None = None,
        items_to_receive: list[Items] | None = None,
    ):
        self.items_to_receive: list[Items] = items_to_receive or []
        self.items_to_send: list[Items] = items_to_send or []
        if item_to_receive:
            self.items_to_receive.append(item_to_receive)
        if item_to_send:
            self.items_to_send.append(item_to_send)
        self.message: str | None = message or None
        self.token: str | None = token
        self._has_been_sent = False
        self.partner: User | SteamID | None = None
        self.updated_at: datetime | None = None
        self.created_at: datetime | None = None
        self.escrow: timedelta | None = None
        self.state = TradeOfferState.Invalid

    @classmethod
    def _from_api(cls, state: ConnectionState, data: TradeOfferDict) -> TradeOffer:
        trade = cls()
        trade._has_been_sent = True
        trade._state = state
        trade._update(data)
        trade.partner = int(data["accountid_other"])  # type: ignore
        return trade

    def _update_from_send(
        self, state: ConnectionState, data: dict[str, Any], partner: User, active: bool = True
    ) -> None:
        self.id = int(data["tradeofferid"])
        self._state = state
        self.partner = partner
        self.state = TradeOfferState.Active if active else TradeOfferState.ConfirmationNeed
        self.created_at = datetime.utcnow()
        self._is_our_offer = True

    def __repr__(self) -> str:
        attrs = ("id", "state", "partner")
        resolved = [f"{attr}={getattr(self, attr, None)!r}" for attr in attrs]
        return f"<TradeOffer {' '.join(resolved)}>"

    def _update(self, data: TradeOfferDict) -> None:
        self.message = data.get("message") or None
        self.id = int(data["tradeofferid"])
        expires = data.get("expiration_time")
        escrow = data.get("escrow_end_date")
        updated_at = data.get("time_updated")
        created_at = data.get("time_created")
        self.expires = datetime.utcfromtimestamp(expires) if expires else None
        self.escrow = datetime.utcfromtimestamp(escrow) - datetime.utcnow() if escrow else None
        self.updated_at = datetime.utcfromtimestamp(updated_at) if updated_at else None
        self.created_at = datetime.utcfromtimestamp(created_at) if created_at else None
        self.state = TradeOfferState.try_value(data.get("trade_offer_state", 1))
        self.items_to_send = [Item(data=item) for item in data.get("items_to_give", [])]
        self.items_to_receive = [Item(data=item) for item in data.get("items_to_receive", [])]
        self._is_our_offer = data.get("is_our_offer", False)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, TradeOffer) and self._has_been_sent and other._has_been_sent and self.id == other.id

    async def confirm(self) -> None:
        """Confirms the trade offer.
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
        if not await self._state.fetch_and_confirm_confirmation(self.id):
            raise ConfirmationError("No matching confirmation could be found for this trade")
        del self._state._confirmations[self.id]

    async def accept(self) -> None:
        """Accepts the trade offer.

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
        """Declines the trade offer.

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
        """Cancels the trade offer.

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
        """Counter a trade offer from an :class:`User`.

        Parameters
        -----------
        trade
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
            self.partner, to_send, to_receive, trade.token, trade.message or "", trade_id=self.id
        )
        if resp.get("needs_mobile_confirmation", False):
            await self._state.fetch_and_confirm_confirmation(int(resp["tradeofferid"]))

    def is_gift(self) -> bool:
        """Helper method that checks if an offer is a gift to the :class:`~steam.ClientUser`"""
        return bool(self.items_to_receive and not self.items_to_send)

    def is_our_offer(self) -> bool:
        """Whether the offer was created by the :class:`~steam.ClientUser`."""
        return self._is_our_offer

    def _check_active(self) -> None:
        if self.state not in (TradeOfferState.Active, TradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException("This trade is not active")
