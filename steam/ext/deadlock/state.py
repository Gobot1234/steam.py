"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from ..._gc import GCState as GCState_
from ...app import DEADLOCK
from ...enums import IntEnum
from ...errors import WSException
from ...id import _ID64_TO_ID32
from ...state import parser
from .models import PartialUser, User
from .protobufs import client_messages, sdk

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from weakref import WeakValueDictionary

    from ...protobufs import friends
    from ...types.id import ID32, ID64, Intable
    from .client import Client


class Result(IntEnum):
    # TODO: is there an official list for this?
    Invalid = 0
    OK = 1


class GCState(GCState_[Any]):  # TODO: implement basket-analogy for deadlock
    client: Client  # type: ignore  # PEP 705
    _users: WeakValueDictionary[ID32, User]
    _APP = DEADLOCK  # type: ignore

    def _store_user(self, proto: friends.CMsgClientPersonaStateFriend) -> User:
        try:
            user = self._users[_ID64_TO_ID32(proto.friendid)]
        except KeyError:
            user = User(state=self, proto=proto)
            self._users[user.id] = user
        else:
            user._update(proto)
        return user

    def get_partial_user(self, id: Intable) -> PartialUser:
        return PartialUser(self, id)

    if TYPE_CHECKING:

        def get_user(self, id: ID32) -> User | None: ...

        async def fetch_user(self, user_id64: ID64) -> User: ...

        async def fetch_users(self, user_id64s: Iterable[ID64]) -> Sequence[User]: ...

        async def _maybe_user(self, id: Intable) -> User: ...

        async def _maybe_users(self, id64s: Iterable[ID64]) -> Sequence[User]: ...

    def _get_gc_message(self) -> sdk.ClientHello:
        return sdk.ClientHello()

    @parser
    def parse_client_goodbye(self, msg: sdk.ConnectionStatus | None = None) -> None:
        if msg is None or msg.status == sdk.GCConnectionStatus.NoSession:
            self.dispatch("gc_disconnect")
            self._gc_connected.clear()
            self._gc_ready.clear()
        if msg is not None:
            self.dispatch("gc_status_change", msg.status)

    @parser
    async def parse_gc_client_connect(self, msg: sdk.ClientWelcome) -> None:
        if not self._gc_ready.is_set():
            self._gc_ready.set()
            self.dispatch("gc_ready")

    # DEADLOCK RELATED PROTO CALLS

    async def fetch_account_stats(
        self,
        account_id: int,
        dev_access_hint: bool,
        friend_access_hint: bool,
        *,
        timeout: float = 10.0,
    ) -> client_messages.ClientToGCGetAccountStatsResponse:
        """Fetch user's account stats."""
        await self.ws.send_gc_message(
            client_messages.ClientToGCGetAccountStats(
                account_id=account_id, dev_access_hint=dev_access_hint, friend_access_hint=friend_access_hint
            )
        )
        async with asyncio.timeout(timeout):
            response = await self.ws.gc_wait_for(client_messages.ClientToGCGetAccountStatsResponse)
        if response.eresult != Result.OK:
            raise WSException(response)
        return response
