"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Generic, TypeVar, overload

from typing_extensions import Literal, Self

from ... import abc, user
from ..._gc.client import ClientUser as ClientUser_
from ...app import CSGO, App
from ...types.id import ID32
from ...utils import DateTime
from ..commands.converters import Converter, UserConverter
from .protobufs import cstrike

if TYPE_CHECKING:
    from ...enums import Language
    from ...trade import Inventory, Item
    from .backpack import Backpack
    from .state import GCState


UserT = TypeVar("UserT", bound=abc.PartialUser)

__all__ = (
    "PartialUser",
    "User",
    "ClientUser",
    "ProfileInfo",
)


class MatchWatchInfo:
    ...


@dataclass(slots=True)
class Team:
    score: int
    players: list[MatchPlayer]


@dataclass(slots=True)
class Round:
    duration: timedelta
    teams: list[Team]
    map: str

    @property
    def players(self) -> list[MatchPlayer]:
        return list(itertools.chain.from_iterable([team.players for team in self.teams]))


class MatchInfo:
    def __init__(self, state: GCState, match_info: cstrike.MatchInfo, players: dict[ID32, User]) -> None:
        self._state = state
        self.id = match_info.matchid
        self.created_at = DateTime.from_timestamp(match_info.matchtime)
        # self.watch_info = MatchWatchInfo(match_info.watchablematchinfo)
        # self.type = self.watch_info.type
        # self.map_group = self.watch_info.map_group
        # self.map = self.watch_info.map
        # self.server_id = self.watch_info.server_id

        # self.rounds = [
        #     Round(
        #         timedelta(seconds=round.match_duration),
        #     )
        #     for round in match_info.roundstatsall
        # ]
        self.rounds = match_info.roundstatsall
        self.players = [MatchPlayer(state, user) for user in players.values()]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"


@dataclass
class Matches:
    matches: list[MatchInfo]
    streams: list["cstrike.TournamentTeam"]
    tournament_info: "cstrike.TournamentInfo"


class PartialUser(abc.PartialUser):
    __slots__ = ()
    _state: GCState

    async def csgo_profile(self) -> ProfileInfo[Self]:
        msg = await self._state.fetch_user_csgo_profile(self.id)
        if not msg.account_profiles:
            raise ValueError
        return ProfileInfo(self, msg.account_profiles[0])


class User(PartialUser, user.User):
    __slots__ = ()

    async def recent_matches(self) -> Matches:
        future = self._state.ws.gc_wait_for(
            cstrike.MatchList,
            check=lambda msg: (
                msg.msgrequestid == cstrike.MatchListRequestRecentUserGames.MSG and msg.accountid == self.id
            ),
        )
        await self._state.ws.send_gc_message(cstrike.MatchListRequestRecentUserGames(accountid=self.id))
        msg = await future

        return Matches([MatchInfo(self._state, match) for match in msg.matches], msg.streams, msg.tournamentinfo)


class ClientUser(PartialUser, ClientUser_):
    __slots__ = ("_profile_info_msg",)

    if TYPE_CHECKING:

        @overload
        async def inventory(self, app: Literal[CSGO], *, language: object = ...) -> Backpack:  # type: ignore
            ...

        @overload
        async def inventory(self, app: App, *, language: Language | None = None) -> Inventory[Item[Self], Self]:
            ...

    async def csgo_profile(self) -> ProfileInfo[Self]:
        return ProfileInfo(self, self._profile_info_msg)

    async def live_games(self) -> ...:
        ...


class MatchPlayer(PartialUser, user.WrapsUser):
    kills: int
    assists: int
    deaths: int
    scores: int
    enemy_kills: int
    enemy_headshots: int
    mvps: int


class ProfileInfo(Generic[UserT]):
    def __init__(self, user: UserT, proto: cstrike.MatchmakingClientHello | cstrike.PlayersProfileProfile):
        self.user = user
        self.in_match = proto.ongoingmatch
        self.global_stats = proto.global_stats
        self.penalty_seconds = proto.penalty_seconds
        self.penalty_reason = proto.penalty_reason
        self.vac_banned = proto.vac_banned
        self.ranking = proto.ranking
        self.commendation = proto.commendation
        self.medals = proto.medals
        self.current_event = proto.my_current_event
        self.current_event_teams = proto.my_current_event_teams
        self.current_team = proto.my_current_team
        self.current_event_stages = proto.my_current_event_stages
        self.survey_vote = proto.survey_vote
        self.activity = proto.activity
        self.current_xp = proto.player_cur_xp
        self.level = proto.player_level
        self.xp_bonus_flags = proto.player_xp_bonus_flags
        self.rankings = proto.rankings

    @property
    def percentage_of_current_level(self) -> int:
        """The user's current percentage of their current level."""
        return math.floor(max(self.current_xp - 327680000, 0) / 5000)

    def __repr__(self) -> str:
        return f"<ProfileInfo user={self.user!r}>"


class CSGOUserConverter(Converter[User]):
    convert = UserConverter.convert  # type: ignore
