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
        account_id: int
        start_at_match_id: NotRequired[int]
        matches_requested: int
        hero_id: NotRequired[int]
        include_practice_matches: bool
        include_custom_games: bool
        include_event_games: bool
        request_id: NotRequired[int]

    class PostSocialMessageKwargs(TypedDict):
        message: NotRequired[str]
        match_id: NotRequired[int]
        match_timestamp: NotRequired[int]

    class TopSourceTVGamesKwargs(TypedDict):
        search_key: NotRequired[str]
        league_id: NotRequired[int]
        hero_id: NotRequired[int]
        start_game: NotRequired[int]
        game_list_index: NotRequired[int]
        lobby_ids: NotRequired[list[int]]


class Result(IntEnum):
    # TODO: is there an official list for this?
    Invalid = 0
    OK = 1


TIMEOUT_DEFAULT = 8.0  # not sure which value would suit the best;


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

    async def fetch_top_source_tv_games(
        self, **kwargs: Unpack[TopSourceTVGamesKwargs]
    ) -> list[watch.GCToClientFindTopSourceTVGamesResponse]:
        """Fetch Top Source TV Games."""
        start_game = kwargs.get("start_game") or 0
        # # if start_game and (start_game < 0 or start_game > 90): # TODO: ???
        # #     # in my experience it never answers in these cases
        # #     raise ValueError("start_game should be between 0 and 90 inclusively.")

        futures = [
            self.ws.gc_wait_for(
                watch.GCToClientFindTopSourceTVGamesResponse, check=lambda msg: msg.start_game == start_game
            )
            for start_game in range(0, start_game + 1, 10)
        ]
        await self.ws.send_gc_message(watch.ClientToGCFindTopSourceTVGames(**kwargs))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            # each response.game_list is 10 games (except possibly last one if filtered by)
            return await asyncio.gather(*futures)

    async def fetch_dota2_profile(self, account_id: int) -> client_messages.ProfileResponse:
        """Fetch user's dota 2 profile."""
        await self.ws.send_gc_message(client_messages.ProfileRequest(account_id=account_id))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            return await self.ws.gc_wait_for(client_messages.ProfileResponse)

    async def fetch_dota2_profile_card(self, account_id: int) -> common.ProfileCard:
        """Fetch user's dota 2 profile card."""
        await self.ws.send_gc_message(client_messages.ClientToGCGetProfileCard(account_id=account_id))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            return await self.ws.gc_wait_for(common.ProfileCard, check=lambda msg: msg.account_id == account_id)

    async def fetch_match_history(
        self,
        **kwargs: Unpack[MatchHistoryKwargs],
    ):
        """Fetch match history."""
        await self.ws.send_gc_message(client_messages.GetPlayerMatchHistory(**kwargs))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            return await self.ws.gc_wait_for(client_messages.GetPlayerMatchHistoryResponse)

    async def fetch_matches_minimal(self, match_ids: list[int]) -> watch.ClientToGCMatchesMinimalResponse:
        """Fetch matches minimal."""
        await self.ws.send_gc_message(watch.ClientToGCMatchesMinimalRequest(match_ids=match_ids))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            return await self.ws.gc_wait_for(watch.ClientToGCMatchesMinimalResponse)

    async def fetch_match_details(self, match_id: int) -> client_messages.MatchDetailsResponse:
        """Fetch match details."""
        await self.ws.send_gc_message(client_messages.MatchDetailsRequest(match_id=match_id))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            response = await self.ws.gc_wait_for(
                client_messages.MatchDetailsResponse, check=lambda msg: msg.match.match_id == match_id
            )
        if response.eresult != Result.OK:
            raise WSException(response)
        return response

    async def fetch_rank(self, rank_type: client_messages.ERankType) -> client_messages.GCToClientRankResponse:
        """Fetch rank."""
        await self.ws.send_gc_message(client_messages.ClientToGCRankRequest(rank_type=rank_type))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            return await self.ws.gc_wait_for(client_messages.GCToClientRankResponse)

    async def post_social_message(
        self, **kwargs: Unpack[PostSocialMessageKwargs]
    ) -> client_messages.GCToClientSocialFeedPostMessageResponse:
        """Post social message."""
        await self.ws.send_gc_message(client_messages.ClientToGCSocialFeedPostMessageRequest(**kwargs))
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            response = await self.ws.gc_wait_for(client_messages.GCToClientSocialFeedPostMessageResponse)
        if response.success != Result.OK:
            raise WSException(response)
        return response

    async def fetch_matchmaking_stats(self) -> client_messages.MatchmakingStatsResponse:
        """Fetch matchmaking stats."""
        await self.ws.send_gc_message(client_messages.MatchmakingStatsRequest())
        async with asyncio.timeout(TIMEOUT_DEFAULT):
            return await self.ws.gc_wait_for(client_messages.MatchmakingStatsResponse)
