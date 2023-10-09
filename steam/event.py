"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Generic, Literal, cast, overload

from typing_extensions import TypeVar

from . import utils
from .abc import Commentable, PartialUser, _CommentableKwargs
from .app import App, PartialApp
from .enums import EventType
from .id import ID_ZERO
from .utils import DateTime

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from .clan import BoringEvents, Clan, CreateableEvents, PartialClan
    from .game_server import GameServer
    from .state import ConnectionState
    from .types import clan
    from .types.http import IPAdress
    from .user import User

__all__ = (
    "Event",
    "Announcement",
)


EventTypeT = TypeVar("EventTypeT", bound=EventType, default=EventType, covariant=True)
ClanT = TypeVar("ClanT", bound="PartialClan", default="Clan", covariant=True)


class BaseEvent(Commentable, utils.AsyncInit, Generic[EventTypeT, ClanT], metaclass=abc.ABCMeta):
    __slots__ = (
        "clan",
        "id",
        "author",
        "name",
        "content",
        "app",
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
        "_feature",
        "_feature2",
        "_state",
    )

    # data here is of type steammessages_base.CClanEventData.to_dict()
    # TODO keep checking if there is a way to get CClanEventData directly from ws
    def __init__(self, state: ConnectionState, clan: ClanT, data: clan.Event):
        self._state = state
        self.id: int = int(data["gid"])
        """The event's ID."""
        self.name: str = data["event_name"]
        """The event's name."""
        self.author: User | PartialUser = PartialUser(state, data["creator_steamid"])
        """The event's author."""
        self.content: str = data["event_notes"]
        """The event's description."""
        self.app = PartialApp(state, id=data["appid"]) if data["appid"] else None
        """The app that the event is going to be played in."""
        self.type = cast(EventTypeT, EventType.try_value(data["event_type"]))
        """The event's type."""
        self.clan = clan
        """The event's clan."""

        self.starts_at = DateTime.from_timestamp(data["rtime32_start_time"])
        """The event's start time."""
        becomes_visible = data.get("rtime32_visibility_start")
        self.becomes_visible = DateTime.from_timestamp(becomes_visible) if becomes_visible else None
        """The time at which the event becomes publicly visible."""
        stops_being_visible = data.get("rtime32_visibility_end")
        self.stops_being_visible = DateTime.from_timestamp(stops_being_visible) if stops_being_visible else None
        """The time at which the event stops being publicly visible."""
        ends_at = data.get("rtime32_end_time")
        self.ends_at = DateTime.from_timestamp(ends_at) if ends_at else None
        """The time at which the event ends."""

        last_edited_at = data.get("rtime32_last_modified")
        self.last_edited_at = DateTime.from_timestamp(last_edited_at) if last_edited_at else None
        """The time the event was last edited at."""
        edited_by = data.get("last_update_steamid")
        self.last_edited_by: User | PartialUser | None = (
            state.get_partial_user(edited_by) if edited_by is not None else None
        )
        """The user last edited the event."""

        self.hidden = bool(data.get("hidden", 0))
        """Whether the event is currently hidden."""
        self.published = bool(data.get("published", 1))
        """Whether the event is currently published."""
        self.upvotes: int = data.get("votes_up", 0)
        """The number of up votes on the event."""
        self.downvotes: int = data.get("votes_down", 0)
        """The number of down votes on the event."""
        self.comment_count: int = data.get("comment_count", 0)
        """The number of comments on the event."""

        self._feature = int(data["gidfeature"])
        self._feature2 = int(data.get("gidfeature2", 0) or 0)

    async def __ainit__(self) -> None:  # TODO can we get clan members?
        if self.last_edited_by and self.last_edited_by != ID_ZERO:
            self.author, self.last_edited_by = await self._state._maybe_users(
                (self.author.id64, self.last_edited_by.id64)
            )
        else:
            self.author = await self._state._maybe_user(self.author.id64)
            self.last_edited_by = None

    def __repr__(self) -> str:
        attrs = ("id", "name", "type", "author", "clan")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self.id == other.id and self.clan == other.clan

    def __hash__(self) -> int:
        return hash((self.id, self.clan))


class Event(BaseEvent[EventTypeT, ClanT]):
    """Represents an event in a clan."""

    __slots__ = (
        "server_address",
        "server_password",
    )

    def __init__(self, state: ConnectionState, clan: ClanT, data: clan.Event):
        super().__init__(state, clan, data)
        server_address = data.get("server_address")
        self.server_address: IPv4Address | None = IPv4Address(server_address) if server_address else None
        """The event's server address."""
        self.server_password: str | None = data.get("server_password")
        """The event's server password."""

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.clan.id64,
            "forum_id": self._feature,
        }

    async def server(self) -> GameServer:
        """The server that the event will be ran on.

        Note
        ----
        This is shorthand for

        .. code:: python

            await client.fetch_server(ip=event.server_address)
        """

        if self.server_address is None:
            raise ValueError("Event has no server address")
        server = await self._state.client.fetch_server(ip=self.server_address)
        assert server is not None
        return server

    @overload
    async def edit(
        self: Event[Literal[EventType.Game]],
        name: str,
        content: str,
        *,
        app: App | None = None,
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
        type: BoringEvents | None = None,
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
        app: App,
        server_address: IPAdress | str | None = ...,
        server_password: str | None = ...,
    ) -> None:
        ...

    async def edit(
        self,
        name: str,
        content: str,
        *,
        type: CreateableEvents | None = None,
        app: App | None = None,
        starts_at: datetime | None = None,
        server_address: IPAdress | str | None = None,
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
            The event's description.
        type
            The event's type.
        app
            The event's app.
        starts_at
            The event's start time.
        server_address
            The event's server's address.
        server_password
            The event's server's password.
        """
        type_ = type or self.type
        new_app = app or self.app
        app_id = str(new_app) if new_app is not None else None
        try:
            ip_address_ = IPv4Address(server_address)
        except ValueError:
            ip_address_ = None
        server_address = ip_address_ if server_address is not None else self.server_address or ""

        await self._state.http.edit_clan_event(
            self.clan.id64,
            name or self.name,
            content or self.content,
            f"{type_.name}Event",
            app_id or "",
            str(server_address),
            server_password or self.server_password if self.server_password else "",
            starts_at or self.starts_at,
            event_id=self.id,
        )
        self.name = name or self.name
        self.content = content or self.content
        self.type = type_
        self.server_address = server_address or None
        self.server_password = server_password or self.server_password
        self.app = new_app
        self.last_edited_at = DateTime.now()
        self.last_edited_by = self._state.user

    async def delete(self) -> None:
        """Delete this event."""
        await self._state.http.delete_clan_event(self.clan.id64, self.id)


class Announcement(BaseEvent[EventType, ClanT]):
    """Represents an announcement in a clan."""

    __slots__ = (
        "topic_id",
        "created_at",
        "updated_at",
        "approved_at",
        "tags",
    )
    # approved_by: User

    def __init__(self, state: ConnectionState, clan: ClanT, data: clan.Event):
        super().__init__(state, clan, data)
        body = data["announcement_body"]
        self.id: int = int(body["gid"])
        self.topic_id = int(data["forum_topic_id"]) if data["forum_topic_id"] else None
        """The ID of the forum post comments are sent to."""
        self.created_at = DateTime.from_timestamp(body["posttime"])
        """The time at which the announcement was created at."""
        self.updated_at = DateTime.from_timestamp(body["updatetime"])  # this is different to self.edited_at?
        """The time at which the announcement was last updated_at."""
        self.approved_at = DateTime.from_timestamp(data["rtime_mod_reviewed"]) if data["rtime_mod_reviewed"] else None
        """The time at which the announcement was approved by a moderator."""
        self.content: str = body["body"]
        self.tags: Sequence[str] = body["tags"]
        """The announcement's tags."""

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        from .clan import Clan  # noqa: F811

        if isinstance(self.clan, Clan) and self.clan.is_ogg():
            raise NotImplementedError("Fetching an app announcement's comments is not currently supported")
        return {
            "id64": self.clan.id64,
            "forum_id": self._feature,
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

    # async def topic(self) -> Topic:
    #     """Fetch the forum topic for this announcement."""
    #     topic = await self.clan.fetch_topic(self.topic_id)
    #     assert topic
    #     return topic
