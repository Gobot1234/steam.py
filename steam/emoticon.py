from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from .game import Game

if TYPE_CHECKING:
    from .protobufs.steammessages_player import CPlayerGetEmoticonListResponseEmoticon as EmoticonProto


class ClientEmoticon:
    __slots__ = ("name", "game", "count", "use_count", "last_used", "received_at")

    def __init__(self, proto: EmoticonProto):
        self.name = proto.name.strip(":")  # :emoji_name:
        self.game = Game(id=proto.appid)
        self.count = proto.count
        self.use_count = proto.use_count
        self.last_used = datetime.utcfromtimestamp(proto.time_last_used)
        self.received_at = datetime.utcfromtimestamp(proto.time_received)

    def __str__(self):
        return f":{self.name}:"

    def __repr__(self) -> str:
        return f"<ClientEmoticon name={self.name!r} game={self.game!r} count={self.count!r}>"
