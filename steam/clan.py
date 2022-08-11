"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import re
import warnings
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, TypeVar, overload

from bs4 import BeautifulSoup
from typing_extensions import Literal, Self

from . import utils
from ._const import HTML_PARSER
from .abc import Commentable, SteamID, _CommentableKwargs
from .channel import ClanChannel
from .chat import ChatGroup, Member
from .enums import EventType, Language, Type
from .errors import HTTPException
from .event import Announcement, Event
from .game import Game, StatefulGame
from .iterators import AnnouncementsIterator, EventIterator
from .protobufs import chat
from .utils import DateTime

if TYPE_CHECKING:
    from .state import ConnectionState
    from .types.id import ID32
    from .user import User

__all__ = ("Clan", "ClanMember")

BoringEventT = TypeVar(
    "BoringEventT",
    Literal[EventType.Other],
    Literal[EventType.Chat],
    Literal[EventType.Party],
    Literal[EventType.Meeting],
    Literal[EventType.SpecialCause],
    Literal[EventType.MusicAndArts],
    Literal[EventType.Sports],
    Literal[EventType.Trip],
    covariant=True,
)


class ClanMember(Member):
    group: None
    clan: Clan

    def __init__(self, state: ConnectionState, clan: Clan, user: User, proto: chat.Member):
        super().__init__(state, clan, user, proto)
        self.clan = clan


class Clan(ChatGroup[ClanMember, ClanChannel], Commentable, utils.AsyncInit):
    """Represents a Steam clan.

    .. container:: operations

        .. describe:: x == y

            Checks if two clans are equal.

        .. describe:: str(x)

            Returns the clan's name.

    Attributes
    ------------
    name
        The name of the clan.
    avatar_url
        The icon url of the clan. Uses the large (184x184 px) image url.
    content
        The content of the clan.
    tagline
        The clan's tagline.
    member_count
        The amount of users in the clan.
    online_count
        The amount of users currently online.
    active_member_count
        The amount of currently users in the clan's chat room.
    in_game_count
        The amount of user's currently in game.
    created_at
        The time the clan was created_at.
    language
        The language set for the clan.
    location
        The location set for the clan.
    game
        The clan's associated game.
    owner
        The clan's owner.
    admins
        A list of the clan's administrators.
    mods
        A list of the clan's moderators.
    """

    __slots__ = (
        "content",
        "created_at",
        "language",
        "location",
        "member_count",
        "in_game_count",
        "online_count",
        "admins",
        "mods",
        "community_url",
        "is_game_clan",
    )

    # TODO more to implement https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/groups.js
    # Clan.requesting_membership
    # Clan.respond_to_requesting_membership(*users, approve)
    # Clan.respond_to_all_requesting_membership(approve)

    # V1
    # Clan.headline
    # Clan.summary
    # Clan.flags https://cs.github.com/SteamDatabase/SteamTracking/blob/5c4420496f18384bea932f4535ee1a87fd9271e4/Structs/enums.steamd#L526
    # or more likely https://cs.github.com/SteamDatabase/SteamTracking/blob/5c4420496f18384bea932f4535ee1a87fd9271e4/Structs/enums.steamd#L3177

    content: str
    created_at: datetime | None
    member_count: int
    online_count: int
    in_game_count: int
    language: Language
    location: str
    mods: list[ClanMember]
    admins: list[ClanMember]
    is_game_clan: bool

    def __init__(self, state: ConnectionState, id: int):
        super().__init__(id, type=Type.Clan)
        self._state = state

    async def __ainit__(self) -> None:
        resp = await self._state.http._session.get(super().community_url)  # type: ignore
        text = await resp.text()  # technically we loose proper request handling here
        if not self.id64:
            search = utils.CLAN_ID64_FROM_URL_REGEX.search(text)
            if search is None:
                raise ValueError("unreachable code reached")
            super().__init__(search["steamid"], type=Type.Clan)

        soup = BeautifulSoup(text, HTML_PARSER)
        _, __, name = soup.title.text.rpartition(" :: ")
        self.name = name
        content = soup.find("meta", property="og:description")
        self.content = content["content"] if content is not None else None
        icon_url = soup.find("link", rel="image_src")
        self.avatar_url = icon_url["href"] if icon_url else None
        self.is_game_clan = "games" in resp.url.parts
        self.community_url = str(resp.url)
        if self.is_game_clan:
            for entry in soup.find_all("div", class_="actionItem"):
                a = entry.a
                if a is not None:
                    href = a.get("href", "")
                    match = re.findall(r"store.steampowered.com/app/(\d+)", href)
                    if match:
                        self.game = StatefulGame(self._state, id=match[0])
        stats = soup.find("div", class_="grouppage_resp_stats")
        if stats is None:
            return

        for stat in stats.find_all("div", class_="groupstat"):
            if "Founded" in stat.text:
                text = stat.text.split("Founded")[1].strip()
                if ", " not in stat.text:
                    text = f"{text}, {DateTime.now().year}"
                self.created_at = utils.DateTime.parse_steam_date(text)
            if "Language" in stat.text:
                self.language = stat.text.split("Language")[1].strip()
            if "Location" in stat.text:
                self.location = stat.text.split("Location")[1].strip()

        for count in stats.find_all("div", class_="membercount"):
            if "MEMBERS" in count.text:
                self.member_count = int(count.text.split("MEMBERS")[0].strip().replace(",", ""))
            if "IN-GAME" in count.text:
                self.in_game_count = int(count.text.split("IN-GAME")[0].strip().replace(",", ""))
            if "ONLINE" in count.text:
                self.online_count = int(count.text.split("ONLINE")[0].strip().replace(",", ""))

        admins = []
        mods = []
        is_admins = None
        for fields in soup.find_all("div", class_="membergrid"):
            for field in fields.find_all("div"):
                if "Administrators" in field.text:
                    is_admins = True
                    continue
                if "Moderators" in field.text:
                    is_admins = False
                    continue
                if "Members" in field.text:
                    break

                try:
                    account_id = int(field["data-miniprofile"])
                except KeyError:
                    continue
                else:
                    if is_admins is None:
                        continue
                    if is_admins:
                        admins.append(account_id)
                    else:
                        mods.append(account_id)

        users = await self._state.client.fetch_users(*admins, *mods)
        self.admins = [user for user in users if user and user.id in admins]
        self.mods = [user for user in users if user and user.id in mods]

    @classmethod
    async def _from_proto(
        cls,
        state: ConnectionState,
        proto: chat.GetChatRoomGroupSummaryResponse,
        *,
        maybe_chunk: bool = True,
    ) -> Self:
        self = await super()._from_proto(state, proto, id=proto.clanid, maybe_chunk=maybe_chunk)
        return await self

    # TODO properties for admins and mods when chunked?

    async def chunk(self) -> Sequence[ClanMember]:
        self._members = dict.fromkeys(self._partial_members)  # type: ignore
        if len(self._partial_members) <= 100:
            # TODO might be if self.flags & ClanFlags.Large (2)?
            for id, member in self._partial_members.items():
                user = self._state.get_user(id)
                if user is None:
                    await asyncio.sleep(0)
                    user = await self._state._maybe_user(utils.make_id64(id))  # TODO maybe users
                member = ClanMember(self._state, self, user, member)
                self._members[member.id] = member
            return await super().chunk()

        # these actually need fetching
        view_id = self._state.chat_group_to_view_id[self._id]
        users: dict[ID32, User] = {
            user.id: user
            for users in await asyncio.gather(
                *(
                    self._state.request_chat_group_members(
                        self._id,
                        view_id,
                        client_change_number + 1,  # steam doesn't send responses if they're 0
                        start + 1,
                        stop,
                    )
                    for client_change_number, (start, stop) in enumerate(
                        utils._int_chunks(len(self._partial_members), 100)
                    )
                )
            )
            for user in users
        }
        for id, member in self._partial_members.items():
            try:
                user = users[id]
            except KeyError:
                # steam doesn't include the first user cause ???, this however, isn't that big a deal.
                user = await self._state._maybe_user(utils.make_id64(id))
                if isinstance(user, SteamID):
                    continue
            member = ClanMember(self._state, self, users[id], member)
            self._members[member.id] = member

        return await super().chunk()

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.id64,
            "thread_type": 12,
        }

    async def fetch_members(self) -> list[SteamID]:
        """Fetches a clan's member list.

        Note
        ----
        This can be a very slow operation due to the rate limits on this endpoint.
        """

        async def getter(i: int) -> BeautifulSoup:
            try:
                resp = await self._state.http.get(
                    f"{self.community_url}/members", params={"p": i + 1, "content_only": "true"}
                )
            except HTTPException:
                await asyncio.sleep(20)
                return await getter(i)
            else:
                soup = BeautifulSoup(resp, HTML_PARSER)
                for s in soup.find_all("div", id="memberList"):
                    for user in s.find_all("div", class_="member_block"):
                        ret.append(SteamID(user["data-miniprofile"]))

                return soup

        ret: list[SteamID] = []
        soup = await getter(0)
        number_of_pages = int(re.findall(r"\d* - (\d*)", soup.find("div", class_="group_paging").text)[0])
        await asyncio.gather(*(getter(i) for i in range(1, number_of_pages)))
        return ret

    @property
    def description(self) -> str:
        """An alias to :attr:`content`.

        .. deprecated:: 0.8.0

            Use :attr:`content` instead.
        """
        warnings.warn("Clan.description is deprecated, use Clan.content instead", DeprecationWarning, stacklevel=2)
        return self.content

    @property
    def icon_url(self) -> str:
        """An alias to :attr:`avatar_url`.

        .. deprecated:: 0.8.0

            Use :attr:`avatar_url` instead.
        """
        warnings.warn("Clan.icon_url is deprecated, use Clan.avatar_url instead", DeprecationWarning, stacklevel=2)
        return self.avatar_url

    async def join(self, *, invite_code: str | None = None) -> None:
        """Joins the clan."""
        await self._state.http.join_clan(self.id64)
        await super().join(invite_code=invite_code)

    async def leave(self) -> None:
        """Leaves the clan."""
        await super().leave()
        await self._state.http.leave_clan(self.id64)

    # event/announcement stuff

    async def fetch_event(self, id: int) -> Event[EventType]:
        """Fetch an event from its ID.

        Parameters
        ----------
        id
            The ID of the event.
        """
        data = await self._state.http.get_clan_events(self.id, [id])
        events = data["events"]
        if not events:
            raise ValueError(f"Event {id} not found")
        return await Event(self._state, self, events[0])

    async def fetch_announcement(self, id: int) -> Announcement:
        """Fetch an announcement from its ID.

        Parameters
        ----------
        id
            The ID of the announcement.
        """
        data = await self._state.http.get_clan_announcement(self.id, id)
        announcement = data["events"][0]
        return await Announcement(self._state, self, announcement)

    def events(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> EventIterator:
        """An :class:`~steam.iterators.AsyncIterator` over a clan's :class:`steam.Event`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for event in clan.events(limit=10):
                print(event.author, "made an event", event.name, "starting at", event.starts_at)

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of events to search through. Default is ``100``. Setting this to ``None`` will fetch all
            the clan's events, but this will be a very slow operation.
        before
            A time to search for events before.
        after
            A time to search for events after.

        Yields
        ---------
        :class:`~steam.Event`
        """
        return EventIterator(self, self._state, limit, before, after)

    def announcements(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AnnouncementsIterator:
        """An :class:`~steam.iterators.AsyncIterator` over a clan's :class:`steam.Announcement`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for announcement in clan.announcements(limit=10):
                print(
                    announcement.author,
                    "made an announcement",
                    announcement.name,
                    "at",
                    announcement.created_at,
                )

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of announcements to search through. Default is ``100``. Setting this to ``None`` will
            fetch all of the clan's announcements, but this will be a very slow operation.
        before
            A time to search for announcements before.
        after
            A time to search for announcements after.

        Yields
        ---------
        :class:`~steam.Announcement`
        """
        return AnnouncementsIterator(self, self._state, limit, before, after)

    @overload
    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: Literal[EventType.Game] = ...,
        starts_at: datetime | None = ...,
        game: Game,
        server_address: str | None = ...,
        server_password: str | None = ...,
    ) -> Event[Literal[EventType.Game]]:
        ...

    @overload
    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: BoringEventT = EventType.Other,
        starts_at: datetime | None = None,
    ) -> Event[BoringEventT]:
        ...

    async def create_event(
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
        ] = EventType.Other,
        game: Game | None = None,
        starts_at: datetime | None = None,
        server_address: str | None = None,
        server_password: str | None = None,
    ) -> Event[EventType]:
        """Create an event.

        Parameters
        ----------
        name
            The name of the event
        content
            The content for the event.
        type
            The type of the event, defaults to :attr:`ClanEvent.Other`.
        game
            The game that will be played in the event. Required if type is :attr:`ClanEvent.Game`.
        starts_at
            The time the event will start at.
        server_address
            The address of the server that the event will be played on. This is only allowed if ``type`` is
            :attr:`ClanEvent.Game`.
        server_password
            The password for the server that the event will be played on. This is only allowed if ``type`` is
            :attr:`ClanEvent.Game`.

        Note
        ----
        It is recommended to use a timezone aware datetime for ``start``.

        Returns
        -------
        The created event.
        """

        resp = await self._state.http.create_clan_event(
            self.id64,
            name,
            content,
            f"{type.name}Event",
            str(game.id) if game is not None else "",
            server_address or "",
            server_password or "",
            starts_at,
        )
        soup = BeautifulSoup(resp, HTML_PARSER)
        for element in soup.find_all("div", class_="eventBlockTitle"):
            a = element.a
            if a is not None and a.text == name:  # this is bad?
                _, __, id = a["href"].rpartition("/")
                event = await self.fetch_event(int(id))
                self._state.dispatch("event_create", event)
                return event
        raise ValueError

    async def create_announcement(
        self,
        name: str,
        content: str,
        hidden: bool = False,
    ) -> Announcement:
        """Create an announcement.

        Parameters
        ----------
        name
            The name of the announcement.
        content
            The content of the announcement.
        hidden
            Whether the announcement should initially be hidden.

        Returns
        -------
        The created announcement.
        """
        await self._state.http.create_clan_announcement(self.id64, name, content, hidden)
        resp = await self._state.http.get(f"{self.community_url}/announcements", params={"content_only": "true"})
        soup = BeautifulSoup(resp, HTML_PARSER)
        for element in soup.find_all("div", class_="announcement"):
            a = element.a
            if a is not None and a.text == name:  # this is bad?
                _, __, id = a["href"].rpartition("/")
                announcement = await self.fetch_announcement(int(id))
                self._state.dispatch("announcement_create", announcement)
                return announcement

        raise ValueError
