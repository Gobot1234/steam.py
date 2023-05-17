from __future__ import annotations

import asyncio
import os
from collections.abc import Collection
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast, overload

from typing_extensions import Self

from ..._const import VDF_LOADS, timeout
from ..._gc import Client as Client_
from ..._gc.client import ClientUser as ClientUser_
from ...app import TF2, App
from ...ext import commands
from ...utils import cached_property
from .protobufs import struct_messages
from .state import GCState

if TYPE_CHECKING:
    from ...enums import Language as Language_
    from ...ext import tf2
    from ...trade import Inventory, Item
    from .backpack import Backpack, BackpackItem, Schema

__all__ = (
    "Client",
    "Bot",
)


class TF2ClientUser(ClientUser_):
    if TYPE_CHECKING:

        @overload
        async def inventory(self, app: Literal[TF2], *, language: object = ...) -> Backpack:  # type: ignore
            ...

        @overload
        async def inventory(self, app: App, *, language: Language_ | None = None) -> Inventory[Item[Self], Self]:
            ...


class Client(Client_):
    _APP: Final = TF2
    _ClientUserCls = TF2ClientUser
    user: cached_property[Self, TF2ClientUser]
    _state: GCState

    def _get_gc_message(self) -> Any:
        return False  # for now this isn't required

    @property
    def schema(self) -> Schema:
        """TF2's item schema. ``None`` if the user isn't ready."""
        return self._state.schema

    @property
    def backpack_slots(self) -> int:
        """The client's number of backpack slots."""
        if self._state.backpack_slots is None:
            raise RuntimeError("GC isn't ready yet")
        return self._state.backpack_slots

    def is_premium(self) -> bool:
        """Whether or not the client's account has TF2 premium. ``None`` if the user isn't ready."""
        return self._state._is_premium  # type: ignore

    def set_language(self, file: os.PathLike[str]) -> None:  # TODO this doesn't work
        """Set the localization files for your bot.

        This isn't necessary in most situations.
        """
        file = Path(file).resolve()
        self._state.localisation = VDF_LOADS(file.read_text())

    async def craft(
        self, items: Collection[BackpackItem[TF2ClientUser]], recipe: int = -2
    ) -> list[BackpackItem[TF2ClientUser]] | None:
        """Craft a set of items together with an optional recipe.

        Parameters
        ----------
        items
            The items to craft.
        recipe
            The recipe to craft them with default is -2 (wildcard). Setting for metal crafts isn't required. See
            https://raw.githubusercontent.com/Gobot1234/TF2-Crafting-Recipe/master/craftRecipe.json for other recipe
            details.

        Returns
        -------
        The crafted items, ``None`` if crafting failed.
        """

        def check_craft(msg: struct_messages.CraftResponse) -> bool:
            if not msg.being_used:  # craft queue is FIFO, so this works fine
                msg.being_used = True
                return True

            return False

        future = self._state.ws.gc_wait_for(struct_messages.CraftResponse, check=check_craft)
        await self._state.ws.send_gc_message(
            struct_messages.CraftRequest(recipe=recipe, items=[item.id for item in items])
        )

        try:
            async with timeout(60):
                resp = await future
        except asyncio.TimeoutError:
            return
        else:
            recipe_id = resp.recipe_id
            if recipe_id == -1:  # error occurred
                return

        return cast(
            "list[BackpackItem[TF2ClientUser]]", await asyncio.gather(*map(self._state.wait_for_item, resp.ids))
        )

    if TYPE_CHECKING:

        async def on_account_update(self) -> None:
            """Called when the client user's account is updated. This can happen from any one of the below changing:

            - :meth:`is_premium`
            - :attr:`backpack_slots`
            """

        async def on_item_receive(self, item: tf2.BackpackItem) -> None:
            """Called when the client receives an item.

            Parameters
            ----------
            item
                The received item.
            """

        async def on_item_remove(self, item: tf2.BackpackItem) -> None:
            """Called when the client has an item removed from its backpack.

            Parameters
            ----------
            item
                The removed item.
            """

        async def on_item_update(self, before: tf2.BackpackItem, after: tf2.BackpackItem) -> None:
            """Called when the client has an item in its backpack updated.

            Parameters
            ----------
            before
                The item before being updated.
            after
                The item now.
            """


class Bot(commands.Bot, Client):
    pass
