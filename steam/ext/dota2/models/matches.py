"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import datetime
from asyncio import timeout
from dataclasses import dataclass
from operator import attrgetter
from typing import TYPE_CHECKING

from ....utils import DateTime
from ..enums import GameMode, Hero, LobbyType, Outcome
from ..protobufs import client_messages, common, watch
from . import users

if TYPE_CHECKING:
    from ..protobufs import common, watch
    from ..state import GCState

__all__ = (
    "LiveMatch",
    "MatchMinimal",
    "PartialMatch",
)


class PartialMatch:
    """Represents an already finished Dota 2 Match.

    This class allows using Dota 2 Coordinator requests related to matches.
    """

    def __init__(self, state: GCState, id: int):
        self._state = state
        self.id = id

    async def details(self) -> MatchDetails | None:
        """Fetch Match Details.

        Contains most of the information that can be found in post-match stats in-game.

        Raises
        ------
        asyncio.TimeoutError
            Request time-outed. Potential reasons:
                * Match ID is incorrect.
                * This match is still live.
                * Dota 2 Game Coordinator lagging or being down.
        """
        await self._state.ws.send_gc_message(client_messages.MatchDetailsRequest(match_id=self.id))
        async with timeout(15.0):
            response = await self._state.ws.gc_wait_for(
                client_messages.MatchDetailsResponse,
                check=lambda msg: msg.match.match_id == self.id,
            )
        if response.eresult == 1:
            return MatchDetails(self._state, response.match)
        else:
            msg = f"Failed to get match_details for {self.id}"
            raise ValueError(msg)

    async def minimal(self) -> MatchMinimal:
        """Fetches basic "minimal" information about the match."""
        proto = await self._state.fetch_matches_minimal(match_ids=[self.id])
        match = next(iter(proto.matches), None)
        if match is not None:
            return MatchMinimal(self._state, match)
        else:
            msg = f"Failed to get match_minimal for {self.id}"
            raise ValueError(msg)


class MatchMinimalPlayer:
    def __init__(self, state: GCState, proto: common.MatchMinimalPlayer):
        self._state = state

        self.id = proto.account_id
        self.hero = Hero.try_value(proto.hero_id)
        self.kills = proto.kills
        self.deaths = proto.deaths
        self.assists = proto.assists
        self.items = proto.items
        self.player_slot = proto.player_slot
        self.pro_name = proto.pro_name
        self.level = proto.level
        self.team_number = proto.team_number


class MatchMinimal:
    def __init__(self, state: GCState, proto: common.MatchMinimal) -> None:
        self._state = state

        self.id = proto.match_id
        self.start_time = DateTime.from_timestamp(proto.start_time)
        self.duration = datetime.timedelta(seconds=proto.duration)
        self.game_mode = GameMode.try_value(proto.game_mode)
        self.players = [MatchMinimalPlayer(state, player) for player in proto.players]
        self.tourney = proto.tourney  # TODO: modelize further `common.MatchMinimalTourney`
        self.outcome = Outcome.try_value(proto.match_outcome)
        self.radiant_score = proto.radiant_score
        self.dire_score = proto.dire_score
        self.lobby_type = LobbyType.try_value(proto.lobby_type)


class MatchDetails:
    def __init__(self, state: GCState, proto: common.Match) -> None:
        self._state = state

        self.id = proto.match_id
        self.duration = datetime.timedelta(seconds=proto.duration)
        self.start_time = DateTime.from_timestamp(proto.starttime)
        self.human_players_amount = proto.human_players
        self.players = proto.players  # TODO: modelize
        self.tower_status = proto.tower_status  # TODO: decipher
        self.barracks_status = proto.barracks_status  # TODO: decipher
        self.cluster = proto.cluster
        self.first_blood_time = proto.first_blood_time
        self.replay_salt = proto.replay_salt
        self.server_port = proto.server_port
        self.lobby_type = LobbyType.try_value(proto.lobby_type)
        self.server_ip = proto.server_ip
        self.average_skill = proto.average_skill
        self.game_balance = proto.game_balance
        self.radiant_team_id = proto.radiant_team_id
        self.dire_team_id = proto.dire_team_id
        self.league_id = proto.leagueid
        self.radiant_team_name = proto.radiant_team_name
        self.dire_team_name = proto.dire_team_name
        self.radiant_team_logo = proto.radiant_team_logo
        self.dire_team_logo = proto.dire_team_logo
        self.radiant_team_logo_url = proto.radiant_team_logo_url
        self.dire_team_logo_url = proto.dire_team_logo_url
        self.radiant_team_complete = proto.radiant_team_complete
        self.dire_team_complete = proto.dire_team_complete
        self.game_mode = GameMode.try_value(proto.game_mode)
        self.picks_bans = proto.picks_bans  # TODO: modelize
        self.match_seq_num = proto.match_seq_num
        self.replay_state = proto.replay_state
        self.radiant_guild_id = proto.radiant_guild_id
        self.dire_guild_id = proto.dire_guild_id
        self.radiant_team_tag = proto.radiant_team_tag
        self.dire_team_tag: str = proto.dire_team_tag
        self.series_id = proto.series_id
        self.series_type = proto.series_type
        self.broadcaster_channels = proto.broadcaster_channels  # TODO: modelize
        self.engine = proto.engine
        self.custom_game_data = proto.custom_game_data  # TODO: ???
        self.match_flags = proto.match_flags  # TODO: ???
        self.private_metadata_key = proto.private_metadata_key  # TODO: ???
        self.radiant_team_score = proto.radiant_team_score
        self.dire_team_score = proto.dire_team_score
        self.match_outcome = Outcome.try_value(proto.match_outcome)
        self.tournament_id = proto.tournament_id
        self.tournament_round = proto.tournament_round
        self.pre_game_duration = proto.pre_game_duration
        self.coaches = proto.coaches  # TODO: modelize


class LiveMatch:
    """Represents a live match of Dota 2

    Attributes
    -----------
    id
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
        Includes information about tournament teams.
    battle_cup
        Battle Cup information, if the match is a battle cup game.
        Includes information about tournament teams.
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

    def __init__(self, state: GCState, proto: watch.SourceTVGameSmall) -> None:
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

        self.tournament = (
            TournamentMatch(
                proto.league_id,
                proto.series_id,
                (
                    TournamentTeam(proto.team_id_radiant, proto.team_name_radiant, proto.team_logo_radiant),
                    TournamentTeam(proto.team_id_dire, proto.team_name_dire, proto.team_logo_dire),
                ),
            )
            if proto.league_id  # if it is 0 then all tournament related fields are going to be 0 as well
            else None
        )
        self.battle_cup = (
            BattleCup(
                proto.weekend_tourney_tournament_id,
                proto.weekend_tourney_division,
                proto.weekend_tourney_skill_level,
                proto.weekend_tourney_bracket_round,
                (
                    TournamentTeam(proto.team_id_radiant, proto.team_name_radiant, proto.team_logo_radiant),
                    TournamentTeam(proto.team_id_dire, proto.team_name_dire, proto.team_logo_dire),
                ),
            )
            if proto.weekend_tourney_tournament_id  # if it is 0 then all battle cup related fields are going to be 0
            else None
        )

        self.radiant_lead = proto.radiant_lead
        self.radiant_score = proto.radiant_score
        self.dire_score = proto.dire_score
        self.building_state = proto.building_state  # TODO: helper function to decode this into human-readable

        self.custom_game_difficulty = proto.custom_game_difficulty

        # Since Immortal Draft update, players come from the proto message in a wrong order
        # which can be fixed back with extra fields that they introduced later: `team`, `team_slot`
        # why valve chose to introduce extra bytes fields instead of resorting it once after player selection - no clue
        sorted_players = sorted(proto.players, key=attrgetter("team", "team_slot"))

        self.players: list[users.LiveMatchPlayer] = []
        for player in sorted_players:
            live_match_player = users.LiveMatchPlayer(self._state, player.account_id)
            live_match_player.hero = Hero.try_value(player.hero_id)
            self.players.append(live_match_player)

    @property
    def heroes(self) -> list[Hero]:
        """List of heroes in the match. The list is sorted by their player's colour."""
        return [p.hero for p in self.players]

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} server_steam_id={self.server_steam_id}>"


@dataclass(slots=True)
class TournamentMatch:  # should this be named LiveTournamentMatch ? Idk how fast I gonna break all these namings,
    league_id: int  # TODO: can I get more info like name of the tournament
    series_id: int
    teams: tuple[TournamentTeam, TournamentTeam]


@dataclass(slots=True)
class TournamentTeam:
    id: int
    name: str
    logo: float  # TODO: can I get more info on logo than float nonsense ?


@dataclass(slots=True)
class BattleCup:
    tournament_id: int
    division: int
    skill_level: int
    bracket_round: int
    teams: tuple[TournamentTeam, TournamentTeam]


# maybe name it Match History Record
class MatchHistoryMatch(PartialMatch):
    def __init__(self, state: GCState, proto: client_messages.GetPlayerMatchHistoryResponseMatch) -> None:
        super().__init__(state, proto.match_id)

        self.start_time = DateTime.from_timestamp(proto.start_time)
        self.hero = Hero.try_value(proto.hero_id)
        self.win = proto.winner
        self.game_mode = GameMode.try_value(proto.game_mode)
        self.lobby_type = LobbyType.try_value(proto.lobby_type)
        self.abandon = proto.abandon
        self.duration = datetime.timedelta(seconds=proto.duration)
        self.active_plus_subscription = proto.active_plus_subscription

        self.tourney_id = proto.tourney_id
        self.tourney_round = proto.tourney_round
        self.tourney_tier = proto.tourney_tier
        self.tourney_division = proto.tourney_division
        self.team_id = proto.team_id
        self.team_name = proto.team_name
        self.ugc_team_ui_logo = proto.ugc_team_ui_logo

        # Deprecated / Pointless (?)
        # self.previous_rank = proto.previous_rank
        # self.solo_rank = proto.solo_rank  # always False
        # self.rank_change = proto.rank_change
        # self.seasonal_rank = proto.seasonal_rank  # always False
        # self.engine = proto.engine  # always 1

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} hero={self.hero} win={self.win}>"
