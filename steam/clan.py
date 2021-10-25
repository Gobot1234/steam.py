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
import re
import time
import warnings
from datetime import datetime
from typing import TYPE_CHECKING, Any, overload

from bs4 import BeautifulSoup
from typing_extensions import Literal

from . import utils
from .abc import Commentable, SteamID
from .channel import ClanChannel
from .enums import ClanEvent, Type
from .errors import HTTPException, WSForbidden
from .event import Announcement, Event
from .game import Game, StatefulGame
from .iterators import AnnouncementsIterator, EventIterator
from .protobufs import chat
from .role import Role

if TYPE_CHECKING:
    from .state import ConnectionState
    from .user import User

__all__ = ("Clan",)


class Clan(SteamID, Commentable, utils.AsyncInit):
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
    chat_id
        The clan's chat id, this is different to :attr:`id`.
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
    top_members
        A list of the clan's top_members.
    roles
        A list of the clan's roles.
    default_role
        The clan's default role.
    """

    __slots__ = (
        "name",
        "content",
        "avatar_url",
        "created_at",
        "language",
        "location",
        "member_count",
        "in_game_count",
        "online_count",
        "admins",
        "mods",
        "chat_id",
        "active_member_count",
        "owner",
        "default_role",
        "tagline",
        "top_members",
        "roles",
        "game",
        "community_url",
        "_channels",
        "_default_channel_id",
        "_state",
    )

    # TODO more to implement https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/groups.js
    # Clan.kick
    # Clan.ban
    # Group.create_channel
    # Clan.requesting_membership
    # Clan.respond_to_requesting_membership(*users, approve)
    # Clan.respond_to_all_requesting_membership(approve)

    name: str
    content: str
    avatar_url: str
    created_at: datetime | None
    member_count: int
    online_count: int
    in_game_count: int
    language: str
    location: str
    mods: list[User]
    admins: list[User]
    is_game_clan: bool
    community_url: str

    def __init__(self, state: ConnectionState, id: int):
        super().__init__(id, type=Type.Clan)
        self._state = state

        self.chat_id: int | None = None
        self.tagline: str | None = None
        self.game: StatefulGame | None = None
        self.owner: User | None = None
        self.active_member_count: int | None = None
        self.top_members: list[User | None] = []
        self.roles: list[Role] = []
        self.default_role: Role | None = None
        self._channels: dict[int, ClanChannel] = {}
        self._default_channel_id: int | None = None

    async def __ainit__(self) -> None:
        resp = await self._state.http._session.get(super().community_url)
        text = await resp.text()  # technically we loose proper request handling here
        if not self.id64:
            search = utils.CLAN_ID64_FROM_URL_REGEX.search(text)
            if search is None:
                raise ValueError("unreachable code reached")
            super().__init__(search["steamid"], type=Type.Clan)

        soup = BeautifulSoup(text, "html.parser")
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
                    text = f"{text}, {datetime.utcnow().year}"
                try:
                    self.created_at = datetime.strptime(text, "%d %B, %Y" if text.split()[0].isdigit() else "%B %d, %Y")
                except ValueError:  # why do other countries have to exist
                    self.created_at = None
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
        is_admins = True
        for fields in soup.find_all("div", class_="membergrid"):
            for idx, field in enumerate(fields.find_all("div")):
                if "Members" in field.text:
                    if mods:
                        del mods[-1]
                    break
                if "Moderators" in field.text:
                    officer = admins.pop()
                    mods.append(officer)
                    is_admins = False
                try:
                    account_id = fields.find_all("div", class_="playerAvatar")[idx]["data-miniprofile"]
                except IndexError:
                    break
                else:
                    if is_admins:
                        admins.append(account_id)
                    else:
                        mods.append(account_id)

        users = await self._state.client.fetch_users(*admins, *mods)
        self.admins = [user for user in users if user and user.id in admins]
        self.admins = [user for user in users if user and user.id in mods]

    @classmethod
    async def _from_proto(
        cls,
        state: ConnectionState,
        clan_proto: chat.SummaryPair
        | chat.GetClanChatRoomInfoResponse
        | chat.GetChatRoomGroupSummaryResponse
        | chat.GroupHeaderState,
    ) -> Clan:
        if isinstance(clan_proto, chat.SummaryPair):
            id = clan_proto.group_summary.clanid
        else:
            id = clan_proto.chat_group_summary.clanid
        self = await cls(state, id)

        proto = clan_proto.group_summary if isinstance(clan_proto, chat.SummaryPair) else clan_proto.chat_group_summary

        self.chat_id = proto.chat_group_id
        self.tagline = proto.chat_group_tagline or None
        self.active_member_count = proto.active_member_count
        self.game = StatefulGame(self._state, id=proto.appid) if proto.appid else self.game

        self.owner = await self._state._maybe_user(utils.make_id64(proto.accountid_owner))
        self.top_members = await self._state.fetch_users([utils.make_id64(u) for u in proto.top_members])

        if hasattr(clan_proto, "roles"):
            roles = clan_proto.roles
        else:
            try:
                roles = await self._state.fetch_group_roles(self.chat_id)
            except WSForbidden:
                roles = []

        for role in roles:
            for permissions in proto.role_actions:
                if permissions.role_id == role.role_id:
                    self.roles.append(Role(self._state, self, role, permissions))
        self.default_role = utils.get(self.roles, id=proto.default_role_id)
        if not isinstance(clan_proto, chat.SummaryPair):
            return self

        for channel in clan_proto.user_chat_group_state.user_chat_room_state:
            try:
                new_channel = self._channels[channel.chat_id]
            except KeyError:
                new_channel = ClanChannel(state=self._state, clan=self, proto=channel)
                self._channels[new_channel.id] = new_channel
            else:
                new_channel._update(channel)
        self._default_channel_id = proto.default_chat_id
        return self

    def _update(self, proto: chat.ChatRoomGroupRoomsChangeNotification) -> None:
        for channel in proto.chat_rooms:
            try:
                new_channel = self._channels[channel.chat_id]
            except KeyError:
                new_channel = ClanChannel(state=self._state, clan=self, proto=channel)
                self._channels[new_channel.id] = new_channel
            else:
                new_channel._update(channel)
        self._default_channel_id = proto.default_chat_id

    def __repr__(self) -> str:
        attrs = ("name", "id", "chat_id", "type", "universe", "instance")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f"<Clan {' '.join(resolved)}>"

    def __str__(self) -> str:
        return self.name

    @property
    def _commentable_kwargs(self) -> dict[str, Any]:
        return {
            "id64": self.id64,
            "thread_type": 12,
        }

    @property
    def channels(self) -> list[ClanChannel]:
        """A list of the clan's channels."""
        return list(self._channels.values())

    @property
    def default_channel(self) -> ClanChannel | None:
        """The clan's default channel."""
        return self.get_channel(self._default_channel_id)  # type: ignore

    def get_channel(self, id: int) -> ClanChannel | None:
        """Get a channel from cache.

        Parameters
        ----------
        id
            The id of the channel.
        """
        return self._channels.get(id)

    async def fetch_members(self) -> list[SteamID]:
        """Fetches a clan's member list.

        Note
        ----
        This can be a very slow operation due to the rate limits on this endpoint.
        """

        def process(resp: str) -> BeautifulSoup:
            soup = BeautifulSoup(resp, "html.parser")
            for s in soup.find_all("div", id="memberList"):
                for user in s.find_all("div", class_="member_block"):
                    ret.append(SteamID(user["data-miniprofile"]))

            return soup

        async def getter(i: int) -> None:
            try:
                resp = await self._state.http.get(
                    f"{self.community_url}/members", params={"p": i + 1, "content_only": "true"}
                )
            except HTTPException:
                await asyncio.sleep(20)
                await getter(i)
            else:
                process(resp)

        ret = []
        resp = await self._state.http.get(f"{self.community_url}/members", params={"p": 1, "content_only": "true"})
        soup = process(resp)
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

    async def join(self) -> None:
        """Joins the clan. This will also join the clan's chat."""
        await self._state.http.join_clan(self.id64)
        await self._state.join_chat(self.chat_id)

    async def leave(self) -> None:
        """Leaves the clan."""
        await self._state.http.leave_clan(self.id64)

    async def invite(self, user: User) -> None:
        """Invites a :class:`~steam.User` to the clan.

        Parameters
        -----------
        user
            The user to invite to the clan.
        """
        await self._state.http.invite_user_to_clan(user.id64, self.id64)

    # event/announcement stuff

    async def fetch_event(self, id: int) -> Event:
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
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> EventIterator:
        """An :class:`~steam.iterators.AsyncIterator` over a clan's :class:`steam.Event`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for event in client.events(limit=10):
                print(event.author, "made an event", event.name, "starting at", event.starts_at)

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of events to search through. Default is ``100``. Setting this to ``None`` will fetch all
            of the clan's events, but this will be a very slow operation.
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
        limit: int | None = 100,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> AnnouncementsIterator:
        """An :class:`~steam.iterators.AsyncIterator` over a clan's :class:`steam.Announcement`\\s.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for announcement in client.announcements(limit=10):
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
        return AnnouncementsIterator(self, self._state, limit, before, after)

    @overload
    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: Literal[
            ClanEvent.Other,
            ClanEvent.Chat,
            ClanEvent.Party,
            ClanEvent.Meeting,
            ClanEvent.SpecialCause,
            ClanEvent.MusicAndArts,
            ClanEvent.Sports,
            ClanEvent.Trip,
        ] = ClanEvent.Other,
        starts_at: datetime | None = None,
    ) -> Event:
        ...

    @overload
    async def create_event(
        self,
        name: str,
        content: str,
        *,
        game: Game,
        type: Literal[ClanEvent.Game] = ...,
        starts_at: datetime | None = ...,
        server_address: str | None = ...,
        server_password: str | None = ...,
    ) -> Event:
        ...

    async def create_event(
        self,
        name: str,
        content: str,
        *,
        type: Literal[
            ClanEvent.Other,
            ClanEvent.Chat,
            ClanEvent.Game,
            # ClanEvent.Broadcast,  # TODO need to wait until implementing stream support for this
            ClanEvent.Party,
            ClanEvent.Meeting,
            ClanEvent.SpecialCause,
            ClanEvent.MusicAndArts,
            ClanEvent.Sports,
            ClanEvent.Trip,
        ] = ClanEvent.Other,
        game: Game | None = None,
        starts_at: datetime | None = None,
        server_address: str | None = None,
        server_password: str | None = None,
    ) -> Event:
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
        soup = BeautifulSoup(resp, "html.parser")
        for element in soup.find_all("div", class_="eventBlockTitle"):
            a = element.a
            if a is not None and a.text == name:  # this is bad?
                _, __, id = a["href"].rpartition("/")
                if starts_at is not None:
                    timestamp = (
                        starts_at.timestamp()
                        if starts_at.tzinfo is not None
                        else (starts_at + (datetime.utcnow() - datetime.now())).timestamp()
                    )
                else:
                    timestamp = 0
                data = {
                    "gid": id,
                    "event_name": name,
                    "event_notes": content,
                    "event_type": type.value,
                    "appid": str(game.id) if game is not None else "",
                    "rtime32_start_time": timestamp,
                    "rtime32_last_modified": timestamp,
                    "server_address": server_address,
                    "server_password": server_password,
                }
                event = Event(self._state, self, data)
                event.author = self._state.client.user
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
            Whether or not the announcement should initially be hidden.

        Returns
        -------
        The created announcement.
        """
        await self._state.http.create_clan_announcement(self.id64, name, content, hidden)
        resp = await self._state.http.get(f"{self.community_url}/announcements", params={"content_only": "true"})
        soup = BeautifulSoup(resp, "html.parser")
        for element in soup.find_all("div", class_="announcement"):
            a = element.a
            if a is not None and a.text == name:  # this is bad?
                _, __, id = a["href"].rpartition("/")
                timestamp = int(time.time())

                data = {
                    "gid": id,
                    "event_name": name,
                    "event_notes": "",
                    "event_type": ClanEvent.News,
                    "appid": 0,
                    "rtime32_start_time": timestamp,
                    "rtime32_last_modified": timestamp,
                    "announcement_body": {
                        "body": content,
                        "posttime": timestamp,
                        "updatetime": timestamp,
                    },
                    "comment_type": "ClanAnnouncement",
                    "hidden": hidden,
                }
                announcement = Announcement(self._state, self, data)
                announcement.author = self._state.client.user
                self._state.dispatch("announcement_create", announcement)
                return announcement

        raise ValueError
