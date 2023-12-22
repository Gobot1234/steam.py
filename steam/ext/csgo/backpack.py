"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from abc import ABCMeta
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from typing_extensions import Self, TypeVar

from ... import utils
from ...abc import BaseUser
from ...trade import Inventory, Item
from ...types.id import AssetID
from .enums import (
    ItemCustomizationNotification as ItemCustomizationNotificationEnum,
    ItemFlags,
    ItemOrigin,
    ItemQuality,
)
from .protobufs import base, econ, struct_messages

if TYPE_CHECKING:
    from datetime import datetime

    from ...abc import PartialUser
    from .client import ClientUser
    from .state import GCState

__all__ = (
    "Sticker",
    "Paint",
    "BaseItem",
    "CasketItem",
    "BaseInspectedItem",
    "InspectedItem",
    "BackpackItem",
    "Casket",
    "Backpack",
)


@dataclass(slots=True)
class Sticker:
    slot: Literal[0, 1, 2, 3, 4]
    """The sticker's slot."""
    id: int
    """The sticker's ID."""
    wear: float | None = None
    """The sticker's wear."""
    rotation: float | None = None
    """The sticker's rotation."""
    scale: float | None = None
    """The sticker's scale."""
    tint_id: float | None = None
    """The sticker's tint_id."""

    _decodeable_attrs = (
        "wear",
        "scale",
        "rotation",
    )


@dataclass(slots=True)
class Paint:
    """Represents the pain on an item."""

    index: float = 0.0
    """The paint's index."""
    seed: float = 0.0
    """The paint's seed."""
    wear: float = 0.0
    """The paint's wear."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} index={self.index} seed={self.seed} wear={self.wear}>"


class BaseItem(metaclass=ABCMeta):
    """Represents an item received from the Game Coordinator."""

    __slots__ = SLOTS = (
        "position",
        "paint",
        "tradable_after",
        "stickers",
        "_state",
        *tuple(base.Item.__annotations__),
    )
    if not TYPE_CHECKING:
        __slots__ = ()

    _state: GCState
    position: int
    """The item's position."""
    paint: Paint
    """The item's paint."""
    tradeable_after: datetime
    """The time the item's tradeable after."""
    stickers: list[Sticker]
    """The item's stickers."""
    id: AssetID
    """The item's asset ID."""
    account_id: int
    """The item's owner's 32-bit account ID."""
    inventory: int
    """Flags that aren't useful."""
    def_index: int
    """The item's def-index useful for its SKU."""
    quantity: int
    """The item's quantity."""
    level: int
    """The item's level."""
    quality: ItemQuality
    """The item's quality."""
    flags: ItemFlags
    """The item's flags."""
    origin: ItemOrigin
    """The item's origin."""
    custom_name: str
    """The item's custom name."""
    custom_description: str
    """The item's custom description."""
    attribute: list[base.ItemAttribute]
    """The item's attribute."""
    interior_item: base.Item
    """The item's interior item."""
    in_use: bool
    """Whether the item's in use."""
    style: int
    """The item's style."""
    original_id: int
    """The item's original ID."""
    equipped_state: list[base.ItemEquipped]
    """The item's equipped state."""
    rarity: int
    """The item's rarity."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} position={self.position}>"


@BaseItem.register
class CasketItem(BaseItem if TYPE_CHECKING else object):
    """Represents an item in a :class:`Casket`."""

    __slots__ = (*BaseItem.SLOTS, "_casket_id")
    _casket_id: AssetID

    @property
    def casket(self) -> Casket:
        """The casket this item is from."""
        backpack = self._state.backpack
        assert backpack is not None
        casket = utils.get(backpack, id=self._casket_id)
        assert isinstance(casket, Casket)
        return casket

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} casket={self.casket}>"


@dataclass
class _BaseInspectedItem(metaclass=ABCMeta):
    __slots__ = SLOTS = (
        "id",
        "def_index",
        "paint",
        "rarity",
        "quality",
        "kill_eater_score_type",
        "kill_eater_value",
        "custom_name",
        "stickers",
        "inventory",
        "origin",
        "quest_id",
        "drop_reason",
        "music_index",
        "ent_index",
    )
    if not TYPE_CHECKING:
        __slots__ = ()

    id: int
    """The item's asset ID."""
    def_index: int
    """The item's asset ID."""
    paint: Paint
    """The item's paint."""
    rarity: int
    """The item's rarity."""
    quality: ItemQuality
    """The item's quality."""
    kill_eater_score_type: int | None
    """The item's kill eater score type."""
    kill_eater_value: int | None
    """The item's kill eater value."""
    custom_name: str
    """The item's custom name."""
    stickers: list[Sticker]
    """The item's stickers."""
    inventory: int
    """The item's inventory."""
    origin: ItemOrigin
    """The item's origin."""
    quest_id: int
    """The item's quest id."""
    drop_reason: int
    """The item's drop reason."""
    music_index: int
    """The item's music index."""
    ent_index: int
    """The item's ent index."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"


@dataclass(repr=False)
@_BaseInspectedItem.register
class BaseInspectedItem(_BaseInspectedItem if TYPE_CHECKING else object, metaclass=ABCMeta):
    """Represents an item received after inspecting an item."""

    __slots__ = _BaseInspectedItem.SLOTS
    __annotations__ = _BaseInspectedItem.__annotations__


OwnerT = TypeVar("OwnerT", bound="PartialUser", default="BaseUser", covariant=True)


@BaseInspectedItem.register
class InspectedItem(Item[OwnerT], _BaseInspectedItem):
    __slots__ = _BaseInspectedItem.SLOTS


F = TypeVar("F", bound=Callable[..., object])


def has_to_be_in_our_inventory(func: F) -> F:
    assert func.__doc__ is not None
    func.__doc__ += """

    Note
    ----
    For this method to work the item has to be in the client's backpack.
    """
    return func


class BackpackItem(Item[OwnerT], BaseItem):
    """A class to represent an item which can interact with the GC."""

    __slots__ = tuple(set(BaseItem.SLOTS) - {"_state"})
    _state: GCState

    REPR_ATTRS = (*Item.REPR_ATTRS, "position")

    @classmethod
    def from_item(cls, item: Item) -> Self:
        """A "type safe" way to cast ``item`` to a :class:`BackpackItem`."""
        return utils.update_class(item, cls.__new__(cls))

    async def rename_to(self: BackpackItem[ClientUser], name: str, tag: BackpackItem[ClientUser]) -> None:
        """Rename this item to ``name`` with ``tag``.

        Parameters
        ----------
        name
            The desired name.
        tag
            The tag to consume for this request.
        """
        future = self._state.ws.gc_wait_for(
            econ.ItemCustomizationNotification,
            check=lambda msg: (
                isinstance(msg, econ.ItemCustomizationNotification)
                and msg.request == ItemCustomizationNotificationEnum.NameItem
                and msg.item_id[0] == self.id
            ),
        )
        await self._state.ws.send_gc_message(
            struct_messages.NameItemRequest(name_tag_id=tag.id, item_id=self.id, name=name)
        )
        await future

    @has_to_be_in_our_inventory
    async def delete(self: BackpackItem[ClientUser]) -> None:
        """Delete this item."""
        await self._state.ws.send_gc_message(struct_messages.DeleteItemRequest(item_id=self.id))

    @property
    def inspect_url(self) -> str | None:
        """The inspect url of item if it's inspectable."""
        try:
            for action in self.actions:
                if "inspect" in action.name.lower():
                    return action.link.replace("%owner_steamid%", str(self.owner.id64)).replace(
                        "%assetid%", str(self.id)
                    )

        except (ValueError, KeyError):
            return None

    async def inspect(self) -> InspectedItem:
        """Inspect this item.

        Note
        ----
        This mutates ``self`` in a way that attributes available on the :class:`InspectedItem` are available on
        ``self``.
        """
        inspect_url = self.inspect_url
        if inspect_url is None:
            raise ValueError("Cannot inspect this item")
        basic = await self._state.client.inspect_item(url=inspect_url)
        return utils.update_class(self, basic)


class Casket(BackpackItem["ClientUser"]):
    """Represents a casket/storage container."""

    __slots__ = ("contained_item_count",)
    REPR_ATTRS = (*BackpackItem.REPR_ATTRS, "contained_item_count")

    contained_item_count: int
    """The number of items contained in the casket."""

    async def add(self, item: BackpackItem) -> None:
        """Add an item to this casket.

        Parameters
        ----------
        item
            The item to add.
        """
        future = self._state.ws.gc_wait_for(
            econ.ItemCustomizationNotification,
            check=lambda msg: (
                msg.request == ItemCustomizationNotificationEnum.CasketAdded and msg.item_id[0] == self.id
            ),
        )
        await self._state.ws.send_gc_message(econ.CasketItemAdd(casket_item_id=self.id, item_item_id=item.id))
        await future
        self.contained_item_count += 1

    async def remove(self, item: CasketItem) -> BackpackItem[ClientUser]:
        """Remove an item from this casket.

        Parameters
        ----------
        item
            The item to remove.

        Returns
        -------
        The item as a :class:`BackpackItem` in your inventory.
        """
        if item._casket_id != self.id:
            raise ValueError("item is not in this casket")

        future = self._state.ws.gc_wait_for(
            econ.ItemCustomizationNotification,
            check=lambda msg: (
                msg.request == ItemCustomizationNotificationEnum.CasketRemoved and msg.item_id[0] == self.id
            ),
        )
        await self._state.ws.send_gc_message(econ.CasketItemExtract(casket_item_id=self.id, item_item_id=item.id))
        await future
        self.contained_item_count -= 1

        return cast("BackpackItem[ClientUser]", await self._state.wait_for_item(item.id))

    async def contents(self) -> list[CasketItem]:
        """This casket's contents"""
        contained_items = [item for item in self._state.casket_items.values() if item._casket_id == self.id]
        if len(contained_items) == self.contained_item_count:
            return contained_items

        future = self._state.ws.gc_wait_for(
            econ.ItemCustomizationNotification,
            check=lambda msg: (
                msg.request == ItemCustomizationNotificationEnum.CasketContents and msg.item_id[0] == self.id
            ),
        )
        await self._state.ws.send_gc_message(econ.CasketItemLoadContents(casket_item_id=self.id, item_item_id=self.id))

        notification = await future
        return await asyncio.gather(
            *map(self._state.wait_for_casket_item, cast("list[AssetID]", notification.item_id[1:]))
        )

    async def rename_to(self, name: str) -> None:  # type: ignore
        """Rename this casket to ``name``.

        Parameters
        ----------
        name
            The name to rename the casket to.

        Note
        ----
        Caskets require names to work so if you've purchased one and forgot to activate it, use this method activate
        it.
        """
        # TODO consider this might need a lock to make sure that we can actually update the correct item
        await super().rename_to(name, _FakeNameTag())


class _FakeNameTag(BackpackItem["ClientUser"]):
    id = AssetID(0)
    __slots__ = ()

    def __init__(self, *_: object, **__: object):
        pass


class Backpack(Inventory[BackpackItem["ClientUser"], "ClientUser"]):
    """A class to represent the client's backpack."""

    @property
    def caskets(self) -> Sequence[Casket]:
        """The caskets in this backpack."""
        return [item for item in self if isinstance(item, Casket)]
