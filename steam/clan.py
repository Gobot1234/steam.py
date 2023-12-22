"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import itertools
import re
from datetime import date, datetime, timezone
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Iterable, Literal, TypeVar, cast, overload

from bs4 import BeautifulSoup, Tag
from typing_extensions import Self
from yarl import URL

from . import utils
from ._const import HTML_PARSER, UNIX_EPOCH
from .abc import Commentable, PartialUser, _CommentableKwargs, _CommentThreadType
from .app import App, PartialApp
from .channel import ClanChannel
from .chat import ChatGroup, Member, PartialMember
from .enums import ClanAccountFlags, EventType, Language, Type, UserNewsType
from .event import Announcement, Event
from .id import ID, parse_id64
from .protobufs import chat
from .types.id import ID32, ID64, Intable
from .utils import BBCodeStr, DateTime, parse_bb_code

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from .media import Media
    from .state import ConnectionState
    from .types.http import IPAdress
    from .user import User

__all__ = (
    "Clan",
    "ClanMember",
)

BoringEvents = Literal[
    EventType.Other,
    EventType.Chat,
    EventType.Party,
    EventType.Meeting,
    EventType.SpecialCause,
    EventType.MusicAndArts,
    EventType.Sports,
    EventType.Trip,
    # EventType.Broadcast,  # TODO need to wait until implementing stream support for this
]
CreateableEvents = BoringEvents | Literal[EventType.Game]

BoringEventT = TypeVar("BoringEventT", bound=BoringEvents)


class ClanMember(Member["Clan", None]):
    def __init__(self, state: ConnectionState, clan: Clan, user: User, proto: chat.Member):
        super().__init__(state, clan, user, proto)
        self.clan = clan


class PartialClan(ID[Literal[Type.Clan]], Commentable):
    def __init__(self, state: ConnectionState, id: Intable):
        super().__init__(id, type=Type.Clan)
        self._state = state

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.id64,
        }

    @utils.classproperty
    def _COMMENTABLE_TYPE(cls: type[Self]) -> _CommentThreadType:  # type: ignore
        return _CommentThreadType.Clan

    async def edit(
        self,
        *,
        abbreviation: str | None = None,
        headline: str | None = None,
        summary: str | None = None,
        community_url: URL | str | None = None,
        language: Language | None = None,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        apps: Iterable[App] | None = None,
        avatar: Media | None = None,
    ) -> None:
        """Edits the clan.

        Parameters
        ----------
        abbreviation
            The new abbreviation for the clan.
        headline
            The new headline for the clan.
        summary
            The new summary for the clan.
        community_url
            The new custom URL for the clan.
        language
            The new language for the clan.
        country
            The new country for the clan.
        state
            The new state for the clan.
        city
            The new city for the clan.
        apps
            The new apps for the clan.
        avatar
            The new avatar for the clan.
        """
        if isinstance(community_url, str):
            community_url = URL(community_url)
        if community_url is not None:
            community_url = community_url.parts[-1] or community_url.parts[-2]

        await self._state.http.edit_clan(
            self.id64,
            abbreviation=abbreviation,
            headline=headline,
            summary=summary,
            community_url_path=community_url,
            language=language,
            country=country,
            state=state,
            city=city,
            apps=(app.id for app in apps) if apps is not None else None,
        )
        if avatar:
            await self._state.http.update_avatar(
                avatar,
                "group_avatar_image",
                gId=self.id64,
                query={
                    "type": "group_avatar_image",
                    "gId": self.id64,
                    "bgColor": "1b2838",
                },
            )

    async def fetch_members(self) -> AsyncGenerator[PartialUser, None]:
        """An :term:`async iterator` over a clan's member list.

        Note
        ----
        This can be a very slow operation due to the rate limits on this endpoint.
        """
        async for id32 in self._state.http.get_clan_members(self.id64):
            yield self._state.get_partial_user(id32)

    async def join(self) -> None:
        """Joins the clan."""
        await self._state.http.join_clan(self.id64)

    async def leave(self) -> None:
        """Leaves the clan."""
        await self._state.http.leave_clan(self.id64)

    # event/announcement stuff

    async def fetch_event(self, id: int) -> Event[EventType, Self]:
        """Fetch an event from its ID.

        Parameters
        ----------
        id
            The ID of the event.
        """
        try:
            (data,) = await self._state.http.get_clan_events(self.id, [id])
            return await Event(self._state, self, data)
        except ValueError:
            raise ValueError(f"Event {id} not found")

    async def fetch_announcement(self, id: int) -> Announcement[Self]:
        """Fetch an announcement from its ID.

        Parameters
        ----------
        id
            The ID of the announcement.
        """
        data = await self._state.http.get_clan_announcement(self.id, id)
        return await Announcement(self._state, self, data)

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
    ) -> Event[Literal[EventType.Game], Self]:
        ...

    @overload
    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: BoringEventT = EventType.Other,
        starts_at: datetime | None = None,
    ) -> Event[BoringEventT, Self]:
        ...

    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: CreateableEvents = EventType.Other,
        app: App | None = None,
        starts_at: datetime | None = None,
        server_address: IPAdress | str | None = None,
        server_password: str | None = None,
    ) -> Event[CreateableEvents, Self]:
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
                if event.name != name or event.content != content:
                    continue
                self._state.dispatch("event_create", event)
                return cast(Event[CreateableEvents, Self], event)
        raise ValueError

    async def create_announcement(
        self,
        name: str,
        content: str,
        *,
        hidden: bool = False,
    ) -> Announcement[Self]:
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
        async for entry in self._state.client.user_news(flags=UserNewsType.PostedAnnouncement):
            if entry.target == self._state.user and entry.actor == self:
                announcement = cast("Announcement[Self]", await entry.announcement())
                entry.actor = self  # makes the above line safe
                if announcement.name != name or announcement.content != content:
                    continue
                self._state.dispatch("announcement_create", announcement)
                return announcement

        raise ValueError


class Clan(ChatGroup[ClanMember, ClanChannel, Literal[Type.Clan]], PartialClan):
    """Represents a Steam clan.

    .. container:: operations

        .. describe:: x == y

            Checks if two clans are equal.

        .. describe:: str(x)

            Returns the clan's name.
    """

    __slots__ = (
        "summary",
        "headline",
        "created_at",
        "language",
        "location",
        "member_count",
        "in_game_count",
        "online_count",
        "_is_app_clan",
    )

    # TODO more to implement https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/groups.js
    # Clan.requesting_membership
    # Clan.respond_to_requesting_membership(*users, approve)
    # Clan.respond_to_all_requesting_membership(approve)

    summary: BBCodeStr | None
    """The summary of the clan."""
    headline: str | None
    """The headline of the clan."""
    created_at: datetime | None
    """The time the clan was created at."""
    member_count: int
    """The amount of users in the clan."""
    online_count: int
    """The amount of users currently online."""
    in_game_count: int
    """The amount of user's currently in game."""
    language: Language
    """The language set for the clan."""
    location: str
    """The location set for the clan."""
    flags: ClanAccountFlags | None
    """The flags"""
    _is_app_clan: bool

    def __init__(self, state: ConnectionState, id: Intable) -> None:
        PartialClan.__init__(self, state, id)
        self._init()
        self.flags = None

    async def _load(self, *, from_proto: bool = False) -> Self:
        community_url = self.community_url
        assert community_url is not None
        async with self._state.http._session.get(community_url) as resp:
            soup = BeautifulSoup(await resp.text(), HTML_PARSER)  # technically we loose proper request handling here
            self._is_app_clan = "games" in resp.url.parts

        if not from_proto:
            assert soup.title is not None
            _, _, self.name = soup.title.text.rpartition(" :: ")
            icon_url = soup.find("link", rel="image_src")
            url = URL(cast(str, icon_url["href"])) if isinstance(icon_url, Tag) else None
            if url:
                self._avatar_sha = bytes.fromhex(url.path.removesuffix("/").removesuffix("_full.jpg"))

        headline = soup.find("div", class_="group_content group_summary")
        headline_h1 = headline.h1 if isinstance(headline, Tag) else None
        self.headline = headline_h1.text if headline_h1 else None
        content = soup.find("meta", property="og:description")
        self.summary = parse_bb_code(cast(str, content["content"])) if isinstance(content, Tag) else None

        if self._is_app_clan:
            for entry in soup.find_all("div", class_="actionItem"):
                if (a := entry.a) is not None:
                    href = a.get("href", "")
                    if match := re.findall(r"store.steampowered.com/app/(\d+)", href):
                        self.app = PartialApp(self._state, id=match[0])
        stats = soup.find("div", class_="grouppage_resp_stats")
        if stats is None:
            return self
        assert isinstance(stats, Tag)
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

        if not from_proto:
            self._officers: list[ID32] = []
            self._mods: list[ID32] = []
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
                        id = ID32(int(field["data-miniprofile"]))
                    except KeyError:
                        continue
                    else:
                        if is_admins is None:
                            continue
                        if is_admins:
                            self._officers.append(id)
                        else:
                            self._mods.append(id)

            self._officers_and_mods = await self._state._maybe_users(map(parse_id64, self._officers + self._mods))

        return self

    @classmethod
    async def _from_proto(  # type: ignore
        cls,
        state: ConnectionState,
        proto: chat.GetChatRoomGroupSummaryResponse,
        *,
        maybe_chunk: bool = True,
    ) -> Self:
        self = await super()._from_proto(state, proto, id=ID32(proto.clanid), maybe_chunk=maybe_chunk)
        return await self._load(from_proto=True)

    async def chunk(self) -> Sequence[ClanMember]:
        if self.chunked:
            return self.members

        self._members = dict.fromkeys(self._partial_members)  # type: ignore
        if self.flags & ClanAccountFlags.Large > 0 if self.flags is not None else len(self._partial_members) <= 100:
            for user, member in zip(
                await self._state._maybe_users(parse_id64(id, type=Type.Individual) for id in self._partial_members),
                self._partial_members.values(),
            ):
                self._members[user.id] = ClanMember(self._state, self, user, member)

            return await super().chunk()

        # these actually need fetching
        view_id = self._state.chat_group_to_view_id[self._id]
        users = {
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
            self._members[user.id] = ClanMember(self._state, self, user, member)
        return await super().chunk()

    def _get_partial_member(self, id: ID32, /) -> PartialMember:
        try:
            return PartialMember(self._state, clan=self, member=self._partial_members[id])
        except KeyError:
            member = self._partial_members[id] = chat.Member(id, state=chat.EChatRoomJoinState.NONE)
            return PartialMember(self._state, clan=self, member=member)

    def is_ogg(self) -> bool:
        """Whether this clan is an official game group."""
        if self.flags is not None:
            return self.flags & ClanAccountFlags.OGG > 0
        return self._is_app_clan

    async def edit(
        self,
        *,
        abbreviation: str | None = None,
        headline: str | None = None,
        summary: str | None = None,
        community_url: URL | str | None = None,
        language: Language | None = None,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        apps: Iterable[App] | None = None,
        name: str | None = None,
        tagline: str | None = None,
        avatar: Media | None = None,
    ) -> None:
        """Edits the clan.

        Parameters
        ----------
        name
            The new name for the clan's chat group. **Does not change the clan's name.**
        tagline
            The new tagline for the clan.
        avatar
            The new avatar for the clan.

        See Also
        --------
        :meth:`PartialClan.edit` for other parameters.
        """
        await PartialClan.edit(
            self,
            abbreviation=abbreviation,
            headline=headline,
            summary=summary,
            community_url=community_url,
            language=language,
            country=country,
            state=state,
            city=city,
            apps=apps,
            avatar=avatar,
        )
        await super().edit(name=name, tagline=tagline)

    async def fetch_members(self) -> AsyncGenerator[ClanMember | PartialMember, None]:
        async for id32 in self._state.http.get_clan_members(self.id64):
            yield self._maybe_member(id32)

    async def join(self, *, invite_code: str | None = None) -> None:
        await self._state.http.join_clan(self.id64)
        await super().join(invite_code=invite_code)

    async def leave(self) -> None:
        await super().leave()
        await self._state.http.leave_clan(self.id64)

    async def events(
        self,
        *,
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AsyncGenerator[Event[EventType, Self], None]:
        """An :term:`asynchronous iterator` over a clan's :class:`steam.Event`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
            dates += (date(year, month, 1) for month in range(start_month, stop_month))
            start_month = 1

        ids = [
            id
            for date_chunk in utils.as_chunks(dates, 12)
            for ids in await asyncio.gather(
                *(self._state.http.get_clan_events_for(self.id64, date) for date in date_chunk)
            )
            for id in ids
        ]

        yielded = 0

        for id_chunk in utils.as_chunks(ids, 15):
            events: list[Event[EventType, Self]] = []
            for event_ in await self._state.http.get_clan_events(self.id, id_chunk):
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
    ) -> AsyncGenerator[Announcement[Self], None]:
        """An :term:`asynchronous iterator` over a clan's :class:`steam.Announcement`\\s.

        Examples
        --------

        Usage:

        .. code:: python

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
        after = after or UNIX_EPOCH
        before = before or DateTime.now()

        ids = await self._state.http.get_clan_announcement_ids(
            self.id64
        )  # TODO make this use the calendar? does that work for announcements

        if not ids:
            return

        announcements: list[Announcement[Self]] = []
        for announcement_ in await asyncio.gather(*(self._state.http.get_clan_announcement(self.id, id) for id in ids)):
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
