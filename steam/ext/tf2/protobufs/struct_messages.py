from __future__ import annotations

from typing import TYPE_CHECKING

from ....protobufs.msg import GCMessage, GCProtobufMessage
from ....utils import StructIO
from ..enums import EMsg

if TYPE_CHECKING:
    from ....types.id import ID64, AssetID

# some custom messages to make things a lot easier decoding/encoding wise


class CraftRequest(GCMessage, msg=EMsg.Craft):
    recipe: int
    items: list[AssetID]

    def __bytes__(self) -> bytes:
        with StructIO() as io:
            io.write_struct("<hh", self.recipe, len(self.items))
            io.write_struct(f"<{len(self.items)}Q", *self.items)

            return io.buffer


class CraftResponse(GCMessage, msg=EMsg.CraftResponse):
    recipe_id: int
    ids: tuple[AssetID, ...]
    being_used: bool

    def parse(self, data: bytes, /) -> CraftResponse:  # type: ignore
        with StructIO(data) as io:
            self.recipe_id = io.read_i16()
            _ = io.read_u32()  # always 0 in mckay's experience
            id_count = io.read_i16()
            self.ids = io.read_struct(f"<{id_count}Q")
            self.being_used = False

        return self


class SetItemStyleRequest(GCMessage, msg=EMsg.SetItemStyle):
    item_id: AssetID
    style: int

    def __bytes__(self) -> bytes:
        with StructIO() as io:
            io.write_u64(self.item_id)
            io.write_u32(self.style)

            return io.buffer


class DeleteItemRequest(GCMessage, msg=EMsg.Delete):
    item_id: AssetID


class WrapItemRequest(GCMessage, msg=EMsg.GiftWrapItem):
    wrapping_paper_id: AssetID
    item_id: AssetID


class UnwrapItemRequest(GCMessage, msg=EMsg.UnwrapGiftRequest):
    gift_id: AssetID


class DeliverGiftRequest(GCMessage, msg=EMsg.DeliverGift):
    user_id64: ID64
    gift_id: AssetID


class OpenCrateRequest(GCMessage, msg=EMsg.UnlockCrate):
    key_id: AssetID
    crate_id: AssetID


class CacheSubscribedCheck(GCProtobufMessage, msg=EMsg.SOCacheSubscriptionCheck):
    pass
