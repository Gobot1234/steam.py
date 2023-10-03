"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import types
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any, Generic, cast, overload

from typing_extensions import NamedTuple, TypeVar, get_original_bases

from . import utils
from ._const import URL
from .app import App, PartialApp
from .enums import Language, TradeOfferState
from .models import AssetMixin, DescriptionMixin
from .protobufs import econ
from .types.id import AppID, AssetID, ClassID, ContextID, InstanceID, TradeOfferID
from .utils import DateTime

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from .abc import BaseUser, PartialUser
    from .friend import Friend
    from .state import ConnectionState
    from .types import trade
    from .user import ClientUser, User


__all__ = (
    "Asset",
    "Item",
    "Inventory",
    "TradeOffer",
    "MovedItem",
    "TradeOfferReceipt",
)


OwnerT = TypeVar("OwnerT", bound="PartialUser", default="BaseUser", covariant=True)


class Asset(AssetMixin, Generic[OwnerT]):
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
        "instance_id",
        "context_id",
        # "post_rollback_id",
        "owner",
    )
    REPR_ATTRS = ("id", "class_id", "instance_id", "context_id", "amount", "owner", "app")  # "post_rollback_id"

    def __init__(self, state: ConnectionState, asset: econ.Asset, owner: OwnerT):
        self.id = AssetID(asset.assetid)
        """The assetid of the item."""
        self.amount = asset.amount
        """The amount of the same asset there are in the inventory."""
        self.instance_id = InstanceID(asset.instanceid)
        """The instanceid of the item."""
        self.class_id = ClassID(asset.classid)
        self.context_id = ContextID(asset.contextid)
        """The contextid of the item."""
        # self.post_rollback_id = int(data["rollback_new_assetid"]) if "rollback_new_assetid" in data else None
        """The assetid of the item after a rollback (cancelled, etc.). ``None`` if not rolled back."""
        self.owner = owner
        """The owner of the asset."""
        self._app_id = AppID(asset.appid)
        self._state = state

    def __repr__(self) -> str:
        cls = self.__class__
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in cls.REPR_ATTRS]
        return f"<{cls.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Asset)
            and self.id == other.id
            and self._app_id == other._app_id
            and self.context_id == other.context_id
        )

    def __hash__(self) -> int:
        return hash((self.id, self._app_id, self.context_id))

    def to_dict(self) -> trade.AssetToDict:
        return {
            "assetid": str(self.id),
            "amount": self.amount,
            "appid": str(self._app_id),
            "contextid": str(self.context_id),
        }

    def to_proto(self) -> econ.Asset:
        return econ.Asset(
            assetid=self.id,
            amount=self.amount,
            instanceid=self.instance_id,
            classid=self.class_id,
            appid=self._app_id,
            contextid=self.context_id,
        )

    @property
    def url(self) -> str:
        """The URL for the asset in the owner's inventory.

        e.g. https://steamcommunity.com/profiles/76561198248053954/inventory/#440_2_8526584188
        """
        return f"{self.owner.community_url}/inventory#{self._app_id}_{self.context_id}_{self.id}"

    async def gift_to(
        self: Asset[ClientUser],
        recipient: Friend,
        /,
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


class Item(Asset[OwnerT], DescriptionMixin):
    """Represents an item in a User's inventory."""

    __slots__ = DescriptionMixin.SLOTS
    REPR_ATTRS = ("name", *Asset.REPR_ATTRS)

    def __init__(self, state: ConnectionState, asset: econ.Asset, description: econ.ItemDescription, owner: OwnerT):
        super().__init__(state, asset, owner)
        DescriptionMixin.__init__(self, state, description)


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
        "context_id",
        "_language",
        "_state",
        "__orig_class__",  # undocumented typing internals more shim to make extensions work
    )
    __orig_class__: InventoryGenericAlias

    def __init__(
        self,
        state: ConnectionState,
        proto: econ.GetInventoryItemsWithDescriptionsResponse,
        owner: OwnerT,
        app: App,
        context_id: ContextID,
        language: Language | None,
    ):
        self._state = state
        self.owner = owner
        """The owner of the inventory."""
        self.app = PartialApp(state, id=app.id, name=app.name)
        """The app the inventory belongs to."""
        self.context_id = context_id
        self._language = language
        self._update(proto)

    def __repr__(self) -> str:
        attrs = ("owner", "app")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        try:
            name = type(self).__name__
        except AttributeError:
            name = self.__orig_class__.__name__
        return f"<{name} {' '.join(resolved)}>"

    def __len__(self) -> int:
        return len(self.items)

    if not TYPE_CHECKING:
        __class_getitem__ = classmethod(InventoryGenericAlias)

        def __getitem__(self, idx):
            return self.items[idx]

    def __iter__(self) -> Iterator[ItemT]:
        return iter(self.items)

    def __contains__(self, item: object) -> bool:
        return item in self.items

    def _update(self, proto: econ.GetInventoryItemsWithDescriptionsResponse, /) -> None:
        items: list[ItemT] = []
        ItemClass: type[ItemT]
        try:  # ideally one day this will just be ItemT.__value__ or something
            ItemClass, *_ = self.__orig_class__.__args__
        except AttributeError:
            ItemClass = get_original_bases(self.__class__)[0].__args__[0].__default__
        for asset in proto.assets:
            description = utils.get(proto.descriptions, instanceid=asset.instanceid, classid=asset.classid)
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
            proto = await self._state.fetch_user_inventory(
                self.owner.id64, self.app.id, self.context_id, self._language
            )
        self._update(proto)


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
            asset=econ.Asset().from_dict(data),
            description=econ.ItemDescription().from_dict(data),
            owner=owner,
        )
        try:
            self.new_id = AssetID(
                int(data["new_assetid"]) if "new_assetid" in data else int(data["rollback_new_assetid"])
            )
            """The new_assetid field, this is the asset ID of the item in the partners inventory."""
        except KeyError:
            self.new_id = AssetID(-1)  # steam broke?

        try:
            self.new_context_id = ContextID(
                int(data["new_contextid"]) if "new_contextid" in data else int(data["rollback_new_contextid"])
            )
            """The new_contextid field."""
        except KeyError:
            self.new_context_id = ContextID(-1)  # steam broke again probably


ReceivingAssetT = TypeVar("ReceivingAssetT", bound="Asset[PartialUser]", default="Item[User]", covariant=True)
SendingAssetT = TypeVar("SendingAssetT", bound="Asset[ClientUser]", default="Item[ClientUser]", covariant=True)
UserT = TypeVar("UserT", bound="PartialUser", default="User", covariant=True)


class TradeOffer(Generic[ReceivingAssetT, SendingAssetT, UserT]):
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
        "user",
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
    user: UserT
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
    def _from_api(
        cls,
        state: ConnectionState,
        data: trade.TradeOffer,
        sending: list[tuple[econ.Asset, econ.ItemDescription]],
        receiving: list[tuple[econ.Asset, econ.ItemDescription]],
        user: UserT,  # type: ignore
    ) -> TradeOffer[Item[UserT], Item[ClientUser], UserT]:
        trade = cls()
        trade._has_been_sent = True
        trade._state = state
        trade.user = user
        return cast(
            "TradeOffer[Item[UserT], Item[ClientUser], UserT]",
            trade._update(data, sending=sending, receiving=receiving),
        )

    @classmethod
    def _from_history(
        cls: type[TradeOffer[MovedItem[UserT], MovedItem[ClientUser], UserT]],
        state: ConnectionState,
        data: trade.TradeOfferHistoryTrade,
        descriptions: Sequence[trade.Description],
    ) -> TradeOffer[MovedItem[UserT], MovedItem[ClientUser], UserT]:
        user = cast("UserT", state.get_partial_user(data["steamid_other"]))
        trade = cls(
            receiving=[
                MovedItem(state, description | asset, user)
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
        trade.user = user
        trade.created_at = DateTime.from_timestamp(data["time_init"])
        trade.state = TradeOfferState.try_value(data["status"])

        return trade

    def _update_from_send(
        self, state: ConnectionState, data: trade.TradeOfferCreateResponse, user: UserT, active: bool = True  # type: ignore
    ) -> None:
        self.id = TradeOfferID(int(data["tradeofferid"]))
        self._state = state
        self.user = user
        self.state = TradeOfferState.Active if active else TradeOfferState.ConfirmationNeed
        self.created_at = DateTime.now()
        self._is_our_offer = True

    def __repr__(self) -> str:
        attrs = ("id", "state", "user")
        resolved = [f"{attr}={getattr(self, attr, None)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    @overload
    def _update(
        self: TradeOffer[Asset[UserT], Asset[ClientUser], UserT],
        data: trade.TradeOffer,
        sending: list[tuple[econ.Asset, econ.ItemDescription]],
        receiving: list[tuple[econ.Asset, econ.ItemDescription]],
    ) -> TradeOffer[Item[UserT], Item[ClientUser], UserT]:
        ...

    @overload
    def _update(
        self: TradeOffer[Asset[UserT], Asset[ClientUser], UserT],
        data: trade.TradeOffer,
        sending: list[econ.Asset],
        receiving: list[econ.Asset],
    ) -> TradeOffer[Asset[UserT], Asset[ClientUser], UserT]:
        ...

    def _update(
        self: TradeOffer[Asset[UserT], Asset[ClientUser], UserT],
        data: trade.TradeOffer,
        sending: list[tuple[econ.Asset, econ.ItemDescription]] | list[econ.Asset],
        receiving: list[tuple[econ.Asset, econ.ItemDescription]] | list[econ.Asset],
    ) -> TradeOffer[Item[UserT], Item[ClientUser], UserT] | TradeOffer[Asset[UserT], Asset[ClientUser], UserT]:
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
        self._is_our_offer = data.get("is_our_offer", False)
        if (self.state != TradeOfferState.Accepted) and (
            sending or receiving
        ):  # steam doesn't really send the item data if the offer just got accepted
            try:
                self.sending = [
                    Item(self._state, asset=asset, description=description, owner=self._state.user)
                    for asset, description in cast("list[tuple[econ.Asset, econ.ItemDescription]]", sending)
                ]
                self.receiving = [
                    Item(self._state, asset=asset, description=description, owner=self.user)
                    for asset, description in cast("list[tuple[econ.Asset, econ.ItemDescription]]", receiving)
                ]
                return cast("TradeOffer[Item[UserT], Item[ClientUser], UserT]", self)
            except TypeError:
                self.sending = [
                    Asset(self._state, asset=asset, owner=self._state.user)
                    for asset in cast("list[econ.Asset]", sending)
                ]
                self.receiving = [
                    Asset(self._state, asset=asset, owner=self.user) for asset in cast("list[econ.Asset]", receiving)
                ]
        return self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TradeOffer):
            return False
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
        ValueError
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
        ValueError
            The trade is either not active, already accepted or not from the ClientUser.
        ConfirmationError
            No matching confirmation could not be found.
        """
        if self.state == TradeOfferState.Accepted:
            raise ValueError("This trade has already been accepted")
        if self.is_our_offer():
            raise ValueError("You cannot accept an offer the ClientUser has made")
        self._check_active()
        assert self.user is not None
        resp = await self._state.http.accept_user_trade(self.user.id64, self.id)
        if resp.get("needs_mobile_confirmation", False):
            await self.confirm()

    async def decline(self) -> None:
        """Declines the trade offer.

        Raises
        ------
        ValueError
            The trade is either not active, already declined or not from the ClientUser.
        """
        if self.state == TradeOfferState.Declined:
            raise ValueError("This trade has already been declined")
        if self.is_our_offer():
            raise ValueError("You cannot decline an offer the ClientUser has made")
        self._check_active()
        await self._state.http.decline_user_trade(self.id)

    async def cancel(self) -> None:
        """Cancels the trade offer.

        Raises
        ------
        ValueError
            The trade is either not active or already cancelled.
        """
        if self.state == TradeOfferState.Canceled:
            raise ValueError("This trade has already been cancelled")
        self._check_active()
        await self._state.http.cancel_user_trade(self.id)

    async def receipt(self) -> TradeOfferReceipt[UserT]:
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
        assert self.user is not None

        return TradeOfferReceipt(
            sent=[
                MovedItem(self._state, data={**description, **asset}, owner=self._state.user)
                for asset, description in itertools.product(trade.get("assets_given", ()), descriptions)
                if description["instanceid"] == asset["instanceid"] and description["classid"] == asset["classid"]
            ],
            received=[
                MovedItem(self._state, data={**description, **asset}, owner=self.user)
                for asset, description in itertools.product(trade.get("assets_received", ()), descriptions)
                if description["instanceid"] == asset["instanceid"] and description["classid"] == asset["classid"]
            ],
        )

    async def counter(
        self: TradeOffer[Asset[UserT], Asset[ClientUser], UserT],
        trade: TradeOffer[Asset[UserT], Asset[ClientUser], Any],
        /,
    ) -> None:
        """Counter a trade offer from an :class:`User`.

        Parameters
        -----------
        trade
            The trade offer to counter with.

        Raises
        ------
        ValueError
            The trade from the ClientUser or it isn't active.
        """
        self._check_active()
        if self.is_our_offer():
            raise ValueError("You cannot counter an offer the ClientUser has made")

        assert self.user is not None
        await self.user._send_trade(trade, tradeofferid_countered=self.id)

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
            raise ValueError("This trade is not active")
