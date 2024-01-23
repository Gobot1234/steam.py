"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..._gc import GCState as GCState_
from ...app import DOTA2
from .protobufs.gcsdk_gcmessages import CMsgClientHello

if TYPE_CHECKING:
    from .client import Client


class GCState(GCState_[Any]):  # todo: implement basket-analogy for dota2
    client: Client  # type: ignore  # PEP 705
    _APP = DOTA2  # type: ignore

    def _get_gc_message(self) -> CMsgClientHello:
        return CMsgClientHello()
