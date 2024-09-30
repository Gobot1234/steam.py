"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass

from ...._gc.client import ClientUser as ClientUser_
from ..protobufs import client_messages
from . import users


class ClientUser(users.PartialUser, ClientUser_):  # type: ignore
    # TODO: if TYPE_CHECKING: for inventory

    async def glicko_rating(self) -> GlickoRating:
        """Request Glicko Rank Information."""
        future = self._state.ws.gc_wait_for(client_messages.GCToClientRankResponse)
        await self._state.ws.send_gc_message(
            client_messages.ClientToGCRankRequest(rank_type=client_messages.ERankType.RankedGlicko)
        )
        response = await future
        return GlickoRating(
            mmr=response.rank_value,
            deviation=response.rank_data1,
            volatility=response.rank_data2,
            const=response.rank_data3,
        )

    async def behavior_summary(self) -> BehaviorSummary:
        """Request Behavior Summary."""
        future = self._state.ws.gc_wait_for(client_messages.GCToClientRankResponse)
        await self._state.ws.send_gc_message(
            client_messages.ClientToGCRankRequest(rank_type=client_messages.ERankType.BehaviorPublic)
        )
        response = await future
        return BehaviorSummary(behavior_score=response.rank_value, communication_score=response.rank_data1)
@dataclass(slots=True)
class GlickoRating:
    mmr: int
    deviation: int
    volatility: int
    const: int  # TODO: confirm all those names somehow or leave a note in doc that I'm clueless

    @property
    def confidence(self):
        return self.deviation / self.volatility  # TODO: confirm this


@dataclass(slots=True)
class BehaviorSummary:
    behavior_score: int
    communication_score: int
