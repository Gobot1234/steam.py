"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from ... import abc, user
from ..._gc.client import ClientUser as ClientUser_

if TYPE_CHECKING:
    from .protobufs import client_messages, common
    from .state import GCState

UserT = TypeVar("UserT", bound=abc.PartialUser)

__all__ = (
    "ClientUser",
    "PartialUser",
    "User",
)


class PartialUser(abc.PartialUser):
    __slots__ = ()
    _state: GCState

    async def account_stats(self):
        """Fetch user's Deadlock account stats."""
        proto = await self._state.fetch_account_stats(self.id, False, True)
        return AccountStats(proto)


class User(PartialUser, user.User):  # type: ignore
    __slots__ = ()


class ClientUser(PartialUser, ClientUser_):  # type: ignore
    # TODO: if TYPE_CHECKING: for inventory
    ...


class AccountStats:
    def __init__(self, proto: client_messages.ClientToGCGetAccountStatsResponse):
        self.account_id = proto.stats.account_id
        self.stats = [AccountHeroStats(p) for p in proto.stats.stats]


class AccountHeroStats:
    def __init__(self, proto: common.AccountHeroStats) -> None:
        self.hero_id: int = proto.hero_id  # TODO: Modelize Enum
        self.stat_id: list[int] = proto.stat_id
        self.total_value: list[int] = proto.total_value
        self.medals_bronze: list[int] = proto.medals_bronze
        self.medals_silver: list[int] = proto.medals_silver
        self.medals_gold: list[int] = proto.medals_gold
