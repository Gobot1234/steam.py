"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import bisect
import math
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from operator import itemgetter
from typing import TYPE_CHECKING, Final, Generic, Mapping, TypeVar, cast, overload

from ... import abc, user, utils
from ..._const import timeout
from ..._gc.client import ClientUser as ClientUser_
from ...id import parse_id64
from ...types.id import ID32
from ...utils import DateTime
from ..commands.converters import Converter, UserConverter
from .enums import Rank, RankType
from .protobufs import cstrike

if TYPE_CHECKING:
    from typing import Literal

    from typing_extensions import Self

    from ...app import CSGO, App
    from ...enums import Language
    from ...trade import Inventory, Item
    from .backpack import Backpack
    from .state import GCState


UserT = TypeVar("UserT", bound=abc.PartialUser)

__all__ = (
    "Team",
    "Round",
    "Match",
    "PartialUser",
    "User",
    "ClientUser",
    "MatchPlayer",
    "ProfileInfo",
)


class MatchWatchInfo:
    ...


@dataclass(slots=True)
class Team:
    """Represents a team in a match"""

    score: int
    won: bool
    players: list[MatchPlayer]


@dataclass(slots=True)
class Round:
    """Represents a round of a match"""

    duration: timedelta
    teams: list[Team]
    map: str

    @property
    def players(self) -> list[MatchPlayer]:
        return [player for team in self.teams for player in team.players]


class Match:
    """Represents a match of CSGO"""

    def __init__(self, state: GCState, match_info: cstrike.MatchInfo, players: dict[ID32, User]) -> None:
        self._state = state
        self.id = match_info.matchid
        self.created_at = DateTime.from_timestamp(match_info.matchtime)
        # self.watch_info = MatchWatchInfo(match_info.watchablematchinfo)
        # self.type = self.watch_info.type
        # self.map_group = self.watch_info.map_group
        # self.map = self.watch_info.map
        # self.server_id = self.watch_info.server_id

        self.rounds: list[Round] = []
        for round in match_info.roundstatsall:
            player_ids = cast(list[ID32], round.reservation.account_ids)
            team_size = len(player_ids) // len(round.team_scores)
            previous_scores = [0] * len(round.team_scores)
            teams: list[Team] = []
            for idx, score in enumerate(round.team_scores):
                players_: list[MatchPlayer] = []
                for id in player_ids[(idx * team_size) : (idx + 1) * team_size]:
                    player = MatchPlayer(state, players[id])
                    idx = player_ids.index(id)
                    player.kills = round.kills[idx]
                    player.assists = round.assists[idx]
                    player.deaths = round.deaths[idx]
                    player.score = round.scores[idx]
                    player.enemy_kills = round.enemy_kills[idx]
                    player.enemy_head_shots = round.enemy_headshots[idx]
                    players_.append(player)

                won = round.team_scores[idx] > previous_scores[idx]
                if won:
                    mvp_idx, _ = max(
                        Counter(round.mvps[(idx * team_size) : (idx + 1) * team_size]).items(), key=itemgetter(1)
                    )  # can't have an even number of players right?
                    mvp = utils.get(players_, id=player_ids[mvp_idx])
                    assert mvp
                    mvp.mvp = True
                teams.append(Team(score, won, players_))
            self.rounds.append(Round(timedelta(seconds=round.match_duration), teams, round.map))

    @property
    def players(self) -> list[MatchPlayer]:
        """All the players that appeared in the match."""
        return list(dict.fromkeys(player for round in reversed(self.rounds) for player in round.players))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"


@dataclass
class Matches:
    matches: list[Match]
    streams: list[cstrike.TournamentTeam]
    tournament_info: cstrike.TournamentInfo


class PartialUser(abc.PartialUser):
    __slots__ = ()
    _state: GCState

    async def csgo_profile(self) -> ProfileInfo[Self]:
        """Fetches this users CSGO profile info."""
        msg = await self._state.fetch_user_csgo_profile(self.id)
        if not msg.account_profiles:
            raise ValueError
        return ProfileInfo(self, msg.account_profiles[0])

    async def recent_matches(self) -> Matches:
        """Fetches this user's recent games."""
        future = self._state.ws.gc_wait_for(
            cstrike.MatchList,
            check=lambda msg: (
                msg.msgrequestid == cstrike.MatchListRequestRecentUserGames.MSG and msg.accountid == self.id
            ),
        )
        await self._state.ws.send_gc_message(cstrike.MatchListRequestRecentUserGames(accountid=self.id))
        async with timeout(30):
            msg = await future

        players = {
            user.id: user
            for user in await self._state._maybe_users(
                parse_id64(id)
                for match in msg.matches
                for round in match.roundstatsall
                for id in round.reservation.account_ids
            )
        }

        return Matches([Match(self._state, match, players) for match in msg.matches], msg.streams, msg.tournamentinfo)


class User(PartialUser, user.User):  # type: ignore
    __slots__ = ()


class ClientUser(PartialUser, ClientUser_):  # type: ignore
    __slots__ = ("_profile_info_msg",)

    if TYPE_CHECKING:

        @overload
        async def inventory(self, app: Literal[CSGO], *, language: object = ...) -> Backpack:  # type: ignore
            ...

        @overload
        async def inventory(self, app: App, *, language: Language | None = None) -> Inventory[Item[Self], Self]:  # type: ignore
            ...

    async def csgo_profile(self) -> ProfileInfo[Self]:
        return ProfileInfo(self, self._profile_info_msg)

    @utils.todo
    async def live_games(self) -> ...:
        ...


class MatchPlayer(PartialUser, user.WrapsUser):  # type: ignore
    kills: int
    assists: int
    deaths: int
    score: int
    enemy_kills: int
    enemy_head_shots: int
    mvp: bool


LEVEL_MAP: Final = cast(Mapping[int, str], {
    0: "Not Recruited",
    1: "Recruit",  # 1-3
    4: "Private",  # 4-7 etc.
    8: "Corporal",
    12: "Sergeant",
    16: "Master Sergeant",
    20: "Sergeant Major",
    24: "Lieutenant",
    28: "Captain",
    32: "Major",
    35: "Colonel",
    36: "Brigadier General",
    37: "Major General",
    38: "Lieutenant General",
    39: "General",
    40: "Global General",
})  # fmt: skip


class Level(int):
    @property
    def name(self, levels: list[int] = list(LEVEL_MAP), names: list[str] = list(LEVEL_MAP.values()), /) -> str:
        return names[bisect.bisect_left(levels, self)]


class Ranking:
    __slots__ = ("rank", "id", "rank_type", "change", "wins", "tv_control")

    def __init__(self, proto: cstrike.PlayerRankingInfo) -> None:
        self.rank = Rank.try_value(proto.rank_id) if proto.rank_type_id != 10 else proto.rank_id
        self.id = proto.rank_type_id
        self.rank_type = RankType.try_value(proto.rank_type_id)
        self.change = proto.rank_change
        self.wins = proto.wins
        self.tv_control = proto.tv_control


class ProfileInfo(Generic[UserT]):
    def __init__(self, user: UserT, proto: cstrike.MatchmakingClientHello | cstrike.PlayersProfileProfile):
        self.user = user
        self.in_match = proto.ongoingmatch
        self.global_stats = proto.global_stats
        self.penalty_seconds = proto.penalty_seconds
        self.penalty_reason = proto.penalty_reason
        self.vac_banned = proto.vac_banned
        self.ranking = Ranking(proto.ranking)
        self.commendation = proto.commendation
        self.medals = proto.medals
        self.current_event = proto.my_current_event
        self.current_event_teams = proto.my_current_event_teams
        self.current_team = proto.my_current_team
        self.current_event_stages = proto.my_current_event_stages
        self.survey_vote = proto.survey_vote
        self.activity = proto.activity
        self.current_xp = proto.player_cur_xp
        self.level = Level(proto.player_level)
        self.xp_bonus_flags = proto.player_xp_bonus_flags
        self.rankings = [Ranking(ranking) for ranking in proto.rankings]

    @property
    def percentage_of_current_level(self) -> int:
        """The user's current percentage of their current level."""
        return math.floor(max(self.current_xp - 327680000, 0) / 5000)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} user={self.user!r}>"


class CSGOUserConverter(Converter[User]):
    convert = UserConverter.convert  # type: ignore
