"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from .abc import BaseUser, Messageable, UserDict
from .enums import TradeOfferState
from .errors import ClientException, ConfirmationError
from .models import URL
from .profile import OwnedProfileItems, ProfileItem

if TYPE_CHECKING:
    from .clan import Clan
    from .game import Game
    from .group import Group
    from .image import Image
    from .message import UserMessage
    from .state import ConnectionState
    from .trade import TradeOffer


__all__ = (
    "User",
    "ClientUser",
)


class User(BaseUser, Messageable["UserMessage"]):
    """Represents a Steam user's account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name
        The user's username.
    state
        The current persona state of the account (e.g. LookingToTrade).
    game
        The Game instance attached to the user. Is ``None`` if the user isn't in a game or one that is recognised by the
        api.
    avatar_url
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name
        The user's real name defined by them. Could be ``None``.
    primary_clan
        The user's primary clan.
    created_at
        The time at which the user's account was created. Could be ``None``.
    last_logon
        The last time the user logged into steam. This is only ``None`` if user hasn't been updated from the websocket.
    last_logoff
        The last time the user logged off from steam. Could be ``None`` (e.g. if they are currently online).
    last_seen_online
        The last time the user could be seen online. This is only ``None`` if user hasn't been updated from the
        websocket.
    country
        The country code of the account. Could be ``None``.
    flags
        The persona state flags of the account.
    """

    __slots__ = ()

    async def add(self) -> None:
        """Sends a friend invite to the user to your friends list."""
        await self._state.http.add_user(self.id64)

    async def remove(self) -> None:
        """Remove the user from your friends list."""
        await self._state.http.remove_user(self.id64)
        try:
            self._state.client.user.friends.remove(self)
        except ValueError:
            pass

    async def cancel_invite(self) -> None:
        """Cancels an invite sent to the user. This effectively does the same thing as :meth:`remove`."""
        await self._state.http.remove_user(self.id64)

    async def block(self) -> None:
        """Blocks the user."""
        await self._state.http.block_user(self.id64)

    async def unblock(self) -> None:
        """Unblocks the user."""
        await self._state.http.unblock_user(self.id64)

    async def escrow(self, token: str | None = None) -> timedelta | None:
        """Check how long any received items would take to arrive. ``None`` if the user has no escrow or has a
        private inventory.

        Parameters
        ----------
        token
            The user's trade offer token, not required if you are friends with the user.
        """
        resp = await self._state.http.get_user_escrow(self.id64, token)
        their_escrow = resp["response"].get("their_escrow")
        if their_escrow is None:  # private
            return None
        seconds = their_escrow["escrow_end_duration_seconds"]
        return timedelta(seconds=seconds) if seconds else None

    def _message_func(self, content: str) -> Coroutine[Any, Any, UserMessage]:
        return self._state.send_user_message(self.id64, content)

    def _image_func(self, image: Image) -> Coroutine[Any, Any, None]:
        return self._state.http.send_user_image(self.id64, image)

    async def send(
        self,
        content: Any = None,
        *,
        trade: TradeOffer | None = None,
        image: Image | None = None,
    ) -> UserMessage | None:
        """Send a message, trade or image to an :class:`User`.

        Parameters
        ----------
        content
            The message to send to the user.
        trade
            The trade offer to send to the user.

            Note
            ----
            This will have its :attr:`~steam.TradeOffer.id` attribute updated after being sent.

        image
            The image to send to the user.

        Raises
        ------
        :exc:`~steam.HTTPException`
            Sending the message failed.
        :exc:`~steam.Forbidden`
            You do not have permission to send the message.

        Returns
        -------
        The sent message only applicable if ``content`` is passed.
        """

        message = await super().send(content, image)
        if trade is not None:
            to_send = [item.to_dict() for item in trade.items_to_send]
            to_receive = [item.to_dict() for item in trade.items_to_receive]
            resp = await self._state.http.send_trade_offer(self, to_send, to_receive, trade.token, trade.message or "")
            trade._has_been_sent = True
            needs_confirmation = resp.get("needs_mobile_confirmation", False)
            trade._update_from_send(self._state, resp, self, active=not needs_confirmation)
            if needs_confirmation:
                for tries in range(5):
                    try:
                        await trade.confirm()
                    except ConfirmationError:
                        break
                    except ClientException:
                        await asyncio.sleep(tries * 2)
                trade.state = TradeOfferState.Active

            # make sure the trade is updated before this function returns
            self._state._trades[trade.id] = trade
            self._state._trades_to_watch.add(trade.id)
            await self._state.trades_list.wait_for(trade.id)

        return message

    async def invite_to_group(self, group: Group) -> None:
        """Invites the user to a :class:`Group`.

        Parameters
        -----------
        group
            The group to invite the user to.
        """
        await self._state.invite_user_to_group(self.id64, group.id)

    async def invite_to_clan(self, clan: Clan) -> None:
        """Invites the user to a :class:`Clan`.

        Parameters
        -----------
        clan
            The clan to invite the user to.
        """
        await self._state.http.invite_user_to_clan(self.id64, clan.id64)

    async def owns(self, game: Game) -> bool:
        """Whether or not the game is owned by this user.

        Parameters
        ----------
        game
            The game you want to check the ownership of.
        """
        return self.id64 in await self._state.fetch_friends_who_own(game.id)

    def is_friend(self) -> bool:
        """Whether or not the user is in the :class:`ClientUser`'s friends."""
        return self in self._state.client.user.friends


class ClientUser(BaseUser):
    """Represents your account.

    .. container:: operations

        .. describe:: x == y

            Checks if two users are equal.

        .. describe:: str(x)

            Returns the user's name.

    Attributes
    ----------
    name
        The user's username.
    friends
        A list of the :class:`ClientUser`'s friends.
    state
        The current persona state of the account (e.g. LookingToTrade).
    game
        The Game instance attached to the user. Is ``None`` if the user isn't in a game or one that is recognised by
        the api.
    avatar_url
        The avatar url of the user. Uses the large (184x184 px) image url.
    real_name
        The user's real name defined by them. Could be ``None``.
    primary_clan
        The user's primary clan. Could be ``None``
    created_at
        The time at which the user's account was created. Could be ``None``.
    last_logon
        The last time the user logged into steam. This is only ``None`` if user hasn't been updated from the websocket.
    last_logoff
        The last time the user logged off from steam. Could be ``None`` (e.g. if they are currently online).
    last_seen_online
        The last time the user could be seen online. This is only ``None`` if user hasn't been updated from the
        websocket.
    country
        The country code of the account. Could be ``None``.
    flags
        The persona state flags of the account.
    """

    # TODO more stuff to add https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/profile.js

    __slots__ = ("friends",)

    def __init__(self, state: ConnectionState, data: UserDict):
        super().__init__(state, data)
        self.friends: list[User] = []

    async def setup_profile(self) -> None:
        """Set up your profile if possible."""
        if self.has_setup_profile():
            return

        params = {"welcomed": 1}
        await self._state.http.get(URL.COMMUNITY / "my/edit", params=params)

    async def clear_nicks(self) -> None:
        """Clears the client user's nickname/alias history."""
        await self._state.http.clear_nickname_history()

    async def profile_items(self) -> OwnedProfileItems:
        """Fetch all of the client user's profile items."""
        items = await self._state.fetch_profile_items()
        return OwnedProfileItems(
            backgrounds=[
                ProfileItem(self._state, background, um_name="ProfileBackground")
                for background in items.profile_backgrounds
            ],
            mini_profile_backgrounds=[
                ProfileItem(self._state, mini_profile_background, um_name="MiniProfileBackground")
                for mini_profile_background in items.mini_profile_backgrounds
            ],
            avatar_frames=[
                ProfileItem(self._state, avatar_frame, um_name="AvatarFrame") for avatar_frame in items.avatar_frames
            ],
            animated_avatars=[
                ProfileItem(self._state, animated_avatar, um_name="AnimatedAvatar")
                for animated_avatar in items.animated_avatars
            ],
            modifiers=[ProfileItem(self._state, modifier) for modifier in items.profile_modifiers],
        )

    async def edit(
        self,
        *,
        name: str | None = None,
        real_name: str | None = None,
        url: str | None = None,
        summary: str | None = None,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        avatar: Image | None = None,
    ) -> None:
        """Edit the client user's profile. Any values that aren't set will use their defaults.

        Parameters
        ----------
        name
            The new name you wish to go by.
        real_name
            The real name you wish to go by.
        url
            The custom url ending/path you wish to use.
        summary
            The summary/description you wish to use.
        country
            The country you want to be from.
        state
            The state you want to be from.
        city
            The city you want to be from.
        avatar
            The avatar you wish to use.

            Note
            ----
            This needs to be at least 184px x 184px.

        Raises
        -------
        :exc:`~steam.HTTPException`
            Editing your profile failed.
        """
        await self._state.http.edit_profile(name, real_name, url, summary, country, state, city, avatar)
