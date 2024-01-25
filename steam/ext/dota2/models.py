"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from operator import attrgetter
from typing import TYPE_CHECKING, Generic, Self, TypeVar

from ... import abc, user
from ...utils import DateTime
from .enums import GameMode, Hero, LobbyType

if TYPE_CHECKING:
    from .protobufs import common, watch
    from .state import GCState

__all__ = (
    "BattleCup",
    "TournamentTeam",
    "TournamentMatch",
    "LiveMatch",
    "LiveMatchPlayer",
    "PartialUser",
    "User",
    "ProfileCard",
)

UserT = TypeVar("UserT", bound=abc.PartialUser)


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
class TournamentMatch:  # should this be named LiveTournamentMatch ? Idk how fast I gonna break all these namings,
    league_id: int  # todo: can I get more info like name of the tournament
    series_id: int
    teams: tuple[TournamentTeam, TournamentTeam]
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

    def __init__(self, state: GCState, proto: watch.CSourceTVGameSmall) -> None:
        self._state = state

        self.id = proto.match_id
        self.server_steam_id = proto.server_steam_id
        self.lobby_id = proto.lobby_id

        self.lobby_type = LobbyType.try_value(proto.lobby_type)
        self.game_mode = GameMode.try_value(proto.game_mode)
        self.average_mmr = proto.average_mmr
        self.sort_score = proto.sort_score
        self.spectators = proto.spectators

        self.start_time = DateTime.from_timestamp(proto.activate_time)
        self.game_time = datetime.timedelta(seconds=proto.game_time)
        self.end_time = datetime.timedelta(seconds=proto.deactivate_time)
        self.delay = datetime.timedelta(seconds=proto.delay)
        self.last_update_time = DateTime.from_timestamp(proto.last_update_time)

        self.tournament: TournamentMatch | None = None
        if proto.league_id:  # if it is 0 then all tournament related fields are going to be 0 as well
            battle_cup = None
            # todo: check if battle cup has league_id, otherwise we need to separate tournament from battle_cup
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
                (
                    TournamentTeam(proto.team_id_radiant, proto.team_name_radiant, proto.team_logo_radiant),
                    TournamentTeam(proto.team_id_dire, proto.team_name_dire, proto.team_logo_dire),
                ),
                battle_cup,
            )

        self.radiant_lead = proto.radiant_lead
        self.radiant_score = proto.radiant_score
        self.dire_score = proto.dire_score
        self.building_state = proto.building_state  # todo: helper function to decode this into human-readable

        self.custom_game_difficulty = proto.custom_game_difficulty

        # Since Immortal Draft update, players come from the proto message in a wrong order
        # which can be fixed back with extra fields that they introduced later: `team`, `team_slot`
        # why valve chose to introduce extra bytes fields instead of resorting it once after player selection - no clue
        sorted_players = sorted(proto.players, key=attrgetter("team", "team_slot"))

        self.players: list[LiveMatchPlayer] = []
        for player in sorted_players:
            live_match_player = LiveMatchPlayer(self._state, player.account_id)
            live_match_player.hero = Hero.try_value(player.hero_id)
            self.players.append(live_match_player)

    @property
    def heroes(self) -> list[Hero]:
        """List of heroes in the match. The list is sorted by their player's colour."""
        return [p.hero for p in self.players]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} server_steam_id={self.server_steam_id}>"


class PartialUser(abc.PartialUser):
    __slots__ = ()
    _state: GCState

    async def dota2_profile_card(self) -> ProfileCard[Self]:
        """Fetches this users Dota 2 profile card."""
        msg = await self._state.fetch_user_dota2_profile_card(self.id)
        return ProfileCard(self, msg)


class User(PartialUser, user.User):  # type: ignore
    __slots__ = ()


class LiveMatchPlayer(PartialUser):
    hero: Hero

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} hero={self.hero!r}>"


class ProfileCard(Generic[UserT]):
    def __init__(self, user: UserT, proto: common.ProfileCard):
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
