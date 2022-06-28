"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Generic, TypeVar, overload

from typing_extensions import Literal

from . import utils
from .abc import Commentable, SteamID, _CommentableKwargs
from .enums import EventType
from .game import Game, StatefulGame
from .utils import DateTime

if TYPE_CHECKING:
    from .clan import Clan
    from .game_server import GameServer
    from .state import ConnectionState
    from .user import User

__all__ = (
    "Event",
    "Announcement",
)


ClanEventT = TypeVar("ClanEventT", bound=EventType, covariant=True)


class BaseEvent(Commentable, utils.AsyncInit, Generic[ClanEventT], metaclass=abc.ABCMeta):
    __slots__ = (
        "clan",
        "id",
        "author",
        "name",
        "content",
        "game",
        "starts_at",
        "becomes_visible",
        "stops_being_visible",
        "ends_at",
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
        author = data.get("creator_steamid")
        self.author: User | SteamID | None = int(author) if author is not None else None  # type: ignore
        edited_by = data.get("last_update_steamid")
        self.last_edited_by: User | SteamID | None = int(edited_by) if edited_by is not None else None  # type: ignore
        self.name: str = data["event_name"]
        self.content: str = data["event_notes"]
        self.game = StatefulGame(state, id=data["appid"]) if data["appid"] else None
        self.type: ClanEventT = EventType.try_value(data["event_type"])

        self.starts_at = DateTime.from_timestamp(data["rtime32_start_time"])
        becomes_visible = data.get("rtime32_visibility_start")
        self.becomes_visible = DateTime.from_timestamp(becomes_visible) if becomes_visible else None
        stops_being_visible = data.get("rtime32_visibility_end")
        self.stops_being_visible = DateTime.from_timestamp(stops_being_visible) if stops_being_visible else None
        ends_at = data.get("rtime32_end_time")
        self.ends_at = DateTime.from_timestamp(ends_at) if ends_at else None
        last_edited_at = data.get("rtime32_last_modified")
        self.last_edited_at = DateTime.from_timestamp(last_edited_at) if last_edited_at else None

        self.hidden = bool(data.get("hidden", 0))
        self.published = bool(data.get("published", 1))
        self.upvotes: int = data.get("votes_up", 0)
        self.downvotes: int = data.get("votes_down", 0)
        self.comment_count: int = data.get("comment_count", 0)
        self.server_address: str | None = data.get("server_address")
        self.server_password: str | None = data.get("server_password")

        self._feature = int(data["gidfeature"])
        self._feature2 = int(data.get("gidfeature2", 0) or 0)

    async def __ainit__(self) -> None:
        if self.last_edited_by:
            self.author, self.last_edited_by = await self._state._maybe_users((self.author, self.last_edited_by))  # type: ignore
        else:
            self.author = await self._state._maybe_user(self.author)  # type: ignore

    def __repr__(self) -> str:
        attrs = ("id", "name", "type", "author", "clan")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return self.id == other.id and self.clan == other.clan if isinstance(other, self.__class__) else NotImplemented


class Event(BaseEvent[ClanEventT]):
    """Represents an event in a clan.

    Attributes
    ----------
    id
        The event's id.
    author
        The event's author.
    name
        The event's name.
    content
        The event's content.
    game
        The game that the event is going to play in.
    clan
        The event's clan.
    starts_at
        The event's start time.
    becomes_visible
        The time at which the event becomes visible.
    stops_being_visible
        The time at which the event stops being visible.
    ends_at
        The time at which the event ends.
    type
        The event's type.
    last_edited_at
        The time the event was last edited at.
    last_edited_by
        The user who made the event last edited.
    hidden
        Whether the event is currently hidden.
    published
        Whether the event is currently published.
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
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "thread_type": 14,
            "id64": self.clan.id64,
            "gidfeature": self._feature,
        }

    async def server(self) -> GameServer | None:
        """The server that the game will be run on, ``None`` if not found.

        Note
        ----
        This is shorthand for

        .. code-block:: python3

            await client.fetch_server(ip=event.server_address)
        """

        if self.server_address == "0":
            return
        return await self._state.client.fetch_server(ip=self.server_address)

    @overload
    async def edit(
        self: Event[Literal[EventType.Game]],
        name: str,
        content: str,
        *,
        game: Game | None = None,
        starts_at: datetime | None = ...,
        server_address: str | None = ...,
        server_password: str | None = ...,
    ) -> None:
        ...

    @overload
    async def edit(
        self,
        name: str,
        content: str,
        *,
        type: Literal[
            EventType.Other,
            EventType.Chat,
            EventType.Party,
            EventType.Meeting,
            EventType.SpecialCause,
            EventType.MusicAndArts,
            EventType.Sports,
            EventType.Trip,
        ]
        | None = None,
        starts_at: datetime | None = None,
    ) -> None:
        ...

    @overload
    async def edit(
        self,
        name: str,
        content: str,
        *,
        type: Literal[EventType.Game] = ...,
        starts_at: datetime | None = ...,
        game: Game,
        server_address: str | None = ...,
        server_password: str | None = ...,
    ) -> None:
        ...

    async def edit(
        self,
        name: str,
        content: str,
        *,
        type: Literal[
            EventType.Other,
            EventType.Chat,
            EventType.Game,
            # ClanEvent.Broadcast,  # TODO need to wait until implementing stream support for this
            EventType.Party,
            EventType.Meeting,
            EventType.SpecialCause,
            EventType.MusicAndArts,
            EventType.Sports,
            EventType.Trip,
        ]
        | None = None,
        game: Game | None = None,
        starts_at: datetime | None = None,
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
        content
            The event's content.
        type
            The event's type.
        game
            The event's game.
        starts_at
            The event's start time.
        server_address
            The event's server's address.
        server_password
            The event's server's password.
        """
        type_ = type or self.type
        new_game = game or self.game
        game_id = str(new_game) if new_game is not None else None
        await self._state.http.edit_clan_event(
            self.clan.id64,
            name or self.name,
            content or self.content,
            f"{type_.name}Event",
            game_id or "",
            server_address or self.server_address if self.server_address else "",
            server_password or self.server_password if self.server_password else "",
            starts_at or self.starts_at,
            event_id=self.id,
        )
        self.name = name or self.name
        self.content = content or self.content
        self.type = type_
        self.server_address = server_address or self.server_address
        self.server_password = server_password or self.server_password
        self.game = StatefulGame(self._state, id=game_id) if game_id is not None else None
        self.last_edited_at = DateTime.now()
        self.last_edited_by = self._state.user

    async def delete(self) -> None:
        """Delete this event."""
        await self._state.http.delete_clan_event(self.clan.id64, self.id)


class Announcement(BaseEvent[EventType]):
    """Represents an announcement in a clan.

    Attributes
    ----------
    id
        The announcement's ID.
    author
        The announcement's author.
    name
        The announcement's name.
    content
        The announcement's content.
    game
        The game that the announcement is for.
    clan
        The announcement's clan.
    starts_at
        The announcement's start time.
    becomes_visible
        The time at which the announcement becomes visible.
    stops_being_visible
        The time at which the announcement stops being visible.
    ends_at
        The time at which the announcement ends.
    type
        The announcement's type.
    last_edited_at
        The time the announcement was last edited at.
    last_edited_by
        The user who made the announcement last edited.
    hidden
        Whether the announcement is currently hidden.
    published
        Whether the announcement is currently published.
    upvotes
        The number of up votes on the announcement.
    downvotes
        The number of down votes on the announcement.
    comment_count
        The number of comments on the announcement.
    topic_id
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
        "topic_id",
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
        self.id: int = int(body["gid"])
        self.topic_id = int(data["forum_topic_id"]) if data["forum_topic_id"] else None
        self.created_at = DateTime.from_timestamp(body["posttime"])
        self.updated_at = DateTime.from_timestamp(body["updatetime"])  # this is different to self.edited_at?
        self.approved_at = DateTime.from_timestamp(data["rtime_mod_reviewed"]) if data["rtime_mod_reviewed"] else None
        self.content: str = body["body"]
        self.tags: Sequence[str] = body["tags"]

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        if self.clan.is_game_clan:
            raise NotImplementedError("Fetching a game announcement's comments is not currently supported")
        return {
            "thread_type": 13,
            "id64": self.clan.id64,
            "gidfeature": self._feature,
        }

    async def edit(self, name: str | None = None, content: str | None = None) -> None:
        """Edit the announcement's details.

        Note
        ----
        If parameters are omitted they use what they are currently set to.

        Parameters
        ----------
        name
            The announcement's name.
        content
            The announcement's content.
        """
        name = name or self.name
        content = content or self.content
        await self._state.http.edit_clan_announcement(self.clan.id64, self.id, name, content)
        self.name = name
        self.content = content
        self.last_edited_at = DateTime.now()
        self.last_edited_by = self._state.user

    async def delete(self) -> None:
        """Delete this announcement."""
        await self._state.http.delete_clan_announcement(self.clan.id64, self.id)

    # async def hide(self) -> None:
    #     """Hide this announcement."""
    #     await self._state.http.hide_clan_announcement(self.clan.id, self.id, True)

    # async def unhide(self) -> None:
    #     """Un-hide this announcement."""
    #     await self._state.http.hide_clan_announcement(self.clan.id, self.id, False)

    async def upvote(self) -> None:
        """Upvote this announcement."""
        return await self._state.rate_clan_announcement(self.clan.id, self.id, True)

    async def downvote(self) -> None:
        """Downvote this announcement."""
        return await self._state.rate_clan_announcement(self.clan.id, self.id, False)
