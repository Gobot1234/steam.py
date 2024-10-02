"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, Unpack

from ..._gc import GCState as GCState_
from ...app import DOTA2
from ...enums import IntEnum
from ...errors import WSException
from ...id import _ID64_TO_ID32
from ...state import parser
from .models import PartialUser, User
from .protobufs import client_messages, common, sdk, watch

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from weakref import WeakValueDictionary

    from ...protobufs import friends
    from ...types.id import ID32, ID64, Intable
    from .client import Client

    # TODO: test this whole Kwargs thing, does it error if we don't provide some of them?
    # what defaults does it assume?

    class MatchHistoryKwargs(TypedDict):
        account_id: NotRequired[int]
        start_at_match_id: NotRequired[int]
        matches_requested: NotRequired[int]
        hero_id: NotRequired[int]
        include_practice_matches: NotRequired[bool]
        include_custom_games: NotRequired[bool]
        include_event_games: NotRequired[bool]
        request_id: NotRequired[int]

    class PostSocialMessageKwargs(TypedDict):
        message: NotRequired[str]
        match_id: NotRequired[int]
        match_timestamp: NotRequired[int]


class Result(IntEnum):
    # TODO: is there an official list for this?
    Invalid = 0
    OK = 1


class GCState(GCState_[Any]):  # TODO: implement basket-analogy for dota2
    client: Client  # type: ignore  # PEP 705
    _users: WeakValueDictionary[ID32, User]
    _APP = DOTA2  # type: ignore

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

    # dota fetch proto calls
    # the difference between these calls and the ones in `client`/`models` is that
    # they directly give proto-response while the latter modelize them into more convenient formats.

    async def fetch_dota2_profile(self, account_id: int) -> client_messages.ProfileResponse:
        """Fetch user's dota 2 profile."""
        await self.ws.send_gc_message(client_messages.ProfileRequest(account_id=account_id))
        return await self.ws.gc_wait_for(client_messages.ProfileResponse)

    async def fetch_dota2_profile_card(self, account_id: int) -> common.ProfileCard:
        """Fetch user's dota 2 profile card."""
        await self.ws.send_gc_message(client_messages.ClientToGCGetProfileCard(account_id=account_id))
        return await self.ws.gc_wait_for(common.ProfileCard, check=lambda msg: msg.account_id == account_id)

    async def fetch_match_history(self, **kwargs: Unpack[MatchHistoryKwargs]):
        """Fetch match history."""
        await self.ws.send_gc_message(client_messages.GetPlayerMatchHistory(**kwargs))
        return await self.ws.gc_wait_for(client_messages.GetPlayerMatchHistoryResponse)

    async def fetch_matches_minimal(
        self, match_ids: list[int], *, timeout: float = 7.0
    ) -> watch.ClientToGCMatchesMinimalResponse:
        """Fetch matches minimal."""
        await self.ws.send_gc_message(watch.ClientToGCMatchesMinimalRequest(match_ids=match_ids))
        async with asyncio.timeout(timeout):
            return await self.ws.gc_wait_for(watch.ClientToGCMatchesMinimalResponse)

    async def fetch_match_details(self, match_id: int, timeout: float = 7.0) -> client_messages.MatchDetailsResponse:
        """Fetch match details."""
        await self.ws.send_gc_message(client_messages.MatchDetailsRequest(match_id=match_id))
        async with asyncio.timeout(timeout):
            response = await self.ws.gc_wait_for(
                client_messages.MatchDetailsResponse, check=lambda msg: msg.match.match_id == match_id
            )
        if response.eresult != Result.OK:
            raise WSException(response)
        return response

    async def fetch_rank(self, rank_type: client_messages.ERankType) -> client_messages.GCToClientRankResponse:
        """Fetch rank."""
        await self.ws.send_gc_message(client_messages.ClientToGCRankRequest(rank_type=rank_type))
        return await self.ws.gc_wait_for(client_messages.GCToClientRankResponse)

    async def post_social_message(
        self, **kwargs: Unpack[PostSocialMessageKwargs]
    ) -> client_messages.GCToClientSocialFeedPostMessageResponse:
        await self.ws.send_gc_message(client_messages.ClientToGCSocialFeedPostMessageRequest(**kwargs))
        response = await self.ws.gc_wait_for(client_messages.GCToClientSocialFeedPostMessageResponse)
        if response.success != Result.OK:
            raise WSException(response)
        return response
