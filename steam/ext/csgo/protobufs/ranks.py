from dataclasses import dataclass

import betterproto

from ....protobufs.msg import GCProtobufMessage
from ..enums import EMsg


class PlayerRankingInfo(GCProtobufMessage, msg=EMsg.ClientGetPlayerRankingInfoResponse):
    account_id: int = betterproto.uint32_field(1)
    rank_id: int = betterproto.uint32_field(2)
    wins: int = betterproto.uint32_field(3)
    rank_change: float = betterproto.float_field(4)
    rank_type_id: int = betterproto.uint32_field(6)
    tv_control: int = betterproto.uint32_field(7)
    rank_window_stats: int = betterproto.uint64_field(8)
    leaderboard_name: str = betterproto.string_field(9)
    rank_if_win: int = betterproto.uint32_field(10)
    rank_if_lose: int = betterproto.uint32_field(11)
    rank_if_tie: int = betterproto.uint32_field(12)
    per_map_rank: "list[PerMapRank]" = betterproto.message_field(13)
    leaderboard_name_status: int = betterproto.uint32_field(14)

    @dataclass(eq=False, repr=False)
    class PerMapRank(betterproto.Message):
        map_id: int = betterproto.uint32_field(1)
        rank_id: int = betterproto.uint32_field(2)
        wins: int = betterproto.uint32_field(3)
