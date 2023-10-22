from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

from ... import utils
from ..._const import VDF_LOADS
from ..._gc.state import GCState as GCState_
from ...app import TF2
from ...errors import HTTPException
from ...state import parser
from .backpack import SCHEMA, Backpack
from .enums import ItemFlags, ItemOrigin
from .protobufs import base, sdk, struct_messages

if TYPE_CHECKING:
    from multidict import MultiDict

    from .client import Client
    from .types.schema import Schema


log = logging.getLogger(__name__)


class GCState(GCState_[Backpack]):
    client: Client  # type: ignore  # PEP 705
    _APP = TF2  # type: ignore

    def __init__(self, client: Client, **kwargs: Any):
        super().__init__(client, **kwargs)
        self.schema: Schema
        self.localisation: MultiDict[Any] | None = None
        self.backpack_slots: int | None = None
        self._is_premium: bool | None = None

        # language = kwargs.get("language")
        # if language is not None:
        #     client.set_language(language)

    def _get_gc_message(self) -> None:
        return

    @parser
    def parse_gc_client_connect(self, _: base.ClientWelcome | None = None) -> None:
        if not self._gc_connected.is_set():
            self.dispatch("gc_connect")
            self._gc_connected.set()

    @parser
    def parse_client_goodbye(self, _: base.ClientGoodbye | None = None) -> None:
        self.dispatch("gc_disconnect")
        self._gc_connected.clear()

    # TODO maybe stuff for servers?
    @parser
    async def parse_schema(self, msg: base.UpdateItemSchema) -> None:
        log.info("Getting TF2 item schema at %s", msg.items_game_url)
        try:
            resp = await self.http._session.get(msg.items_game_url)
        except Exception as exc:
            return log.error("Failed to get item schema", exc_info=exc)

        self.schema = cast("Schema", VDF_LOADS(await resp.text())["items_game"])
        SCHEMA.set(self.schema)
        log.info("Loaded schema")

    @parser
    def parse_system_message(self, msg: base.SystemBroadcast) -> None:
        self.dispatch("system_message", msg.message)

    @parser
    def parse_client_notification(self, msg: base.ClientDisplayNotification) -> None:
        if self.localisation is None:
            return

        title = self.localisation[msg.notification_title_localization_key[1:]]
        text = re.sub(r"[\u0001|\u0002]", "", self.localisation[msg.notification_body_localization_key[1:]])
        for i, replacement in enumerate(msg.body_substring_values):
            if replacement[0] == "#":
                replacement = self.localisation[replacement[1:]]
            text = text.replace(f"%{msg.body_substring_keys[i]}%", replacement)
        self.dispatch("display_notification", title, text)

    @parser
    async def parse_cache_check(self, _: struct_messages.CacheSubscribedCheck | None = None) -> None:
        log.debug("Requesting SO cache subscription refresh")
        msg = sdk.CacheSubscriptionRefresh(owner=self.client.user.id64)
        await self.ws.send_gc_message(msg)

    async def update_backpack(self, *cso_items: base.Item, is_cache_subscribe: bool = False) -> None:
        await self.client.wait_until_ready()

        backpack = self.backpack or await self.fetch_backpack(Backpack)
        item_ids = [item.id for item in backpack]

        if any(cso_item.id not in item_ids for cso_item in cso_items):
            try:
                await backpack.update()
            except HTTPException:
                pass

            item_ids = [item.id for item in backpack]

            if any(cso_item.id not in item_ids for cso_item in cso_items):
                await self.restart_tf2()
                await backpack.update()  # if the item still isn't here something on valve's end has broken

        for cso_item in cso_items:  # merge the two items
            item = utils.get(backpack, id=cso_item.id)
            if item is None:
                continue  # the item has been removed (gc sometimes sends you items that you have crafted/deleted)
            for attribute_name in cso_item.__annotations__:
                setattr(item, attribute_name, getattr(cso_item, attribute_name))

            is_new = is_cache_subscribe and (cso_item.inventory >> 30) & 1
            item.position = 0 if is_new else cso_item.inventory & 0xFFFF
            item.flags = ItemFlags.try_value(cso_item.flags)
            item.origin = ItemOrigin.try_value(cso_item.origin)

        self.backpack = backpack

    @parser
    async def parse_cache_subscribe(self, msg: sdk.CacheSubscribed) -> None:
        for object in msg.objects:
            if object.type_id == 1:  # backpack
                await self.update_backpack(
                    *(base.Item().parse(item_data) for item_data in object.object_data),
                    is_cache_subscribe=True,
                )
            elif object.type_id == 7:  # account metadata
                proto = base.GameAccountClient().parse(object.object_data[0])
                self._is_premium = not proto.trial_account
                self.backpack_slots = (50 if proto.trial_account else 300) + proto.additional_backpack_slots
        if self._gc_connected.is_set():
            self._gc_ready.set()
            self.dispatch("gc_ready")

    @parser
    async def parse_item_add(self, msg: sdk.SOCreate) -> None:
        if msg.type_id != 1 or not self.backpack:
            return

        cso_item = base.Item().parse(msg.object_data)
        await self.update_backpack(cso_item)
        item = utils.get(self.backpack, id=cso_item.id)
        if item is None:  # protect from a broken item
            return
        self.dispatch("item_receive", item)

    @utils.call_once
    async def restart_tf2(self) -> None:
        async with self.temporarily_play(*self._original_apps):
            self.parse_client_goodbye()

        await self._gc_connected.wait()

    @parser
    async def handle_so_update(self, msg: sdk.SOUpdate) -> None:
        await self._handle_so_update(msg)

    @parser
    async def handle_multiple_so_update(self, msg: sdk.MultipleObjects) -> None:
        for item in msg.objects:
            await self._handle_so_update(item)

    async def _handle_so_update(self, object: sdk.SOUpdate | sdk.MultipleObjectsSingleObject) -> None:
        if object.type_id == 1:
            if not self.backpack:
                return

            cso_item = base.Item().parse(object.object_data)

            old_item = utils.get(self.backpack, id=cso_item.id)
            if old_item is None:  # broken item
                return
            await self.update_backpack(cso_item)
            new_item = utils.get(self.backpack, id=cso_item.id)
            if new_item is None:
                return

            self.dispatch("item_update", old_item, new_item)
        elif object.type_id == 7:
            proto = base.GameAccountClient().parse(object.object_data)
            backpack_slots = (50 if proto.trial_account else 300) + proto.additional_backpack_slots
            if proto.trial_account == self._is_premium or self.backpack_slots != backpack_slots:
                self._is_premium = not proto.trial_account
                self.backpack_slots = backpack_slots
                self.dispatch("account_update")
        else:
            log.debug("Unknown item %r updated", object)

    @parser
    async def handle_item_remove(self, msg: sdk.SODestroy) -> None:
        if msg.type_id != 1 or not self.backpack:
            return

        deleted_item = base.Item().parse(msg.object_data)
        item = utils.get(self.backpack, id=deleted_item.id)
        if item is None:  # broken item
            return
        for attribute_name in deleted_item.__annotations__:
            setattr(item, attribute_name, getattr(deleted_item, attribute_name))
        self.backpack.items.remove(item)  # type: ignore
        self.dispatch("item_remove", item)
