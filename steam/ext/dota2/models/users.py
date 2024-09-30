"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from .... import abc, user
from ..enums import Hero, RankTier
from ..protobufs import client_messages, common
from . import matches

if TYPE_CHECKING:
    from ..state import GCState

UserT = TypeVar("UserT", bound=abc.PartialUser)

__all__ = (
    "ProfileCard",
    "PartialUser",
    "User",
)


class PartialUser(abc.PartialUser):
    __slots__ = ()
    _state: GCState

    async def profile_card(self) -> ProfileCard:
        """Fetch user's Dota 2 profile card.

        Contains basic information about the account. Somewhat mirrors old profile page.
        """
        await self._state.ws.send_gc_message(client_messages.ClientToGCGetProfileCard(account_id=self.id))
        response = await self._state.ws.gc_wait_for(
            common.ProfileCard,
            check=lambda msg: msg.account_id == self.id,
        )
        return ProfileCard(response)

    async def match_history(
        self,
        *,
        start_at_match_id: int = 0,
        matches_requested: int = 20,
        hero: Hero = Hero.NONE,
        include_practice_matches: bool = False,
        include_custom_games: bool = False,
        include_event_games: bool = False,
    ) -> list[matches.MatchHistoryMatch]:
        """Fetch user's Dota 2 match history.

        Only works for steam friends.
        """
        await self._state.ws.send_gc_message(
            client_messages.GetPlayerMatchHistory(
                account_id=self.id,
                start_at_match_id=start_at_match_id,
                matches_requested=matches_requested,
                hero_id=hero.value,
                include_practice_matches=include_practice_matches,
                include_custom_games=include_custom_games,
                include_event_games=include_event_games,
                # request_id=69, # but where to get it without asking for MatchHistory first
            )
        )
        response = await self._state.ws.gc_wait_for(client_messages.GetPlayerMatchHistoryResponse)
        return [matches.MatchHistoryMatch(self._state, match) for match in response.matches]


class User(PartialUser, user.User):  # type: ignore
    __slots__ = ()


class ProfileCard:
    def __init__(self, proto: common.ProfileCard):
        self.account_id = proto.account_id
        self.badge_points = proto.badge_points
        self.event_points = proto.event_points
        self.event_id = proto.event_id
        self.recent_battle_cup_victory = proto.recent_battle_cup_victory
        self.rank_tier = RankTier.try_value(proto.rank_tier)
        """Ranked medal like Herald-Immortal with a number of stars, i.e. Legend 5."""
        self.leaderboard_rank = proto.leaderboard_rank
        """Leaderboard rank, i.e. found here https://www.dota2.com/leaderboards/#europe."""
        self.is_plus_subscriber = proto.is_plus_subscriber
        """Is Dota Plus Subscriber."""
        self.plus_original_start_date = proto.plus_original_start_date
        """When user subscribed to Dota Plus for their very first time."""
        self.favorite_team_packed = proto.favorite_team_packed
        self.lifetime_games = proto.lifetime_games
        """Amount of lifetime games, includes Turbo games as well."""

        # (?) Unused/Deprecated by Valve
        # self.slots = proto.slots  # profile page was reworked
        # self.title = proto.title
        # self.rank_tier_score = proto.rank_tier_score  # relic from time when support/core MMR were separated
        # self.leaderboard_rank_core = proto.leaderboard_rank_core  # relic from time when support/core MMR were separated

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} account_id={self.account_id}>"


class LiveMatchPlayer(PartialUser):
    hero: Hero

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} hero={self.hero!r}>"
