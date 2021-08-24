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

import abc
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from . import utils
from .abc import Commentable, SteamID
from .enums import ClanEvent
from .game import Game, StatefulGame

if TYPE_CHECKING:
    from .clan import Clan
    from .game_server import GameServer
    from .state import ConnectionState
    from .user import User

__all__ = (
    "Event",
    "Announcement",
)


def utc_from_timestamp(time: int) -> datetime:
    return datetime.fromtimestamp(time, tz=timezone.utc)


class BaseEvent(Commentable, utils.AsyncInit, metaclass=abc.ABCMeta):
    __slots__ = (
        "clan",
        "id",
        "author",
        "name",
        "description",
        "game",
        "start",
        "becomes_visible",
        "stops_being_visible",
        "end",
        "type",
        "last_edited_at",
        "last_edited_by",
        "hidden",
        "published",
        "upvotes",
        "downvotes",
        "comment_count",
        "server_address",
        "server_password",
        "_state",
    )

    # data here is of type steammessages_base.CClanEventData.to_dict()
    # TODO keep checking if there is a way to get CClanEventData directly from ws
    def __init__(self, state: ConnectionState, clan: Clan, data: dict[str, Any]):
        self._state = state
        self.clan = clan
        self.id: int = int(data["gid"])
        self.author: User | SteamID | None = int(data["creator_steamid"])  # type: ignore
        self.name: str = data["event_name"]
        self.description: str = data["event_notes"]
        self.game = StatefulGame(state, id=data["appid"]) if data["appid"] else None
        self.start = utc_from_timestamp(data["rtime32_start_time"])
        self.becomes_visible = (
            utc_from_timestamp(data["rtime32_visibility_start"]) if data.get("rtime32_visibility_start") else None
        )
        self.stops_being_visible = (
            utc_from_timestamp(data["rtime32_visibility_end"]) if data.get("rtime32_visibility_end") else None
        )
        self.end = utc_from_timestamp(data["rtime32_end_time"]) if data["rtime32_end_time"] else None
        self.type = ClanEvent.try_value(data["event_type"])
        self.last_edited_at = utc_from_timestamp(data["rtime32_last_modified"])
        self.last_edited_by: User | SteamID | None = (  # type: ignore
            int(data["last_update_steamid"]) if (data["last_update_steamid"] or "0") != "0" else None
        )
        self.hidden = bool(data.get("hidden", 0))
        self.published = bool(data.get("published", 1))
        self.upvotes: int = data.get("votes_up", 0)
        self.downvotes: int = data.get("votes_down", 0)
        self.comment_count: int = data.get("comment_count", 0)
        self.server_address: str | None = data["server_address"]
        self.server_password: str | None = data["server_password"]

    async def __ainit__(self) -> None:
        self.author = await self._state._maybe_user(self.author)
        if self.last_edited_by:
            self.last_edited_by = await self._state._maybe_user(self.last_edited_by)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} name={self.name!r} author={self.author!r} clan={self.clan!r}>"


class Event(BaseEvent):
    """Represents an event in a clan.

    Attributes
    ----------
    id
        The event's id.
    author
        The event's author.
    name
        The event's name.
    description
        The event's description.
    game
        The game the event is going to play in.
    clan
        The event's clan.
    start
        The event's start time.
    becomes_visible
        The time at which the event becomes visible.
    stops_being_visible
        The time at which the event stops being visible.
    end
        The time at which the event ends.
    type
        The event's type.
    last_edited_at
        The time the event was last edited at.
    last_edited_by
        The the user who made the event last edited.
    hidden
        Whether or not the event is currently hidden.
    published
        Whether or not the event is currently published.
    upvotes
        The number of up votes on the event.
    downvotes
        The number of down votes on the event.
    comment_count
        The number of comments on the event.
    server_address
        The event's server address.
    server_password
        The event's server password.
    """

    server_address: str
    server_password: str

    @property
    def _commentable_kwargs(self) -> dict[str, Any]:
        return {
            "thread_type": 14,
            "id64": self.clan.id64,
            "gidfeature": self.id,
        }

    async def server(self) -> GameServer | None:
        """The server that the game will be ran on, ``None`` if not found.

        Note
        ----
        This is shorthand for

        .. code-block:: python3

            await client.fetch_server(ip=event.server_address)
        """

        if self.server_address == "0":
            return
        return await self._state.client.fetch_server(ip=self.server_address)

    async def edit(
        self,
        name: str | None = None,
        description: str | None = None,
        type: Literal[
            ClanEvent.Chat,
            ClanEvent.Game,
            ClanEvent.Broadcast,
            ClanEvent.Other,
            ClanEvent.Party,
            ClanEvent.Meeting,
            ClanEvent.SpecialCause,
            ClanEvent.MusicAndArts,
            ClanEvent.Sports,
            ClanEvent.Trip,
        ]
        | None = None,
        game: Game | int | None = None,
        start: datetime | None = None,
        server_address: str | None = None,
        server_password: str | None = None,
    ) -> None:
        """Edit the event's details.

        Note
        ----
        If parameters are omitted they use what they are currently set to.

        Parameters
        ----------
        name
            The event's name.
        description
            The event's description.
        type
            The event's type.
        game
            The event's game.
        start
            The event's start time.
        server_address
            The event's server's address.
        server_password
            The event's server's password.
        """
        type = type or self.type
        game_id = str(getattr(game or self.game, "id", game))
        await self._state.http.edit_clan_event(
            self.clan.id64,
            name or self.name,
            description or self.description,
            f"{type.name}Event",
            game_id or "",
            server_address or self.server_address if self.server_address else "",
            server_password or self.server_password if self.server_password else "",
            start or self.start,
            event_id=self.id,
        )
        self.name = name or self.name
        self.description = description or self.description
        self.type = type or self.type
        self.server_address = server_address or self.server_address
        self.server_password = server_password or self.server_password
        self.game = StatefulGame(self._state, id=game_id)
        self.last_edited_at = datetime.utcnow()
        self.last_edited_by = self._state.client.user

    async def delete(self) -> None:
        await self._state.http.delete_clan_event(self.clan.id64, self.id)


@dataclass
class Forum(Commentable):
    announcement: Announcement
    clan: Clan
    id: int
    gidfeature2: int

    @property
    def _commentable_kwargs(self) -> dict[str, Any]:
        return {
            "thread_type": 7,
            "id64": self.clan.id64 if self.clan is not None else 0,
            "thread_id": self.id,
            "gidfeature": self.announcement.id,
            "gidfeature2": self.gidfeature2,
        }


class Announcement(BaseEvent):
    """Represents an announcement in a clan.

    Attributes
    ----------
    id
        The announcement's id.
    author
        The announcement's author.
    name
        The announcement's name.
    description
        The announcement's description.
    game
        The game the announcement is for.
    clan
        The announcement's clan.
    start
        The announcement's start time.
    becomes_visible
        The time at which the announcement becomes visible.
    stops_being_visible
        The time at which the announcement stops being visible.
    end
        The time at which the announcement ends.
    type
        The announcement's type.
    last_edited_at
        The time the announcement was last edited at.
    last_edited_by
        The the user who made the announcement last edited.
    hidden
        Whether or not the announcement is currently hidden.
    published
        Whether or not the announcement is currently published.
    upvotes
        The number of up votes on the announcement.
    downvotes
        The number of down votes on the announcement.
    comment_count
        The number of comments on the announcement.
    forum_id
        The id of the forum post comments are sent to.
    created_at
        The time at which the announcement was created at.
    updated_at
        The time at which the announcement was last updated_at.
    approved_at
        The time at which the announcement was approved by a moderator.
    tags
        The announcement's tags.
    """

    __slots__ = (
        "forum_id",
        "created_at",
        "updated_at",
        "approved_at",
        "tags",
    )
    approved_by: User
    server_ip: None
    server_password: None

    def __init__(self, state: ConnectionState, clan: Clan, data: dict[str, Any]):
        super().__init__(state, clan, data)
        body: dict[str, Any] = data["announcement_body"]
        self.forum_id = int(data["forum_topic_id"]) or None
        self.created_at = utc_from_timestamp(body["posttime"])
        self.updated_at = utc_from_timestamp(body["updatetime"])  # this is different to self.edited_at?
        self.approved_at = utc_from_timestamp(data["rtime_mod_reviewed"]) if data["rtime_mod_reviewed"] else None
        self.description: str = body["body"]
        self.tags: Sequence[str] = body["tags"]

    @property
    def _commentable_kwargs(self) -> dict[str, Any]:
        if self.clan.is_game_clan:
            raise NotImplementedError("you need to use Announcement.forum to get an announcement's comments")
        return {
            "thread_type": 13,
            "id64": self.clan.id64,
            "gidfeature": self.id,
        }

    async def edit(self, name: str | None = None, description: str | None = None) -> None:
        """Edit the announcement's details.

        Note
        ----
        If parameters are omitted they use what they are currently set to.

        Parameters
        ----------
        name
            The announcement's name.
        description
            The announcement's description.
        """
        await self._state.http.edit_clan_announcement(self.clan.id64, self.id, name, description)
        self.name = name
        self.description = description
        self.last_edited_at = datetime.utcnow()
        self.last_edited_by = self._state.client.user

    # TODO
    """
    async def forum(self) -> Forum:
        # permissions = await self._state.http.get()
        # text = await self._state.http.get(f"{self.clan.game.url}/eventcomments/{self.forum_id}")
        # soup = BeautifulSoup(text, "html.parser")
        ...
        
    async def permissions(self) -> ...:
        ...
        
    async def hide(self) -> None:
        ...
        
    async def unhide(self) -> None:
        ...

    # use protos for these
    async def upvote(self) -> None:
        ...

    async def downvote(self) -> None:
        ...
    """
