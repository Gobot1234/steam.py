"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..._gc import GCState as GCState_
from ...app import DOTA2
from .protobufs.client_messages import CMsgClientToGCGetProfileCard
from .protobufs.common import CMsgDOTAProfileCard
from .protobufs.sdk import CMsgClientHello

if TYPE_CHECKING:
    from .client import Client


class GCState(GCState_[Any]):  # todo: implement basket-analogy for dota2
    client: Client  # type: ignore  # PEP 705
    _APP = DOTA2  # type: ignore

    def _get_gc_message(self) -> CMsgClientHello:
        return CMsgClientHello()

    async def fetch_user_dota2_profile_card(self, user_id: int):
        await self.ws.send_gc_message(CMsgClientToGCGetProfileCard(account_id=user_id))
        return await self.ws.gc_wait_for(
            CMsgDOTAProfileCard,
            check=lambda msg: msg.account_id == user_id,
        )
