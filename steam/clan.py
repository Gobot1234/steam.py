"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import itertools
import re
from collections.abc import AsyncGenerator, Sequence
from datetime import date, datetime, timezone
from ipaddress import IPv4Address
from operator import itemgetter
from typing import TYPE_CHECKING, Literal, TypeVar, overload

from bs4 import BeautifulSoup
from typing_extensions import Self
from yarl import URL

from . import utils
from ._const import HTML_PARSER, UNIX_EPOCH
from .abc import Commentable, _CommentableKwargs
from .app import App, PartialApp
from .channel import ClanChannel
from .chat import ChatGroup, Member
from .enums import EventType, Language, Type
from .errors import HTTPException
from .event import Announcement, Event
from .id import CLAN_ID64_FROM_URL_REGEX, ID, parse_id64
from .protobufs import chat
from .types.id import ID32, ID64
from .utils import DateTime

if TYPE_CHECKING:
    from .state import ConnectionState
    from .types.http import IPAdress
    from .user import User

__all__ = ("Clan", "ClanMember")

BoringEvents = Literal[
    EventType.Other,
    EventType.Chat,
    EventType.Party,
    EventType.Meeting,
    EventType.SpecialCause,
    EventType.MusicAndArts,
    EventType.Sports,
    EventType.Trip,
]
CreateableEvents = Literal[BoringEvents, EventType.Game]

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
    app
        The clan's associated app.
    owner
        The clan's owner.
    admins
        A list of the clan's administrators.
    mods
        A list of the clan's moderators.
    """

    __slots__ = (
        "summary",
        "created_at",
        "language",
        "location",
        "member_count",
        "in_game_count",
        "online_count",
        "admins",
        "mods",
        "community_url",
        "is_app_clan",
    )

    # TODO more to implement https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/groups.js
    # Clan.requesting_membership
    # Clan.respond_to_requesting_membership(*users, approve)
    # Clan.respond_to_all_requesting_membership(approve)

    # V1
    # Clan.headline
    # Clan.flags https://cs.github.com/SteamDatabase/SteamTracking/blob/5c4420496f18384bea932f4535ee1a87fd9271e4/Structs/enums.steamd#L526
    # or more likely https://cs.github.com/SteamDatabase/SteamTracking/blob/5c4420496f18384bea932f4535ee1a87fd9271e4/Structs/enums.steamd#L3177

    summary: str
    created_at: datetime | None
    member_count: int
    online_count: int
    in_game_count: int
    language: Language
    location: str
    mods: list[ClanMember]
    admins: list[ClanMember]
    is_app_clan: bool

    def __init__(self, state: ConnectionState, id: int):
        super().__init__(state, id, type=Type.Clan)
        self._state = state

    async def __ainit__(self) -> None:
        resp = await self._state.http._session.get(super().community_url)  # type: ignore
        text = await resp.text()  # technically we loose proper request handling here
        if not self.id64:
            search = CLAN_ID64_FROM_URL_REGEX.search(text)
            if search is None:
                raise ValueError("unreachable code reached")
            super().__init__(self._state, search["steamid"], type=Type.Clan)

        soup = BeautifulSoup(text, HTML_PARSER)
        if not hasattr(self, "name"):
            _, _, self.name = soup.title.text.rpartition(" :: ")
        content = soup.find("meta", property="og:description")
        self.summary = content["content"] if content is not None else None
        if not hasattr(self, "_avatar_sha"):
            icon_url = soup.find("link", rel="image_src")
            url = URL(icon_url["href"]) if icon_url else None
            if url:
                self._avatar_sha = bytes.fromhex(url.path.removesuffix("/").removesuffix("_full.jpg"))
        self.is_app_clan = "games" in resp.url.parts

        if self.is_app_clan:
            for entry in soup.find_all("div", class_="actionItem"):
                if (a := entry.a) is not None:
                    href = a.get("href", "")
                    if match := re.findall(r"store.steampowered.com/app/(\d+)", href):
                        self.app = PartialApp(self._state, id=match[0])
        stats = soup.find("div", class_="grouppage_resp_stats")
        if stats is None:
            return

        for stat in stats.find_all("div", class_="groupstat"):
            if "Founded" in stat.text:
                text = stat.text.split("Founded")[1].strip()
                if ", " not in stat.text:
                    text = f"{text}, {DateTime.now().year}"
                self.created_at = DateTime.parse_steam_date(text)
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
        self = await super()._from_proto(state, proto, id=ID32(proto.clanid), maybe_chunk=maybe_chunk)
        return await self

    # TODO properties for admins and mods when chunked?

    async def chunk(self) -> Sequence[ClanMember]:
        if self.chunked:
            return self.members

        self._members = dict.fromkeys(self._partial_members)  # type: ignore
        if len(self._partial_members) <= 100:
            # TODO might be if self.flags & ClanFlags.Large (2)?
            for user, member in zip(
                await self._state._maybe_users(parse_id64(id, type=Type.Individual) for id in self._partial_members),
                self._partial_members.values(),
            ):
                self._members[user.id] = ClanMember(self._state, self, user, member)

            return await super().chunk()

        # these actually need fetching
        view_id = self._state.chat_group_to_view_id[self._id]
        users: dict[ID32, User] = {
            user.id: user
            for users in await asyncio.gather(
                *(
                    self._state.fetch_chat_group_members(
                        self._id,
                        view_id,
                        client_change_number
                        + 1,  # steam doesn't send responses if they're 0 (TODO this might be a betterproto bug)
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
                user = await self._state._maybe_user(parse_id64(id))
                if type(user) is ID:
                    continue
            self._members[user.id] = ClanMember(self._state, self, user, member)  # type: ignore  # pyright being daft
        return await super().chunk()

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.id64,
        }

    async def fetch_members(self) -> list[ID]:
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
                ret.extend(
                    ID(user["data-miniprofile"])
                    for s in soup.find_all("div", id="memberList")
                    for user in s.find_all("div", class_="member_block")
                )
                return soup

        ret: list[ID] = []
        soup = await getter(0)
        number_of_pages = int(re.findall(r"\d* - (\d*)", soup.find("div", class_="group_paging").text)[0])
        await asyncio.gather(*(getter(i) for i in range(1, number_of_pages)))
        return ret

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
        if events := data["events"]:
            return await Event(self._state, self, events[0])

        raise ValueError(f"Event {id} not found")

    async def fetch_announcement(self, id: int) -> Announcement:
        """Fetch an announcement from its ID.

        Parameters
        ----------
        id
            The ID of the announcement.
        """
        data = await self._state.http.get_clan_announcement(self.id, id)
        return await Announcement(self._state, self, data["event"])

    async def events(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[Event[EventType], None]:
        """An :term:`async iterator` over a clan's :class:`steam.Event`\\s.

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

            Warning
            -------
            If this is ``None`` and :attr:`created_at` is ``None``, this has to fetch events all the way back until 2007

        Yields
        ---------
        :class:`~steam.Event`
        """

        after = after or self.created_at or datetime(2007, 7, 1, tzinfo=timezone.utc)
        # uh-oh I really hope you have a created_at cause I have no way of telling if this request is done
        # date from https://www.ign.com/articles/2007/08/06/steam-community-beta-opens (public release of steamcommunity)
        before = before or DateTime.now()
        start_at_month = after.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stop_at_month = after.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        dates: list[date] = []
        start_month = start_at_month.month
        stop_month = 13

        for year in range(start_at_month.year, stop_at_month.year + 1):
            if year == stop_at_month.year:
                stop_month = stop_at_month.month + 1
            dates.extend(date(year, month, 1) for month in range(start_month, stop_month))
            start_month = 1

        ids: list[int] = []
        for date_chunk in utils.as_chunks(dates, 12):
            for xml in await asyncio.gather(
                *(self._state.http.get_clan_events_for(self.id64, date) for date in date_chunk)
            ):
                soup = BeautifulSoup(xml, HTML_PARSER)
                ids.extend(
                    int(url.rpartition("/")[2])
                    for event_title in soup.find_all("div", class_="eventBlockTitle")
                    for url in event_title.a.get("href")
                    if url
                )

        yielded = 0

        for id_chunk in utils.as_chunks(ids, 15):
            events: list[Event[EventType]] = []
            for event in ids:
                resp = await self._state.http.get_clan_events(self.id, id_chunk)
                data = resp["events"]
                for event_ in data:
                    event = Event(self._state, self, event_)
                    if not after < event.starts_at < before:
                        break
                    events.append(event)

            authors = utils.as_chunks(
                await self._state._maybe_users(
                    itertools.chain.from_iterable(
                        (
                            e.author.id64,
                            e.last_edited_by.id64 if e.last_edited_by is not None else ID64(0),
                        )
                        for e in events
                    )
                ),
                2,
            )
            for event in events:
                if limit is not None and yielded >= limit:
                    return
                event.author, event.last_edited_by = next(authors)
                yield event
                yielded += 1

    async def announcements(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
        # hidden: bool = False,
    ) -> AsyncGenerator[Announcement, None]:
        """An :term:`async iterator` over a clan's :class:`steam.Announcement`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for announcement in clan.announcements(limit=10):
                print(announcement.author, "made an announcement", announcement.name, "at", announcement.created_at)

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
        rss = await self._state.http.get_clan_rss(
            self.id64
        )  # TODO make this use the calendar? does that work for announcements
        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        soup = BeautifulSoup(rss, HTML_PARSER)

        ids: list[int] = []
        for url in soup.find_all("guid"):
            if match := re.findall(r"announcements/detail/(\d+)", url.text):
                ids.append(int(match[0]))

        if not ids:
            return

        announcements: list[Announcement] = []
        for announcement_ in itertools.chain.from_iterable(
            map(
                itemgetter("event"),
                await asyncio.gather(*(self._state.http.get_clan_announcement(self.id, id) for id in ids)),
            )
        ):
            announcement = Announcement(self._state, self, announcement_)
            if not after < announcement.starts_at < before:
                break
            announcements.append(announcement)

        for yielded, (announcement, (author, last_edited_by)) in enumerate(
            zip(
                announcements,
                utils.as_chunks(
                    await self._state._maybe_users(
                        itertools.chain.from_iterable(
                            (
                                a.author.id64,
                                a.last_edited_by.id64 if a.last_edited_by is not None else ID64(0),
                            )
                            for a in announcements
                        )
                    ),
                    2,
                ),
            )
        ):
            if limit is not None and yielded >= limit:
                return
            announcement.author = author
            announcement.last_edited_by = last_edited_by if last_edited_by.id != 0 else None
            yield announcement

    @overload
    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: Literal[EventType.Game] = ...,
        starts_at: datetime | None = ...,
        app: App,
        server_address: IPAdress | str | None = ...,
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
            # EventType.Broadcast,  # TODO need to wait until implementing stream support for this
            EventType.Party,
            EventType.Meeting,
            EventType.SpecialCause,
            EventType.MusicAndArts,
            EventType.Sports,
            EventType.Trip,
        ] = EventType.Other,
        app: App | None = None,
        starts_at: datetime | None = None,
        server_address: IPAdress | str | None = None,
        server_password: str | None = None,
    ) -> Event[CreateableEvents]:
        """Create an event.

        Parameters
        ----------
        name
            The name of the event
        content
            The content for the event.
        type
            The type of the event, defaults to :attr:`EventType.Other`.
        app
            The app that will be played in the event. Required if type is :attr:`EventType.Game`.
        starts_at
            The time the event will start at.
        server_address
            The address of the server that the event will be played on. This is only allowed if ``type`` is
            :attr:`EventType.App`.
        server_password
            The password for the server that the event will be played on. This is only allowed if ``type`` is
            :attr:`EventType.App`.

        Note
        ----
        It is recommended to use a timezone aware datetime for ``start``.

        Returns
        -------
        The created event.
        """
        server_address = IPv4Address(server_address) if server_address is not None else ""

        resp = await self._state.http.create_clan_event(
            self.id64,
            name,
            content,
            f"{type.name}Event",
            str(app.id) if app is not None else "",
            str(server_address),
            server_password or "",
            starts_at,
        )
        soup = BeautifulSoup(resp, HTML_PARSER)
        for element in soup.find_all("div", class_="eventBlockTitle"):
            a = element.a
            if a is not None and a.text == name:  # this is bad?
                _, _, id = a["href"].rpartition("/")
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
                _, _, id = a["href"].rpartition("/")
                announcement = await self.fetch_announcement(int(id))
                self._state.dispatch("announcement_create", announcement)
                return announcement

        raise ValueError
