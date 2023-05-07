from ....protobufs.msg import GCMessage
from ....utils import StructIO
from ..enums import EMsg


class NameItemRequest(GCMessage, msg=EMsg.NameItem):
    name_tag_id: int
    item_id: int
    name: str

    def __bytes__(self) -> bytes:
        with StructIO() as io:
            io.write_u64(self.name_tag_id)
            io.write_u64(self.item_id)
            io.write(b"\x00" + self.name.encode("UTF-8") + b"\x00")
            return io.buffer


class DeleteItemRequest(GCMessage, msg=EMsg.Delete):
    item_id: int
