"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, Generic, Self

from .enums import Hero
from ... import abc
from .protobufs.shared_enums import DOTAGameMode
from .protobufs.lobby import CSODOTALobbyLobbyType

if TYPE_CHECKING:
    from .protobufs.watch import CSourceTVGameSmall
    from .state import GCState
    from .protobufs.common import CMsgDOTAProfileCard

__all__ = ("LiveMatch",)

UserT = TypeVar("UserT", bound=abc.PartialUser)


@dataclass(slots=True)
class LivePlayer:
    user: PartialUser
    hero: Hero


@dataclass(slots=True)
class BattleCup:
    tournament_id: int
    division: int
    skill_level: int
    bracket_round: int


@dataclass(slots=True)
class TournamentTeam:
    id: int
    name: str
    logo: float  # todo: can I get more info on logo than float nonsense ?


@dataclass(slots=True)
class TournamentMatch:
    league_id: int
    series_id: int
    teams: list[TournamentTeam]
    battle_cup_info: BattleCup | None


class LiveMatch:
    """Represents a live match of Dota 2

    Attributes
    -----------
    match_id
        Match ID.
    server_steam_id
        Server Steam ID.
    lobby_id
        Lobby ID.
    lobby_type
        Lobby Type. i.e. Ranked, Unranked.
    game_mode
        Game mode, i.e. All Pick, Captains Mode.
    players
        List of players in this match. This is sorted with team slot order (or commonly referred as player's colour).
        Radiant team players first, i.e. "blue", "teal", "purple", ... Then Dire team players.
    average_mmr
        Average MMR.
    sort_score
        Number for in-game's Watch Tab to sort the game list in descending order with.
    spectators:
        Amount of people currently watching this match live in the Dota 2 application.
    start_time:
        Datetime in UTC for when the match started, including pre-draft stage.
    end_time:
        Datetime in UTC for when the match is finished. 0 if match is currently live.
    game_time:
        Timedelta representing in-game timer.
        Draft stage and time before runes (0:00 mark) have this as non-positive timedelta.
    delay
        Time delay for the match if watching in the Dota 2 application.
        Similarly, the data in attributes of this class is also behind the present by this delay.
    last_update_time:
        Time the data was updated last by the Game Coordinator.
    tournament
        Tournament information, if the match is a tournament game.
    radiant_lead
        Amount of gold lead Radiant team has. Negative value in case Dire is leading.
    radiant_score
        Amount of kills Radiant team has
    dire_score
        Amount of kills Dire team has
    building_state
        Bitmask. An integer that represents a binary of which buildings are still standing.
    custom_game_difficulty
        Custom Game Difficulty
    """

    def __init__(self, state: GCState, proto: CSourceTVGameSmall) -> None:
        self._state: GCState = state

        self.match_id: int = proto.match_id
        self.server_steam_id: int = proto.match_id
        self.lobby_id: int = proto.lobby_id

        self.lobby_type = CSODOTALobbyLobbyType.try_value(proto.lobby_type)
        self.game_mode = DOTAGameMode.try_value(proto.game_mode)
        self.average_mmr: int = proto.average_mmr
        self.sort_score: int = proto.sort_score
        self.spectators: int = proto.spectators

        self.start_time = datetime.datetime.fromtimestamp(proto.activate_time, datetime.timezone.utc)
        self.game_time = datetime.timedelta(seconds=proto.game_time)
        self.end_time = datetime.timedelta(seconds=proto.deactivate_time)
        self.delay = datetime.timedelta(seconds=proto.delay)
        self.last_update_time = datetime.datetime.fromtimestamp(proto.last_update_time, datetime.timezone.utc)

        self.tournament: TournamentMatch | None = None
        if proto.league_id:  # if it is 0 then all tournament related fields are going to be 0 as well
            battle_cup = None
            if proto.weekend_tourney_tournament_id:  # if it is 0 then all battle cup related fields are going to be 0
                battle_cup = BattleCup(
                    proto.weekend_tourney_tournament_id,
                    proto.weekend_tourney_division,
                    proto.weekend_tourney_skill_level,
                    proto.weekend_tourney_bracket_round,
                )
            self.tournament = TournamentMatch(
                proto.league_id,
                proto.series_id,
                [
                    TournamentTeam(proto.team_id_radiant, proto.team_name_radiant, proto.team_logo_radiant),
                    TournamentTeam(proto.team_id_dire, proto.team_name_dire, proto.team_logo_dire),
                ],
                battle_cup,
            )

        self.radiant_lead: int = proto.radiant_lead
        self.radiant_score: int = proto.radiant_score
        self.dire_score: int = proto.dire_score
        self.building_state: float = proto.building_state  # todo: helper function to decode this into human-readable

        self.custom_game_difficulty: int = proto.custom_game_difficulty

        # Since Immortal Draft update, players come from the proto message in a wrong order
        # which can be fixed back with extra fields that they introduced later: `team`, `team_slot`
        # why valve chose to introduce extra bytes fields instead of resorting it once after player selection - no clue
        sorted_players = [p for p in sorted(proto.players, key=lambda player: (player.team, player.team_slot))]

        self.players = [
            LivePlayer(
                user=PartialUser(self._state, p.account_id),
                hero=Hero.try_value(p.hero_id),
            )
            for p in sorted_players
        ]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} match_id={self.match_id} server_steam_id={self.server_steam_id}>"


class PartialUser(abc.PartialUser):
    __slots__ = ()
    _state: GCState

    async def dota2_profile_card(self) -> ProfileCard[Self]:
        """Fetches this users Dota 2 profile card."""
        msg = await self._state.fetch_user_dota2_profile_card(self.id)
        return ProfileCard(self, msg)


class ProfileCard(Generic[UserT]):
    def __init__(self, user: UserT, proto: CMsgDOTAProfileCard):
        print(proto)
        self.user = user
        self.slots = proto.slots
        self.badge_points = proto.badge_points
        self.event_points = proto.event_points
        self.event_id = proto.event_id
        self.recent_battle_cup_victory = proto.recent_battle_cup_victory
        self.rank_tier = proto.rank_tier
        self.leaderboard_rank = proto.leaderboard_rank
        self.is_plus_subscriber = proto.is_plus_subscriber
        self.plus_original_start_date = proto.plus_original_start_date
        self.rank_tier_score = proto.rank_tier_score
        self.leaderboard_rank_core = proto.leaderboard_rank_core
        self.title = proto.title
        self.favorite_team_packed = proto.favorite_team_packed
        self.lifetime_games = proto.lifetime_games

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} user={self.user!r}>"
