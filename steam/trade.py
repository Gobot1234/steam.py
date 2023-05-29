"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import types
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Generic, cast, overload

from typing_extensions import NamedTuple, TypeVar

from . import utils
from ._const import URL
from .app import App, PartialApp
from .enums import Language, TradeOfferState
from .errors import ClientException, ConfirmationError
from .models import CDNAsset
from .protobufs import econ
from .types.id import AppID, AssetID, ClassID, ContextID, InstanceID, TradeOfferID
from .utils import DateTime

if TYPE_CHECKING:
    from .abc import BaseUser, PartialUser
    from .friend import Friend
    from .state import ConnectionState
    from .types import trade
    from .user import ClientUser


__all__ = (
    "Asset",
    "Item",
    "Inventory",
    "TradeOffer",
    "MovedItem",
    "TradeOfferReceipt",
)


OwnerT = TypeVar("OwnerT", bound="PartialUser", default="BaseUser", covariant=True)


class Asset(Generic[OwnerT]):
    """Base most version of an item. This class should only be received when Steam fails to find a matching item for
    its class and instance IDs.

    .. container:: operations

        .. describe:: x == y

            Checks if two assets are equal.

        .. describe:: hash(x)

            Returns the hash of an asset.
    """

    __slots__ = (
        "id",
        "amount",
        "class_id",
        "instance_id",
        # "post_rollback_id",
        "owner",
        "_app_cs",
        "_app_id",
        "_context_id",
        "_state",
    )
    REPR_ATTRS = ("id", "class_id", "instance_id", "amount", "owner", "app")  # "post_rollback_id"

    def __init__(self, state: ConnectionState, asset: econ.Asset, owner: OwnerT):
        self.id = AssetID(asset.assetid)
        """The assetid of the item."""
        self.amount = asset.amount
        """The amount of the same asset there are in the inventory."""
        self.instance_id = InstanceID(asset.instanceid)
        """The instanceid of the item."""
        self.class_id = ClassID(asset.classid)
        """The classid of the item."""
        # self.post_rollback_id = int(data["rollback_new_assetid"]) if "rollback_new_assetid" in data else None
        """The assetid of the item after a rollback (cancelled, etc.). ``None`` if not rolled back."""
        self.owner = owner
        """The owner of the asset."""
        self._app_id = AppID(asset.appid)
        self._context_id = ContextID(asset.contextid)
        self._state = state

    def __repr__(self) -> str:
        cls = self.__class__
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in cls.REPR_ATTRS]
        return f"<{cls.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: Any) -> bool:
        return (
            self.id == other.id and self._app_id == other._app_id and self._context_id == other._context_id
            if isinstance(other, Asset)
            else NotImplemented
        )

    def __hash__(self) -> int:
        return hash((self.id, self._app_id, self._context_id))

    def to_dict(self) -> trade.AssetToDict:
        return {
            "assetid": str(self.id),
            "amount": self.amount,
            "appid": str(self._app_id),
            "contextid": str(self._context_id),
        }

    def to_proto(self) -> econ.Asset:
        return econ.Asset(
            assetid=self.id,
            amount=self.amount,
            instanceid=self.instance_id,
            classid=self.class_id,
            appid=self._app_id,
            contextid=self._context_id,
        )

    @utils.cached_slot_property
    def app(self) -> PartialApp:
        """The app the item is from."""
        return PartialApp(self._state, id=self._app_id, context_id=self._context_id)

    @property
    def url(self) -> str:
        """The URL for the asset in the owner's inventory.

        e.g. https://steamcommunity.com/profiles/76561198248053954/inventory/#440_2_8526584188
        """
        return f"{self.owner.community_url}/inventory#{self._app_id}_{self._context_id}_{self.id}"

    async def gift_to(
        self: Asset[ClientUser],
        recipient: Friend,
        *,
        name: str | None = None,
        message: str,
        closing_note: str,
        signature: str,
    ) -> None:
        """Gifts the asset to the recipient.

        Parameters
        ------------
        recipient
            The recipient to gift the asset to.
        name
            The name to give the asset. If not provided, the recipient's :attr:`name` will be used.
        message
            The message to send with the gift.
        closing_note
            The closing note to send with the gift.
        signature
            The signature to send with the gift.
        """
        await self._state.http.send_user_gift(
            recipient.id,
            self.id,
            name=name if name is not None else recipient.name,
            message=message,
            closing_note=closing_note,
            signature=signature,
        )


class Item(Asset[OwnerT]):
    """Represents an item in a User's inventory."""

    __slots__ = (
        "name",
        "type",
        "tags",
        "colour",
        "icon",
        "display_name",
        "descriptions",
        "owner_descriptions",
        "fraud_warnings",
        "actions",
        "owner_actions",
        "market_actions",
        "_is_tradable",
        "_is_marketable",
    )
    REPR_ATTRS = ("name", *Asset.REPR_ATTRS)

    def __init__(self, state: ConnectionState, asset: econ.Asset, description: econ.ItemDescription, owner: OwnerT):
        super().__init__(state, asset, owner)

        self.name = description.market_name
        """The market_name of the item."""
        self.display_name = description.name or self.name
        """The displayed name of the item. This could be different to :attr:`Item.name` if the item is user re-nameable."""
        self.colour = int(description.name_color, 16) if description.name_color else None
        """The colour of the item."""
        self.descriptions = description.descriptions
        """The descriptions of the item."""
        self.owner_descriptions = description.owner_descriptions
        """The descriptions of the item which are visible only to the owner of the item."""
        self.type = description.type
        """The type of the item."""
        self.tags = description.tags
        """The tags of the item."""
        icon_url = description.icon_url_large or description.icon_url
        self.icon = (
            CDNAsset(state, f"https://community.cloudflare.steamstatic.com/economy/image/{icon_url}")
            if icon_url
            else None
        )
        """The icon url of the item. Uses the large image url where possible."""
        self.fraud_warnings = description.fraudwarnings
        """The fraud warnings for the item."""
        self.actions = description.actions
        """The actions for the item."""
        self.owner_actions = description.owner_actions
        """The owner actions for the item."""
        self.market_actions = description.market_actions
        """The market actions for the item."""
        self._is_tradable = description.tradable
        self._is_marketable = description.marketable

    def is_tradable(self) -> bool:
        """Whether the item is tradable."""
        return self._is_tradable

    def is_marketable(self) -> bool:
        """Whether the item is marketable."""
        return self._is_marketable


class InventoryGenericAlias(types.GenericAlias):
    if TYPE_CHECKING:

        @property
        def __origin__(self) -> type[Inventory]:
            ...

    def __call__(self, *args: Any, **kwargs: Any) -> object:
        # this is done cause we need __orig_class__ in __init__
        result = self.__origin__.__new__(self.__origin__, *args, **kwargs)
        result.__orig_class__ = self
        result.__init__(*args, **kwargs)
        return result

    def __mro_entries__(self, bases: tuple[type, ...]) -> tuple[type]:
        # if we are subclassing we should return a new class that already has __orig_class__

        class BaseInventory(*super().__mro_entries__(bases)):  # type: ignore
            __slots__ = ()
            __orig_class__ = self

        return (BaseInventory,)


ItemT = TypeVar("ItemT", bound=Item["PartialUser"], default=Item["BaseUser"], covariant=True)


class Inventory(Generic[ItemT, OwnerT], Sequence[ItemT]):
    """Represents a User's inventory.

    .. container:: operations

        .. describe:: len(x)

            Returns how many items are in the inventory.

        .. describe:: iter(x)

            Iterates over the inventory's items.

        .. describe:: x[i]

            Returns the item at the given index.

        .. describe:: y in x

            Determines if an item is in the inventory based off of its :attr:`Asset.id`.
    """

    __slots__ = (
        "app",
        "items",
        "owner",
        "_language",
        "_state",
        "__orig_class__",  # undocumented typing internals more shim to make extensions work
    )
    __orig_class__: InventoryGenericAlias
    __orig_bases__: tuple[types.GenericAlias, ...]  # "duck typing"

    def __init__(
        self,
        state: ConnectionState,
        data: econ.GetInventoryItemsWithDescriptionsResponse,
        owner: OwnerT,
        app: App,
        language: Language | None,
    ):
        self._state = state
        self.owner = owner
        """The owner of the inventory."""
        self.app = PartialApp(state, id=app.id, name=app.name, context_id=app.context_id)
        """The app the inventory belongs to."""
        self._language = language
        self._update(data)

    def __repr__(self) -> str:
        attrs = ("owner", "app")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{getattr(self, '__orig_class__', self.__class__.__name__)} {' '.join(resolved)}>"

    def __len__(self) -> int:
        return len(self.items)

    @overload
    def __getitem__(self, idx: int) -> ItemT:
        ...

    @overload
    def __getitem__(self, idx: slice) -> Sequence[ItemT]:
        ...

    def __getitem__(self, idx: int | slice) -> ItemT | Sequence[ItemT]:
        return self.items[idx]

    def __iter__(self) -> Iterator[ItemT]:
        return iter(self.items)

    def __contains__(self, item: Asset) -> bool:
        if not isinstance(item, Asset):
            raise TypeError(
                f"unsupported operand type(s) for 'in': {item.__class__.__qualname__!r} and {self.__orig_class__!r}"
            )
        return item in self.items

    if not TYPE_CHECKING:
        __class_getitem__ = classmethod(InventoryGenericAlias)

    def _update(self, data: econ.GetInventoryItemsWithDescriptionsResponse) -> None:
        items: list[ItemT] = []
        ItemClass: type[ItemT]
        try:  # ideally one day this will just be ItemT.__value__ or something
            (ItemClass,) = self.__orig_class__.__args__
        except AttributeError:
            ItemClass = self.__orig_bases__[0].__args__[0].__default__
        for asset in data.assets:
            description = utils.get(data.descriptions, instanceid=asset.instanceid, classid=asset.classid)
            if description is None:
                raise RuntimeError(f"Associated description for {asset} not found")
            items.append(ItemClass(self._state, asset=asset, description=description, owner=self.owner))
        self.items: Sequence[ItemT] = items
        """A list of the inventory's items."""

    async def update(self) -> None:
        """Re-fetches the inventory and updates it inplace."""
        async with (
            self._state.user._inventory_locks.setdefault(self.app.id, asyncio.Lock())
            if self.owner == self._state.user
            else contextlib.nullcontext()
        ):
            data = await self._state.fetch_user_inventory(
                self.owner.id64, self.app.id, self.app.context_id, self._language
            )
        self._update(data)


class TradeOfferReceipt(NamedTuple, Generic[OwnerT]):
    sent: list[MovedItem[ClientUser]]
    received: list[MovedItem[OwnerT]]


class MovedItem(Item[OwnerT]):
    """Represents an item that has moved from one inventory to another."""

    __slots__ = (
        "new_id",
        "new_context_id",
    )
    REPR_ATTRS = (*Item.REPR_ATTRS, "new_id", "new_context_id")

    def __init__(self, state: ConnectionState, data: trade.TradeOfferReceiptItem, owner: OwnerT):
        super().__init__(
            state,
            asset=econ.Asset().from_dict(data),  # type: ignore  # TODO waiting on https://github.com/danielgtaylor/python-betterproto/issues/432
            description=econ.ItemDescription().from_dict(data),  # type: ignore
            owner=owner,
        )
        self.new_id = int(data["new_assetid"])
        """The new_assetid field, this is the asset ID of the item in the partners inventory."""
        self.new_context_id = int(data["new_contextid"])
        """The new_contextid field."""


ReceivingAssetT = TypeVar("ReceivingAssetT", bound="Asset[PartialUser]", default="Item[BaseUser]", covariant=True)
SendingAssetT = TypeVar("SendingAssetT", bound="Asset[ClientUser]", default="Item[ClientUser]", covariant=True)


class TradeOffer(Generic[ReceivingAssetT, SendingAssetT, OwnerT]):
    """Represents a trade offer from/to send to a User.
    This can also be used in :meth:`steam.User.send`.

    Parameters
    ----------
    sending
        The items you are sending to the other user.
    receiving
        The items you are receiving from the other user.
    token
        The trade token used to send trades to users who aren't on the ClientUser's friend's list.
    message
         The offer message to send with the trade.
    """

    __slots__ = (
        "id",
        "_id",
        "state",
        "escrow",
        "partner",
        "message",
        "token",
        "expires",
        "updated_at",
        "created_at",
        "sending",
        "receiving",
        "_has_been_sent",
        "_state",
        "_is_our_offer",
    )

    id: TradeOfferID
    """The trade offer's ID."""
    partner: OwnerT
    """The trade offer partner."""

    def __init__(
        self,
        *,
        message: str | None = None,
        token: str | None = None,
        sending: Sequence[SendingAssetT] | SendingAssetT | None = None,
        # TODO HKT for this would be really nice as could then "ensure" we own the item
        receiving: Sequence[ReceivingAssetT] | ReceivingAssetT | None = None,
    ):
        self.sending: Sequence[SendingAssetT] = (
            sending if isinstance(sending, Sequence) else [sending] if sending else []
        )
        """The items you are sending to the partner."""
        self.receiving: Sequence[ReceivingAssetT] = (
            receiving if isinstance(receiving, Sequence) else [receiving] if receiving else []
        )
        """The items you are receiving from the partner."""
        self.message: str | None = message or None
        """The message included with the trade offer."""
        self.token: str | None = token
        """The trade token used to send trades to users who aren't on the ClientUser's friend's list."""
        self.updated_at: datetime | None = None
        """The time at which the trade was last updated."""
        self.created_at: datetime | None = None
        """The time at which the trade was created."""
        self.escrow: timedelta | None = None
        """
        The time at which the escrow will end. Can be ``None`` if there is no escrow on the trade.

        Warning
        -------
        This isn't likely to be accurate, use :meth:`User.escrow` instead if possible.
        """
        self.state = TradeOfferState.Invalid
        """The offer state of the trade for the possible types see :class:`~steam.TradeOfferState`."""
        self._id: int | None = None
        self._has_been_sent = False

    @classmethod
    def _from_api(cls, state: ConnectionState, data: trade.TradeOffer, partner: OwnerT) -> TradeOffer[Item[OwnerT], Item[ClientUser], OwnerT]:  # type: ignore
        trade = cls()
        trade._has_been_sent = True
        trade._state = state
        trade.partner = partner
        return cast("TradeOffer[Item[OwnerT], Item[ClientUser], OwnerT]", trade._update(data))

    @classmethod
    def _from_history(
        cls: type[TradeOffer[MovedItem[OwnerT], MovedItem[ClientUser], OwnerT]],
        state: ConnectionState,
        data: trade.TradeOfferHistoryTrade,
        descriptions: Sequence[trade.Description],
    ) -> TradeOffer[MovedItem[OwnerT], MovedItem[ClientUser], OwnerT]:
        from .abc import PartialUser

        partner = cast("OwnerT", PartialUser(state, data["steamid_other"]))
        trade = cls(
            receiving=[
                MovedItem(state, description | asset, partner)
                for asset, description in itertools.product(data.get("assets_received", ()), descriptions)
                if description["instanceid"] == asset["instanceid"] and description["classid"] == asset["classid"]
            ],
            sending=[
                MovedItem(state, description | asset, state.user)
                for asset, description in itertools.product(data.get("assets_given", ()), descriptions)
                if description["instanceid"] == asset["instanceid"] and description["classid"] == asset["classid"]
            ],
        )
        trade._state = state
        trade._id = int(data["tradeid"])
        trade.partner = partner
        trade.created_at = DateTime.from_timestamp(data["time_init"])
        trade.state = TradeOfferState.try_value(data["status"])

        return trade

    def _update_from_send(
        self, state: ConnectionState, data: trade.TradeOfferCreateResponse, partner: OwnerT, active: bool = True  # type: ignore
    ) -> None:
        self.id = TradeOfferID(int(data["tradeofferid"]))
        self._state = state
        self.partner = partner
        self.state = TradeOfferState.Active if active else TradeOfferState.ConfirmationNeed
        self.created_at = DateTime.now()
        self._is_our_offer = True

    def __repr__(self) -> str:
        attrs = ("id", "state", "partner")
        resolved = [f"{attr}={getattr(self, attr, None)!r}" for attr in attrs]
        return f"<TradeOffer {' '.join(resolved)}>"

    def _update(
        self: TradeOffer[Asset[OwnerT], Asset[ClientUser], OwnerT], data: trade.TradeOffer
    ) -> TradeOffer[Item[OwnerT], Item[ClientUser], OwnerT]:
        self.message = data.get("message") or None
        self.id = TradeOfferID(int(data["tradeofferid"]))
        self._id = int(data["tradeid"]) if "tradeid" in data else None
        expires = data.get("expiration_time")
        escrow = data.get("escrow_end_date")
        updated_at = data.get("time_updated")
        created_at = data.get("time_created")
        self.expires = DateTime.from_timestamp(expires) if expires else None
        self.escrow = DateTime.from_timestamp(escrow) - DateTime.now() if escrow else None
        self.updated_at = DateTime.from_timestamp(updated_at) if updated_at else None
        self.created_at = DateTime.from_timestamp(created_at) if created_at else None
        self.state = TradeOfferState.try_value(data.get("trade_offer_state", 1))
        if (
            self.state != TradeOfferState.Accepted
        ):  # steam doesn't really send the item data if the offer just got accepted
            # TODO update this to actually check if the items are different (they shouldn't be)
            self.sending = [
                Item(
                    self._state,
                    asset=econ.Asset().from_dict(item),
                    description=econ.ItemDescription().from_dict(item),
                    owner=self._state.user,
                )
                for item in data.get("items_to_give", ())
            ]
            self.receiving = [
                Item(
                    self._state,
                    asset=econ.Asset().from_dict(item),
                    description=econ.ItemDescription().from_dict(item),
                    owner=self.partner,
                )
                for item in data.get("items_to_receive", ())
            ]
        self._is_our_offer = data.get("is_our_offer", False)
        return cast("TradeOffer[Item[OwnerT], Item[ClientUser], OwnerT]", self)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, TradeOffer):
            return NotImplemented
        return (
            self.id == other.id
            if self._has_been_sent and other._has_been_sent
            else self.sending == other.sending and self.receiving == other.receiving
        )

    def __hash__(self) -> int:
        return hash(self.id) if self._has_been_sent else hash((tuple(self.sending), tuple(self.receiving)))

    async def confirm(self) -> None:
        """Confirms the trade offer.
        This rarely needs to be called as the client handles most of these.

        Raises
        ------
        steam.ClientException
            The trade is not active.
        steam.ConfirmationError
            No matching confirmation could not be found.
        """
        self._check_active()
        if self.is_gift():
            return  # no point trying to confirm it
        confirmation = await self._state.wait_for_confirmation(self.id)
        await confirmation.confirm()
        self._state._confirmations.pop(self.id, None)

    async def accept(self) -> None:
        """Accepts the trade offer.

        Note
        ----
        This also calls :meth:`confirm` (if necessary) so you don't have to.

        Raises
        ------
        steam.ClientException
            The trade is either not active, already accepted or not from the ClientUser.
        steam.ConfirmationError
            No matching confirmation could not be found.
        """
        if self.state == TradeOfferState.Accepted:
            raise ClientException("This trade has already been accepted")
        if self.is_our_offer():
            raise ClientException("You cannot accept an offer the ClientUser has made")
        self._check_active()
        assert self.partner is not None
        resp = await self._state.http.accept_user_trade(self.partner.id64, self.id)
        if resp.get("needs_mobile_confirmation", False):
            await self.confirm()

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

    async def receipt(self) -> TradeOfferReceipt[OwnerT]:
        """Get the receipt for a trade offer and the updated asset ids for the trade.

        .. source:: steam.TradeOfferReceipt

        Returns
        -------
        A trade receipt.
        """
        if self._id is None:
            raise ValueError("Cannot fetch the receipt for a trade not accepted")

        data = await self._state.http.get_trade_receipt(self._id)
        (trade,) = data["trades"]
        descriptions = data["descriptions"]
        assert self.partner is not None

        return TradeOfferReceipt(
            sent=[
                MovedItem(self._state, data=description | asset, owner=self._state.user)
                for asset, description in itertools.product(trade.get("assets_given", ()), descriptions)
                if description["instanceid"] == asset["instanceid"] and description["classid"] == asset["classid"]
            ],
            received=[
                MovedItem(self._state, data=description | asset, owner=self.partner)
                for asset, description in itertools.product(trade.get("assets_received", ()), descriptions)
                if description["instanceid"] == asset["instanceid"] and description["classid"] == asset["classid"]
            ],
        )

    async def counter(
        self: TradeOffer[Asset[OwnerT], Asset[ClientUser], OwnerT],
        trade: TradeOffer[Asset[OwnerT], Asset[ClientUser], Any],
    ) -> None:
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

        assert self.partner is not None
        resp = await self._state.http.send_trade_offer(
            self.partner,
            [item.to_dict() for item in trade.sending],
            [item.to_dict() for item in trade.receiving],
            trade.token,
            trade.message or "",
            tradeofferid_countered=self.id,
        )
        trade._has_been_sent = True
        needs_confirmation = resp.get("needs_mobile_confirmation", False)
        trade._update_from_send(self._state, resp, self.partner, active=not needs_confirmation)
        if needs_confirmation:
            for tries in range(5):
                try:
                    await trade.confirm()
                    break
                except ConfirmationError:
                    await asyncio.sleep(tries * 2)
            else:
                raise ConfirmationError("Failed to confirm trade offer")
            trade.state = TradeOfferState.Active

        # make sure the trade is updated before this function returns
        self._state._trades[trade.id] = trade  # type: ignore  # we only use the value covariant-ly but but type checkers can't figure that out
        await self._state.wait_for_trade(trade.id)

    @property
    def url(self) -> str:
        """The URL of the trade offer."""
        return str(URL.COMMUNITY / f"tradeoffer/{self.id}")

    def is_gift(self) -> bool:
        """Helper method that checks if an offer is a gift to the :class:`~steam.ClientUser`"""
        return bool(self.receiving and not self.sending)

    def is_our_offer(self) -> bool:
        """Whether the offer was created by the :class:`~steam.ClientUser`."""
        return self._is_our_offer

    def _check_active(self) -> None:
        if self.state not in (TradeOfferState.Active, TradeOfferState.ConfirmationNeed) or not self._has_been_sent:
            raise ClientException("This trade is not active")
