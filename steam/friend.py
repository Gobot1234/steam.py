"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from typing_extensions import Literal

from .enums import Language
from .profile import FriendProfile
from .user import ClientUser, WrapsUser

if TYPE_CHECKING:
    from .clan import Clan
    from .game import Game
    from .group import Group

__all__ = ("Friend",)


class Friend(WrapsUser):
    """Represents a friend of the :class:`ClientUser`."""

    __slots__ = ()

    profile_info = ClientUser.profile_info

    async def profile(self, *, language: Language | None = None) -> FriendProfile:
        return FriendProfile(
            *await asyncio.gather(
                self.equipped_profile_items(language=language),
                self.profile_info(),
                self.profile_customisation_info(language=language),
            )
        )

    async def owns(self, game: Game) -> bool:
        """Whether the game is owned by this friend.

        Parameters
        ----------
        game
            The game you want to check the ownership of.
        """
        return self.id64 in await self._state.fetch_friends_who_own(game.id)

    async def invite_to_group(self, group: Group) -> None:
        """Invites the user to a :class:`Group`.

        Parameters
        -----------
        group
            The group to invite the user to.
        """
        await self._state.invite_user_to_chat_group(self.id64, group.id)

    async def invite_to_clan(self, clan: Clan) -> None:
        """Invites the user to a :class:`Clan`.

        Parameters
        -----------
        clan
            The clan to invite the user to.
        """
        await self._state.http.invite_user_to_clan(self.id64, clan.id64)

    if TYPE_CHECKING:
        is_friend: Callable[[], Literal[True]]
