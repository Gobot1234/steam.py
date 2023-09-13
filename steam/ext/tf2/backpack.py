from __future__ import annotations

import re
from contextvars import ContextVar
from typing import TYPE_CHECKING

from betterproto.casing import pascal_case
from typing_extensions import TypeVar

from ...trade import Inventory, Item
from ...utils import cached_slot_property
from .currency import Metal
from .enums import *
from .protobufs import base, econ, struct_messages

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ...abc import BaseUser, PartialUser
    from ...user import User
    from .client import ClientUser
    from .state import GCState
    from .types.schema import Schema

__all__ = (
    "BackpackItem",
    "Backpack",
)


WEAR_PARSER = re.compile("|".join(re.escape(wear.name) for wear in WearLevel))
SCHEMA = ContextVar["Schema"]("SCHEMA")
SKU_RE = re.compile(
    r"""\

""",
    re.VERBOSE,
)


OwnerT = TypeVar("OwnerT", bound="PartialUser", default="BaseUser", covariant=True)


class BackpackItem(Item[OwnerT]):
    """A class to represent an item from the client's backpack.

    Note
    ----
    This is meant to be user instantiable but only to use the following methods:

        - :meth:`is_australium`
        - :meth:`is_craftable`
        - :meth:`is_unusual`
        - :attr:`wear`
        - :attr:`equipable_by`
        - :attr:`slot`
    """

    __slots__ = (
        "position",
        "account_id",
        "inventory",
        "quantity",
        "level",
        "flags",
        "origin",
        "custom_name",
        "custom_description",
        "attribute",
        "interior_item",
        "in_use",
        "style",
        "original_id",
        "contains_equipped_state",
        "equipped_state",
        "contains_equipped_state_v2",
        "_quality_cs",
        "_def_index_cs",
    )
    REPR_ATTRS = (*Item.REPR_ATTRS, "position", "def_index")
    _state: GCState

    position: int
    """The item's position in the backpack."""

    account_id: int
    """Same as the :attr:`steam.ID.id` of the :attr:`steam.Client.user`."""
    inventory: int
    """The attribute the :attr:`position` is calculated from."""
    quantity: int
    """I think this should be the same as :attr:`amount`."""
    level: int
    """The item's level."""
    flags: ItemFlags
    """The item's flags."""
    origin: ItemOrigin
    """The item's origin."""
    custom_name: str
    custom_description: str
    attribute: list[base.ItemAttribute]
    interior_item: base.Item
    in_use: bool
    style: int
    original_id: int
    contains_equipped_state: bool
    equipped_state: list[base.ItemEquipped]
    contains_equipped_state_v2: bool

    # the other attribute definitions others not a clue please feel free to PR them

    @cached_slot_property
    def quality(self) -> ItemQuality:
        """The item's quality."""
        for tag in self.tags:
            if tag.category == "Quality":
                try:
                    return ItemQuality[tag.internal_name.title().replace(" ", "")]
                except KeyError:
                    pass
        raise RuntimeError(f"could not find quality for {self}")

    async def use(self: BackpackItem[ClientUser]) -> None:
        """Use this item."""
        await self._state.ws.send_gc_message(base.UseItem(item_id=self.id))

    async def open(self: BackpackItem[ClientUser], key: BackpackItem) -> None:
        """Open a crate with a ``key``.

        Parameters
        ----------
        key
            The key to open the crate with.
        """
        await self._state.ws.send_gc_message(struct_messages.OpenCrateRequest(key_id=key.id, crate_id=self.id))

    async def delete(self: BackpackItem[ClientUser]) -> None:
        """Delete this item."""
        await self._state.ws.send_gc_message(struct_messages.DeleteItemRequest(item_id=self.id))

    async def wrap(self: BackpackItem[ClientUser], wrapper: BackpackItem[ClientUser]) -> None:
        """Wrap this item with the ``wrapper``.

        Parameters
        ----------
        wrapper
            The wrapping paper to use.
        """
        await self._state.ws.send_gc_message(
            struct_messages.WrapItemRequest(item_id=self.id, wrapping_paper_id=wrapper.id)
        )

    async def unwrap(self: BackpackItem[ClientUser]) -> None:
        """Unwrap this item."""
        await self._state.ws.send_gc_message(struct_messages.UnwrapItemRequest(gift_id=self.id))

    async def equip(self: BackpackItem[ClientUser], mercenary: Mercenary, slot: ItemSlot) -> None:
        """Equip this item to a mercenary.

        Parameters
        ----------
        mercenary
            The mercenary to equip the item to.
        slot
            The item slot to equip the item to.
        """
        if slot >= ItemSlot.Misc:
            raise ValueError("cannot use enums that aren't real item slots")
        await self._state.ws.send_gc_message(
            base.AdjustItemEquippedState(item_id=self.id, new_class=mercenary, new_slot=slot)
        )

    async def set_position(self: BackpackItem[ClientUser], position: int) -> None:
        """Set the position for this item.

        Parameters
        ----------
        position
            The position to set the item to. This is 0 indexed.
        """
        assert self._state.backpack is not None
        await self._state.backpack.set_positions([(self, position)])

    async def set_style(self: BackpackItem[ClientUser], style: int) -> None:
        """Set the style for this item."""
        await self._state.ws.send_gc_message(struct_messages.SetItemStyleRequest(item_id=self.id, style=style))

    async def send_to(self: BackpackItem[ClientUser], user: User) -> None:
        """Send this gift-wrapped item to another user.

        Parameters
        ----------
        user
            The user to send this gift wrapped item to.
        """
        await self._state.ws.send_gc_message(struct_messages.DeliverGiftRequest(user_id64=user.id64, gift_id=self.id))

    # async def remove_attribute(self, attribute: Attribute) -> None:
    #     await self._state.ws.remove_attribute

    # methods similar to https://github.com/danocmx/node-tf2-item-format

    def is_australium(self) -> bool:
        """Whether or not the item is australium."""
        return "Australium" in self.name and self.name != "Australium Gold"

    def is_craftable(self) -> bool:
        """Whether or not the item is craftable."""
        return all(description.value != "( Not Usable in Crafting )" for description in self.descriptions)

    def is_festivized(self) -> bool:
        """Whether or not the item is festivized."""
        return any(
            description.value == "Festivized" and description.color == "ffd700" for description in self.descriptions
        )

    def is_festive(self) -> bool:
        """Whether or not the item is festive."""
        return self.name.startswith("Festive ")

    @property
    def wear(self) -> WearLevel | None:
        """The item's wear level."""
        wear = WEAR_PARSER.findall(self.name)
        return WearLevel[wear[0]] if wear else None

    @property
    def equipable_by(self) -> list[Mercenary]:
        """The mercenaries the item is equipable."""
        tags = [tag for tag in self.tags if tag.category == "Class"]
        return [Mercenary[mercenary.internal_name] for mercenary in tags]

    @property
    def slot(self) -> ItemSlot | None:
        """The item's equip slot."""
        for tag in self.tags:
            if tag.category == "Type" and tag.internal_name:
                try:
                    return ItemSlot[
                        pascal_case(tag.internal_name, strict=False)
                        .replace("Pda", "PDA")
                        .replace("Tf_Gift", "Gift")
                        .replace("Craft_Item", "CraftItem")
                    ]
                except KeyError:
                    return ItemSlot._new_member(name=tag.internal_name, value=-1)

    @cached_slot_property
    def def_index(self) -> int:
        """The item's def index. This is used to form the item's SKU."""
        for def_index, item in SCHEMA.get()["items"].items():
            if item.get("name") == self.name:
                return int(def_index)
        raise RuntimeError(f"Could not find def_index for {self.name}")

    @property
    def effect(self) -> str | None:
        """The item's unusual effect."""
        if self.quality != ItemQuality.Unusual:
            return
        for description in self.descriptions:
            if description.value.startswith("★ Unusual Effect: ") and description.color == "ffd700":
                return description.value.removeprefix("★ Unusual Effect: ")
        raise RuntimeError(f"Could not find unusual effect for {self.name}")

    @property
    def texture(self) -> int | None:
        """The item's texture."""
        for tag in self.tags:
            if tag.category == "texture":
                return int(tag.internal_name)

    @property
    def spells(self) -> list[str]:
        raise NotImplementedError

    @property
    def paint_colour(self) -> int | None:
        raise NotImplementedError

    @property
    def sku(self) -> str:
        """The item's SKU."""
        raise NotImplementedError
        parts = [str(self.def_index), ";", self.quality.value]

        if self.effect:
            parts.append(f";u{self.effect}")

        if self.is_australium():
            parts.append(";australium")

        if not self.is_craftable():
            parts.append(";uncraftable")

        if self.wear:
            parts.append(f";w{self.wear.value}")  # TODO check

        if self.texture:
            parts.append(f";pk{self.texture}")

        if self.elevated:
            parts.append(";strange")

        if self.killstreak:
            parts.append(f";kt-{self.killstreak}")

        if self.def_index:
            parts.append(f";td-{self.def_index}")

        if self.festivized:
            parts.append(";festive")

        if self.craft_number:
            parts.append(f";n{self.selfNumber.value}")

        if self.crate_number:
            parts.append(f";c{self.selfNumber.value}")

        return "".join(parts)

    @classmethod
    def from_sku(cls, value: str, /) -> BackpackItem[None]:  # type: ignore  # this is cursed, should probably be changed
        """Construct a :class:`BackPackItem` from an SKU.

        Parameters
        ----------
        value
            The SKU to construct the item from.

        Raises
        ------
        ValueError
            The SKU is invalid.
        """
        raise NotImplementedError
        self = cls.__new__(cls)

        data = SKU_RE.match(value)
        if data is None:
            raise ValueError(f"Invalid SKU: {value!r}")
        self.def_index = int(data["def_index"])

        return self

    # - to_listing?
    # - from_listing?
    # https://github.com/ZeusJunior/node-tf2-backpack/blob/7ce6fd0fc2ec648cee239c276742af2d3ab3fe5c/src/parser.ts#L19


class Backpack(Inventory[BackpackItem["ClientUser"], "ClientUser"]):
    """A class to represent the client's backpack."""

    __slots__ = ()

    @property
    def metal(self) -> Metal:
        """Returns the amount of metal in this inventory"""
        return Metal.from_items(self)

    async def set_positions(self, items_and_positions: Iterable[tuple[BackpackItem[ClientUser], int]]) -> None:
        """Set the positions of items in the inventory.

        Parameters
        ----------
        items_and_positions
            A list of (item, position) pairs to set the positions for. This is 0 indexed.
        """
        await self._state.ws.send_gc_message(
            base.SetItemPositions(
                item_positions=[
                    base.SetItemPositionsItemPosition(item_id=item.id, position=position)
                    for item, position in items_and_positions
                ],
            )
        )

    async def sort(self, type: BackpackSortType) -> None:
        """Sort this inventory.

        Parameters
        ----------
        type
            The sort type to sort by, only types visible in game are usable.
        """
        await self._state.ws.send_gc_message(base.SortItems(sort_type=type))

    async def trade_up(
        self, *items: BackpackItem[ClientUser]
    ) -> None:  # TODO would be nice to have a way to be able to return the new item
        """Trade up these items. Into a new item.

        Note
        ----
        The `TF2 wiki <https://wiki.teamfortress.com/wiki/Trade-Up#Item_Grade_Trade-Up>`_ for more info.
        """
        await self._state.ws.send_gc_message(econ.CraftCollectionUpgrade([item.id for item in items]))
