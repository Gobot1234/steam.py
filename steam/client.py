"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/Rapptz/discord.py/blob/master/discord/client.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import random
import sys
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Collection, Coroutine, Sequence
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, TypeVar, final, overload

import aiohttp
from bs4 import BeautifulSoup

from . import errors, utils
from ._const import DOCS_BUILDING, MISSING, STATE, UNIX_EPOCH, URL
from .app import App, FetchedApp, PartialApp
from .enums import Language, PersonaState, PersonaStateFlag, PublishedFileRevision, Type, UIMode
from .game_server import GameServer, Query
from .gateway import *
from .guard import generate_one_time_code
from .http import HTTPClient
from .id import ID
from .manifest import AppInfo, PackageInfo
from .models import PriceOverview, return_true
from .package import FetchedPackage, License, Package, PartialPackage
from .post import Post
from .published_file import PublishedFile
from .reaction import ClientEmoticon, ClientSticker
from .state import ConnectionState
from .types.id import AppID, BundleID, Intable, PackageID
from .utils import DateTime, TradeURLInfo, parse_id64

if TYPE_CHECKING:
    import steam

    from .abc import Message
    from .clan import Clan
    from .comment import Comment
    from .event import Announcement, Event
    from .friend import Friend
    from .group import Group
    from .invite import ClanInvite, UserInvite
    from .protobufs import Message, ProtobufMessage
    from .reaction import MessageReaction
    from .trade import TradeOffer
    from .types.http import IPAdress
    from .user import ClientUser, User

__all__ = ("Client",)

log = logging.getLogger(__name__)

EventType: TypeAlias = Callable[..., Coroutine[Any, Any, Any]]
E = TypeVar("E", bound=EventType)
EventDeco: TypeAlias = Callable[[E], E] | E


class Client:
    """Represents a client connection that connects to Steam. This class is used to interact with the Steam API and CMs.

    Parameters
    ----------
    proxy
        A proxy URL to use for requests.
    proxy_auth
        The proxy authentication to use with requests.
    connector
        The connector to use with the :class:`aiohttp.ClientSession`.
    max_messages
        The maximum number of messages to store in the internal cache, default is 1000.
    app
        An app to set your status as on connect.
    apps
        A list of apps to set your status to on connect.
    state
        The state to show your account as on connect.

        Note
        ----
        Setting your status to :attr:`~steam.PersonaState.Offline`, will stop you receiving persona state updates
        and by extension :meth:`on_user_update` will stop being dispatched.
    ui_mode
        The UI mode to set your status to on connect.
    flags
        Flags to set your persona state to.
    force_kick
        Whether to forcefully kick any other playing sessions on connect. Defaults to ``False``.
    language
        The language to use when interacting with the API.
    auto_chunk_chat_groups
        Whether to automatically call chunk on clans and groups filling :attr:`ChatGroup.members`. Setting this to
        ``True`` isn't recommend unless you have a good internet connection and good hardware.
    """

    # TODO
    # Client.create_clan
    # Client.create_group

    @overload
    def __init__(  # type: ignore
        self,
        *,
        proxy: str | None = ...,
        proxy_auth: aiohttp.BasicAuth | None = ...,
        connector: aiohttp.BaseConnector | None = ...,
        max_messages: int | None = 1000,
        app: App | None = ...,
        apps: list[App] = ...,
        state: PersonaState | None = PersonaState.Online,
        ui_mode: UIMode | None = UIMode.Desktop,
        flags: PersonaStateFlag | None = PersonaStateFlag.NONE,
        force_kick: bool = False,
        language: Language = Language.English,
        auto_chunk_chat_groups: bool = False,
    ):
        ...

    def __init__(self, **options: Any):
        loop = options.get("loop")
        if loop:
            import inspect
            import warnings

            warnings.warn(
                "The loop argument is deprecated and scheduled for removal in V.1",
                stacklevel=len(inspect.stack())
                + 1,  # make sure its always at the top of the stack most likely where the Client was created
            )
        self.loop = asyncio.get_event_loop()
        self.http = HTTPClient(client=self, **options)
        self._state = self._get_state(**options)
        STATE.set(self._state)
        self.ws: SteamWebSocket | None = None

        self.username: str | None = None
        self.password: str | None = None
        self.shared_secret: str | None = None
        self.identity_secret: str | None = None

        self._closed = True
        self._listeners: dict[str, list[tuple[asyncio.Future[Any], Callable[..., bool]]]] = {}
        self._ready = asyncio.Event()

    def _get_state(self, **options: Any) -> ConnectionState:
        return ConnectionState(client=self, **options)

    @property
    def user(self) -> ClientUser:
        """Represents the connected client. ``None`` if not logged in."""
        return self.http.user

    @property
    def users(self) -> Sequence[User]:
        """A read-only list of all the users the connected client can see."""
        return self._state.users

    @property
    def trades(self) -> Sequence[TradeOffer]:
        """A read-only list of all the trades the connected client can see."""
        return self._state.trades

    @property
    def groups(self) -> Sequence[Group]:
        """A read-only list of all the groups the connected client is in."""
        return self._state.groups

    @property
    def messages(self) -> Sequence[Message]:
        """A read-only list of all the messages the client has."""
        return self._state._messages

    @property
    def clans(self) -> Sequence[Clan]:
        """A read-only list of all the clans the connected client is in."""
        return self._state.clans

    @property
    def licenses(self) -> Sequence[License]:
        """A read-only list of licenses the client has access to."""
        return list(self._state.licenses.values())

    @property
    def emoticons(self) -> Sequence[ClientEmoticon]:
        """A read-only list of all the emoticons the client has."""
        return self._state.emoticons

    @property
    def stickers(self) -> Sequence[ClientSticker]:
        """A read-only list of all the stickers the client has."""
        return self._state.stickers

    @property
    def latency(self) -> float:
        """Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return float("nan") if self.ws is None else self.ws.latency

    @property
    def refresh_token(self) -> str | None:
        """The refresh token for the logged in account, can be used to login."""
        return None if self.ws is None else self.ws.refresh_token

    async def code(self) -> str:
        """Get the current steam guard code.

        Warning
        -------
        This function will wait for a Steam guard code using :func:`input` in an executor if no shared_secret is passed
        to :meth:`run` or :meth:`start`, which blocks exiting until one is entered.
        """
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        print("Please enter a Steam guard code")
        code = await utils.ainput(">>> ")
        return code.strip()

    def is_ready(self) -> bool:
        """Specifies if the client's internal cache is ready for use."""
        return self._ready.is_set()

    def is_closed(self) -> bool:
        """Indicates if connection is closed to the API or CMs."""
        return self._closed

    @overload
    def event(self, coro: None = ...) -> Callable[[E], E]:
        ...

    @overload
    def event(self, coro: E) -> E:
        ...

    def event(self, coro: Callable[[E], E] | E | None = None) -> Callable[[E], E] | E:
        """|maybecallabledeco|
        Register an event to listen to.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Usage:

        .. code-block:: python3

            @client.event
            async def on_ready():
                print("Ready!")

        Raises
        ------
        :exc:`TypeError`
            The function passed is not a coroutine.
        """

        def decorator(coro: E) -> E:
            if not asyncio.iscoroutinefunction(coro):
                raise TypeError(f"Registered events must be a coroutines, {coro.__name__} is {type(coro).__name__}")

            setattr(self, coro.__name__, coro)
            log.debug(f"{coro.__name__} has been registered as an event")
            return coro

        return decorator(coro) if coro is not None else decorator

    async def _run_event(self, coro: EventType, event_name: str, *args: Any, **kwargs: Any) -> None:
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            try:
                await self.on_error(event_name, exc, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    def _schedule_event(self, coro: EventType, event_name: str, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        return asyncio.create_task(
            self._run_event(coro, event_name, *args, **kwargs), name=f"steam.py task: {event_name}"
        )

    def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        log.debug(f"Dispatching event {event}")
        method = f"on_{event}"

        # remove the dispatched listener
        if listeners := self._listeners.get(event):
            removed: list[int] = []
            for idx, (future, condition) in enumerate(listeners):
                if future.cancelled():
                    removed.append(idx)
                    continue

                try:
                    result = condition(*args)
                except Exception as exc:
                    future.set_exception(exc)
                    removed.append(idx)
                else:
                    if result:
                        if not args:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(idx)

            if len(removed) == len(listeners):
                del self._listeners[event]
            else:
                for idx in reversed(removed):
                    del listeners[idx]

        # schedule the event (if possible)
        try:
            coro = getattr(self, method)
        except AttributeError:
            pass
        else:
            self._schedule_event(coro, method, *args, **kwargs)

    async def _handle_ready(self) -> None:
        self._ready.set()
        self.dispatch("ready")

    @overload
    @final
    def run(
        self,
        username: str,
        password: str,
        *,
        shared_secret: str = MISSING,
        identity_secret: str = MISSING,
    ) -> object:
        ...

    @overload
    @final
    def run(self, *, refresh_token: str) -> object:
        ...

    @final
    def run(self, *args: Any, **kwargs: Any) -> object:
        """A blocking call that abstracts away the event loop initialisation from you.

        It is not recommended to subclass this method, it is normally favourable to subclass :meth:`start` as it is a
        :ref:`coroutine <coroutine>`.

        Note
        ----
        This takes the same arguments as :meth:`start`.
        """

        async def runner() -> None:
            asyncio.events.new_event_loop = old_new_event_loop
            try:
                await self.login(*args, **kwargs)
            finally:
                if not self.is_closed():
                    await self.close()

        # we just have to monkey patch in support for using get_event_loop
        old_new_event_loop = asyncio.new_event_loop
        asyncio.events.new_event_loop = asyncio.get_event_loop
        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            log.info("Closing the event loop")

    async def close(self) -> None:
        """Close the connection to Steam."""
        if self.is_closed():
            return

        self._closed = True

        if self.ws is not None:
            try:
                await self.change_presence(app=App(id=0))  # disconnect from games
                await self.ws.handle_close()
            except ConnectionClosed:
                pass

        await self.http.close()
        self._ready.clear()

    def clear(self) -> None:
        """Clears the internal state of the bot. After this, the bot can be considered "re-opened", i.e.
        :meth:`is_closed` and :meth:`is_ready` both return ``False``. This also clears the internal cache.
        """
        self._closed = False
        self._ready.clear()
        self._state.clear()
        self.http.clear()

    @overload
    async def login(
        self,
        username: str,
        password: str,
        *,
        shared_secret: str = ...,
        identity_secret: str = ...,
    ) -> None:
        ...

    @overload
    async def login(
        self,
        *,
        refresh_token: str,
    ) -> None:
        ...

    async def login(
        self,
        username: str = MISSING,
        password: str = MISSING,
        *,
        shared_secret: str = MISSING,
        identity_secret: str = MISSING,
        refresh_token: str = MISSING,
    ) -> None:
        """Initialize a connection to a Steam CM and login.

        If no ``shared_secret`` is passed, you will have to manually enter a Steam guard code using :meth:`code`.

        Parameters
        ----------
        username
            The username of the account to login to.
        password
            The password of the account to login to.
        shared_secret
            The shared secret for the account to login to.
        identity_secret
            The identity secret for the account to login to.

        Other Parameters
        ----------------
        refresh_token
            The refresh token of the account to login to.
        """
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        self._closed = False

        if identity_secret is None:
            log.info("Trades will not be automatically accepted when sent as no identity_secret was passed.")

        exceptions = (
            OSError,
            ConnectionClosed,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            errors.HTTPException,
        )

        async def throttle() -> None:
            now = time.monotonic()
            between = now - last_connect
            sleep = random.random() * 4 if between > 600 else 100 / between**0.5
            log.info(f"Attempting to connect to another CM in {sleep}")
            await asyncio.sleep(sleep)

        self.http.clear()
        while not self.is_closed():
            last_connect = time.monotonic()

            try:
                self.ws = await asyncio.wait_for(SteamWebSocket.from_client(self, refresh_token), timeout=60)
            except exceptions:
                await throttle()
                continue

            try:
                while True:
                    await self.ws.poll_event()
            except exceptions as exc:
                if isinstance(exc, ConnectionClosed):
                    self._state._connected_cm = exc.cm
                self.dispatch("disconnect")
            finally:
                if not self.is_closed():
                    await throttle()

    async def anonymous_login(self) -> None:
        """Initialize a connection to a Steam CM and login anonymously."""
        self._closed = False

        exceptions = (
            OSError,
            ConnectionClosed,
            aiohttp.ClientError,
            asyncio.TimeoutError,
            errors.HTTPException,
        )

        async def throttle() -> None:
            now = time.monotonic()
            between = now - last_connect
            sleep = random.random() * 4 if between > 600 else 100 / between**0.5
            log.info(f"Attempting to connect to another CM in {sleep}")
            await asyncio.sleep(sleep)

        self.http.clear()
        while not self.is_closed():
            last_connect = time.monotonic()

            try:
                self.ws = await asyncio.wait_for(SteamWebSocket.anonymous_login_from_client(self), timeout=60)
            except exceptions:
                await throttle()
                continue

            try:
                while True:
                    await self.ws.poll_event()
            except exceptions as exc:
                if isinstance(exc, ConnectionClosed):
                    self._state._connected_cm = exc.cm
                self.dispatch("disconnect")
            finally:
                if not self.is_closed():
                    await throttle()

    # state stuff
    # TODO decide on where this should take id32s
    def get_user(self, id: Intable) -> User | None:
        """Returns a user from cache with a matching ID or ``None`` if the user was not found.

        Parameters
        ----------
        id
            The ID of the user, can be an :attr:`.ID.id64`, :attr:`.ID.id`, :attr:`.ID.id2` or an
            :attr:`.ID.id3`.
        """
        steam_id = ID(id=id, type=Type.Individual)
        return self._state.get_user(steam_id.id)

    async def fetch_user(self, id: Intable) -> User | None:
        """Fetches a user with a matching ID or ``None`` if the user was not found.

        Parameters
        ----------
        id
            The ID of the user, can be an :attr:`.ID.id64`, :attr:`.ID.id`, :attr:`.ID.id2` or an
            :attr:`.ID.id3`.
        """
        id64 = parse_id64(id=id, type=Type.Individual)
        return await self._state.fetch_user(id64)

    async def fetch_users(self, *ids: Intable) -> list[User]:
        """Fetches a list of :class:`~steam.User` or ``None`` if the user was not found, from their IDs.

        Note
        ----
        The :class:`~steam.User` objects returned are unlikely to retain the order they were originally in.

        Parameters
        ----------
        ids
            The user's IDs.
        """
        id64s = [parse_id64(id, type=Type.Individual) for id in ids]
        return await self._state.fetch_users(id64s)

    async def fetch_user_named(self, name: str) -> User | None:
        """Fetches a user from https://steamcommunity.com from their community URL name.

        Parameters
        ----------
        name
            The name of the user after https://steamcommunity.com/id
        """
        id64 = await utils.id64_from_url(URL.COMMUNITY / f"id/{name}", self.http._session)
        return await self._state.fetch_user(id64) if id64 is not None else None

    def get_trade(self, id: int) -> TradeOffer | None:
        """Get a trade from cache with a matching ID or ``None`` if the trade was not found.

        Parameters
        ----------
        id
            The id of the trade to search for from the cache.
        """
        return self._state.get_trade(id)

    async def fetch_trade(self, id: int, *, language: Language | None = None) -> TradeOffer | None:
        """Fetches a trade with a matching ID or ``None`` if the trade was not found.

        Parameters
        ----------
        id
            The ID of the trade to search for from the API.
        language
            The language to fetch the trade in. ``None`` uses the current language.
        """
        return await self._state.fetch_trade(id, language)

    def get_group(self, id: Intable) -> Group | None:
        """Get a group from cache with a matching ID or ``None`` if the group was not found.

        Parameters
        ----------
        id
            The ID of the group, can be an :attr:`.ID.id64`, :attr:`.ID.id`, :attr:`.ID.id2` or an
            :attr:`.ID.id3`.
        """
        steam_id = ID(id=id, type=Type.Chat)
        return self._state.get_group(steam_id.id)

    def get_clan(self, id: Intable) -> Clan | None:
        """Get a clan from cache with a matching ID or ``None`` if the group was not found.

        Parameters
        ----------
        id
            The ID of the clan, can be an :attr:`.ID.id64`, :attr:`.ID.id`, :attr:`.ID.id2` or an
            :attr:`.ID.id3`.
        """
        steam_id = ID(id=id, type=Type.Clan)
        return self._state.get_clan(steam_id.id)

    async def fetch_clan(self, id: Intable) -> Clan | None:
        """Fetches a clan from the websocket with a matching ID or ``None`` if the clan was not found.

        Parameters
        ----------
        id
            The ID of the clan, can be an :attr:`.ID.id64`, :attr:`.ID.id`, :attr:`.ID.id2` or an
            :attr:`.ID.id3`.
        """
        id64 = parse_id64(id=id, type=Type.Clan)
        return await self._state.fetch_clan(id64)

    async def fetch_clan_named(self, name: str) -> Clan | None:
        """Fetches a clan from https://steamcommunity.com with a matching name or ``None`` if the clan was not found.

        Parameters
        ----------
        name
            The name of the Steam clan.
        """
        steam_id = await ID.from_url(URL.COMMUNITY / "clans" / name, self.http._session)
        return await self._state.fetch_clan(steam_id.id64) if steam_id is not None else None

    def get_app(self, id: int | App) -> PartialApp:
        """Creates a stateful app from its ID.

        Parameters
        ----------
        id
            The app id of the app or a :class:`~steam.App` instance.
        """
        return PartialApp(self._state, id=getattr(id, "id", id))

    async def fetch_app(self, id: int | App, *, language: Language | None = None) -> FetchedApp | None:
        """Fetch an app from its ID or ``None`` if the app was not found.

        Parameters
        ----------
        id
            The app id of the app or a :class:`~steam.App` instance.
        language
            The language to fetch the app in. If ``None`` uses the current language.
        """
        id = id if isinstance(id, int) else id.id
        resp = await self.http.get_app(id, language)
        if resp is None:
            return None
        data = resp[str(id)]
        return FetchedApp(self._state, data["data"], language or self._state.language) if data["success"] else None

    def get_package(self, id: int) -> PartialPackage:
        """Creates a package from its ID.

        Parameters
        ----------
        id
            The ID of the package.
        """
        return PartialPackage(self._state, id=id)

    async def fetch_package(self, id: int | Package, *, language: Language | None = None) -> FetchedPackage | None:
        """Fetch a package from its ID.

        Parameters
        ----------
        id
            The ID of the package.
        language
            The language to fetch the package in. If ``None`` uses the current language.
        """
        id = PackageID(id) if isinstance(id, int) else id.id
        resp = await self.http.get_package(id, language)
        if resp is None:
            return None
        data = resp[str(id)]
        return FetchedPackage(self._state, data["data"]) if data["success"] else None

    @overload
    async def fetch_server(self, *, id: Intable) -> GameServer | None:
        ...

    @overload
    async def fetch_server(
        self,
        *,
        ip: IPAdress | str,
        port: int = ...,
    ) -> GameServer | None:
        ...

    async def fetch_server(
        self,
        *,
        id: Intable = MISSING,
        ip: IPAdress | str = MISSING,
        port: int | str = MISSING,
    ) -> GameServer | None:
        """Fetch a :class:`.GameServer` from its ip and port or its Steam ID or ``None`` if fetching the server failed.

        Parameters
        ----------
        ip
            The ip of the server.
        port
            The port of the server.
        id
            The ID of the game server, can be an :attr:`.ID.id64`, :attr:`.ID.id2` or an :attr:`.ID.id3`.
            If this is passed, it makes a call to the master server to fetch its ip and port.

        Note
        ----
        Passing an ``ip``, ``port`` and ``id`` to this function will raise an :exc:`TypeError`.
        """

        if all((id, ip, port)):
            raise TypeError("Too many arguments passed to fetch_server")
        if id:
            # we need to fetch the ip and port
            servers = await self._state.fetch_server_ip_from_steam_id(parse_id64(id, type=Type.GameServer))
            if not servers:
                raise ValueError(f"The master server didn't find a matching server for {id}")
            ip_, _, port = servers[0].addr.rpartition(":")
            ip = IPAdress(ip_)
        elif not ip:
            raise TypeError("fetch_server missing argument ip")

        servers = await self.fetch_servers(Query.ip / f"{ip}{f':{port}' if port is not None else ''}", limit=1)
        return servers[0] if servers else None

    async def fetch_servers(self, query: Query[Any], *, limit: int = 100) -> list[GameServer]:
        """Query game servers.

        Parameters
        ----------
        query
            The query to match servers with.
        limit
            The maximum amount of servers to return.
        """
        servers = await self._state.fetch_servers(query.query, limit)
        return [GameServer(self._state, server) for server in servers]

    # content server related stuff

    @overload
    async def fetch_product_info(self, *, apps: Collection[App]) -> list[AppInfo]:
        ...

    @overload
    async def fetch_product_info(self, *, packages: Collection[Package]) -> list[PackageInfo]:
        ...

    @overload
    async def fetch_product_info(
        self, *, apps: Collection[App], packages: Collection[Package]
    ) -> tuple[list[AppInfo], list[PackageInfo]]:
        ...

    async def fetch_product_info(
        self, *, apps: Collection[App] = (), packages: Collection[Package] = ()
    ) -> list[AppInfo] | list[PackageInfo] | tuple[list[AppInfo], list[PackageInfo]]:
        """Fetch product info.

        Parameters
        ----------
        apps
            The apps to fetch info on.
        packages
            The packages to fetch info on.
        """

        app_infos, package_infos = await self._state.fetch_product_info(
            (app.id for app in apps), (package.id for package in packages)
        )

        if apps and packages:
            return app_infos, package_infos

        return app_infos if apps else package_infos

    # miscellaneous stuff

    async def fetch_published_file(
        self,
        id: int,
        *,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
    ) -> PublishedFile | None:
        """Fetch a published file from its ID.

        Parameters
        ----------
        id
            The ID of the published file.
        revision
            The revision of the published file to fetch.
        language
            The language to fetch the published file in. If ``None``, the current language is used.
        """
        (file,) = await self._state.fetch_published_files((id,), revision, language)
        return file

    async def fetch_published_files(
        self,
        *ids: int,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
    ) -> list[PublishedFile | None]:
        """Fetch published files from their IDs.

        Parameters
        ----------
        ids
            The IDs of the published files.
        revision
            The revision of the published files to fetch.
        language
            The language to fetch the published files in. If ``None``, the current language is used.
        """
        return await self._state.fetch_published_files(ids, revision, language)

    async def create_post(self, content: str, app: App | None = None) -> Post:
        """Create a post.

        Parameters
        ----------
        content
            The content of the post.
        app
            The app to create the post for.
        """
        await self._state.create_user_post(content, app_id=AppID(0) if app is None else app.id)
        # TODO if ws ever gives the post id switch to just this
        # for now steam is broken and thinks I'm logged out even though /my seems to resolve to the right account
        resp = await self.http.get(URL.COMMUNITY / "my/myactivity")
        soup = BeautifulSoup(resp, "html.parser")
        for post in soup.find_all("div", class_="blotter_userstatus"):
            if (
                content_element := post.find("div", class_="blotter_userstatus_content responsive_body_text")
            ) is not None and content_element.text.strip() == content:
                id, _, _ = post["id"].removeprefix("userstatus_").partition("_")
                return Post(
                    self._state, int(id), content, self.user, PartialApp(self._state, id=app.id) if app else None
                )

        raise RuntimeError("Post created has no ID, this should be unreachable")

    async def trade_history(
        self,
        *,
        limit: int | None = 100,
        before: datetime.datetime | None = None,
        after: datetime.datetime | None = None,
        language: Language | None = None,
    ) -> AsyncGenerator[TradeOffer, None]:
        """An :term:`async iterator` for accessing a :class:`steam.ClientUser`'s
        :class:`steam.TradeOffer` objects.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for trade in client.trade_history(limit=10):
                items = [getattr(item, "name", str(item.id)) for item in trade.items_to_receive]
                items = ", ".join(items) or "Nothing"
                print("Partner:", trade.partner)
                print("Sent:", items)

        All parameters are optional.

        Parameters
        ----------
        limit
            The maximum number of trades to search through. Default is ``100``. Setting this to ``None`` will fetch all
            of the user's trades, but this will be a very slow operation.
        before
            A time to search for trades before.
        after
            A time to search for trades after.
        language
            The language to fetch the trade in. ``None`` uses the current language.

        Yields
        ---------
        :class:`~steam.TradeOffer`
        """
        from .trade import TradeOffer

        total = 100
        previous_time = 0
        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        after_timestamp = after.timestamp()
        before_timestamp = before.timestamp()
        yielded = 0

        async def get_trades(page: int = 100) -> list[TradeOffer]:
            nonlocal total, previous_time
            resp = await self._state.http.get_trade_history(page, previous_time, language)
            data = resp["response"]
            if total is None:
                total = data.get("total_trades", 0)
            if not total:
                return []

            trades: list[TradeOffer] = []
            descriptions = data.get("descriptions", ())
            trade = None
            for trade in data.get("trades", []):
                if not after_timestamp < trade["time_init"] < before_timestamp:
                    break
                for item in descriptions:
                    for asset in trade.get("assets_received", []):
                        if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                            asset.update(item)
                    for asset in trade.get("assets_given", []):
                        if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                            asset.update(item)

                trades.append(TradeOffer._from_history(state=self._state, data=trade))

            assert trade is not None
            previous_time = trade["time_init"]
            for trade, partner in zip(trades, await self._state._maybe_users(trade.partner for trade in trades)):
                trade.partner = partner
            return trades

        for trade in await get_trades():
            for item in trade.items_to_receive:
                item.owner = trade.partner
            if limit is not None and yielded >= limit:
                return
            yield trade
            yielded += 1

        if total < 100:
            for page in range(200, math.ceil((total + 100) / 100) * 100, 100):
                for trade in await get_trades(page):
                    for item in trade.items_to_receive:
                        item.owner = trade.partner
                    if limit is not None and yielded >= limit:
                        return
                    yield trade
                    yielded += 1

    async def change_presence(
        self,
        *,
        app: App | None = None,
        apps: list[App] | None = None,
        state: PersonaState | None = None,
        ui_mode: UIMode | None = None,
        flags: PersonaStateFlag | None = None,
        force_kick: bool = False,
    ) -> None:
        """Set your status.

        Parameters
        ----------
        app
            An app to set your status as.
        apps
            A list of apps to set your status to.
        state
            The state to show your account as.

            Warning
            -------
            Setting your status to :attr:`~steam.PersonaState.Offline`, will stop you receiving persona state updates
            and by extension :meth:`on_user_update` will stop being dispatched.

        ui_mode
            The UI mode to set your status to.
        flags
            The flags to update your account with.
        force_kick
            Whether to forcefully kick any other playing sessions.
        """
        apps_ = [app.to_proto() for app in apps] if apps is not None else []
        if app is not None:
            apps_.append(app.to_proto())
        await self.ws.change_presence(apps=apps_, state=state, flags=flags, ui_mode=ui_mode, force_kick=force_kick)

    async def trade_url(self, generate_new: bool = False) -> TradeURLInfo:
        """Fetches this account's trade url.

        Parameters
        ----------
        generate_new
            Whether or not to generate a new trade token, defaults to ``False``.
        """
        info = utils.parse_trade_url(await self._state.fetch_trade_url(generate_new))
        assert info is not None
        return info

    async def wait_until_ready(self) -> None:
        """Waits until the client's internal cache is all ready."""
        await self._ready.wait()

    async def fetch_price(self, name: str, app: App, currency: int | None = None) -> PriceOverview:
        """Fetch the :class:`PriceOverview` for an item.

        Parameters
        ----------
        name
            The name of the item.
        app
            The app the item is from.
        currency
            The currency to fetch the price in.
        """
        price = await self.http.get_price(app.id, name, currency)
        return PriceOverview(price)

    # events to be subclassed

    async def on_error(self, event: str, error: Exception, *args: object, **kwargs: object):
        """The default error handler provided by the client.

        Usually when an event raises an uncaught exception, a traceback is printed to :attr:`sys.stderr` and the
        exception is ignored. If you want to change this behaviour and handle the exception yourself, this event can
        be overridden. Which, when done, will suppress the default action of printing the traceback.

        If you want exception to propagate out of the :class:`Client` class you can define an ``on_error`` handler
        consisting of a single empty :ref:`py:raise`. Exceptions raised by ``on_error`` will not be handled in any
        way by :class:`Client`.

        Parameters
        ----------
        event
            The name of the event that errored.
        error
            The error that was raised.
        args
            The positional arguments associated with the event.
        kwargs
            The key-word arguments associated with the event.
        """
        print(f"Ignoring exception in {event}", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if TYPE_CHECKING or DOCS_BUILDING:
        # these methods shouldn't exist at runtime unless subclassed to prevent pollution of logs

        async def on_connect(self) -> None:
            """Called when the client has successfully connected to Steam. This is not the same as the client being
            fully prepared, see :func:`on_ready` for that.

            The warnings on :meth:`on_ready` also apply.
            """

        async def on_disconnect(self) -> None:
            """Called when the client has disconnected from Steam. This could happen either through the internet
            disconnecting, an explicit call to logout, or Steam terminating the connection.

            This function can be called multiple times.
            """

        async def on_ready(self) -> None:
            """Called after a successful login and the client has handled setting up everything.

            Warning
            -------
            This function is not guaranteed to be the first event called. Likewise, this function is **not** guaranteed
            to only be called once. This library implements reconnection logic and will therefore end up calling this
            event whenever a CM disconnects.
            """

        async def on_login(self) -> None:
            """Called when the client has logged into https://steamcommunity.com."""

        async def on_logout(self) -> None:
            """Called when the client has logged out of https://steamcommunity.com."""

        async def on_message(self, message: "steam.Message") -> None:
            """Called when a message is created.

            Parameters
            ----------
            message
                The message that was received.
            """

        async def on_typing(self, user: "steam.User", when: "datetime.datetime") -> None:
            """Called when typing is started.

            Parameters
            ----------
            user
                The user that started typing.
            when
                The time the user started typing at.
            """

        async def on_reaction_add(self, reaction: MessageReaction) -> None:
            """Called when a reaction is added to a message.

            Parameters
            ----------
            reaction
                The reaction that was added.
            """

        async def on_reaction_remove(self, reaction: MessageReaction) -> None:
            """Called when a reaction is removed from a message.

            Parameters
            ----------
            reaction
                The reaction that was removed.
            """

        async def on_trade_receive(self, trade: "steam.TradeOffer") -> None:
            """Called when the client receives a trade offer.

            Parameters
            ----------
            trade
                The trade offer that was received.
            """

        async def on_trade_send(self, trade: "steam.TradeOffer") -> None:
            """Called when the client sends a trade offer.

            Parameters
            ----------
            trade
                The trade offer that was sent.
            """

        async def on_trade_accept(self, trade: "steam.TradeOffer") -> None:
            """Called when the client or the trade partner accepts a trade offer.

            Parameters
            ----------
            trade
                The trade offer that was accepted.
            """

        async def on_trade_decline(self, trade: "steam.TradeOffer") -> None:
            """Called when the client or the trade partner declines a trade offer.

            Parameters
            ----------
            trade
                The trade offer that was declined.
            """

        async def on_trade_cancel(self, trade: "steam.TradeOffer") -> None:
            """Called when the client or the trade partner cancels a trade offer.

            Note
            ----
            This is called when the trade state becomes :attr:`~steam.TradeOfferState.Canceled` and
            :attr:`~steam.TradeOfferState.CanceledBySecondaryFactor`.

            Parameters
            ----------
            trade
                The trade offer that was cancelled.
            """

        async def on_trade_expire(self, trade: "steam.TradeOffer") -> None:
            """Called when a trade offer expires due to being active for too long.

            Parameters
            ----------
            trade
                The trade offer that expired.
            """

        async def on_trade_counter(self, trade: "steam.TradeOffer") -> None:
            """Called when the client or the trade partner counters a trade offer.

            Parameters
            ----------
            trade
                The trade offer that was countered.
            """

        async def on_comment(self, comment: "steam.Comment") -> None:
            """Called when the client receives a comment notification.

            Parameters
            ----------
            comment
                The comment received.
            """

        async def on_user_invite(self, invite: "steam.UserInvite") -> None:
            """Called when the client receives/sends an invite from/to a :class:`~steam.User` to become a friend.

            Parameters
            ----------
            invite
                The invite received.
            """

        async def on_user_invite_accept(self, invite: "steam.UserInvite") -> None:
            """Called when the client/invitee accepts an invite from/to a :class:`~steam.User` to become a friend.

            Parameters
            ----------
            invite
                The invite that was accepted.
            """

        async def on_user_invite_decline(self, invite: "steam.UserInvite") -> None:
            """Called when the client/invitee declines an invite from/to a :class:`~steam.User` to become a friend.

            Parameters
            ----------
            invite
                The invite that was declined.
            """

        async def on_user_update(self, before: "steam.User", after: "steam.User") -> None:
            """Called when a user is updated, due to one or more of the following attributes changing:

                - :attr:`~steam.User.name`
                - :attr:`~steam.User.state`
                - :attr:`~steam.User.flags`
                - :attr:`~steam.User.avatar_url`
                - :attr:`~steam.User.last_logon`
                - :attr:`~steam.User.last_logoff`
                - :attr:`~steam.User.last_seen_online`
                - :attr:`~steam.User.app`

            Parameters
            ----------
            before
                The user's state before it was updated.
            after
                The user's state now.
            """

        async def on_friend_add(self, friend: "steam.Friend") -> None:
            """Called when a friend is added to the client's friends list.

            Parameters
            ----------
            friend
                The friend that was added.
            """

        async def on_friend_remove(self, friend: "steam.Friend") -> None:
            """Called when you or the ``friend`` remove each other from your friends lists.

            Parameters
            ----------
            friend
                The friend who was removed.
            """

        async def on_clan_invite(self, invite: "steam.ClanInvite") -> None:
            """Called when the client receives/sends an invite from/to a :class:`~steam.User` to join a
            :class:`~steam.Clan`.

            Parameters
            ----------
            invite
                The invite received.
            """

        async def on_clan_invite_accept(self, invite: "steam.ClanInvite") -> None:
            """Called when the client/invitee accepts an invite to join a :class:`~steam.Clan`.

            Parameters
            ----------
            invite
                The invite that was accepted.
            """

        async def on_clan_invite_decline(self, invite: "steam.ClanInvite") -> None:
            """Called when the client/invitee declines an invite to join a :class:`~steam.Clan`.

            Parameters
            ----------
            invite
                The invite that was declined.
            """

        async def on_clan_join(self, clan: "steam.Clan") -> None:
            """Called when the client joins a new clan.

            Parameters
            ----------
            clan
                The joined clan.
            """

        async def on_clan_update(self, before: "steam.Clan", after: "steam.Clan") -> None:
            """Called when a clan is updated, due to one or more of the following attributes changing:

                - :attr:`~steam.Clan.name`
                - :attr:`~steam.Clan.avatar_url`
                - :attr:`~steam.Clan.member_count`
                - :attr:`~steam.Clan.in_game_count`
                - :attr:`~steam.Clan.online_count`
                - :attr:`~steam.Clan.active_member_count`

            Parameters
            ----------
            before
                The clan's state before it was updated.
            after
                The clan's state now.
            """

        async def on_clan_leave(self, clan: "steam.Clan") -> None:
            """Called when the client leaves a clan.

            Parameters
            ----------
            clan
                The left clan.
            """

        async def on_group_join(self, group: "steam.Group") -> None:
            """Called when the client joins a new group.

            Parameters
            ----------
            group
                The joined group.
            """

        async def on_group_update(self, before: "steam.Group", after: "steam.Group") -> None:
            """Called when a group is updated.

            Parameters
            ----------
            before
                The group's state before it was updated.
            after
                The group's state now.
            """

        async def on_group_leave(self, group: "steam.Group") -> None:
            """Called when the client leaves a group.

            Parameters
            ----------
            group
                The left group.
            """

        async def on_event_create(self, event: "steam.Event") -> None:
            """Called when an event in a clan is created.

            Parameters
            ----------
            event
                The event that was created.
            """

        async def on_announcement_create(self, announcement: "steam.Announcement") -> None:
            """Called when an announcement in a clan is created.

            Parameters
            ----------
            announcement
                The announcement that was created.
            """

        async def on_socket_receive(self, msg: "Message | ProtobufMessage") -> None:
            """Called when the connected CM parses a received a message.

            Parameters
            ----------
            msg
                The received message.
            """

        async def on_socket_send(self, msg: "Message | ProtobufMessage") -> None:
            """Called when the client sends a message to the connected CM.

            Parameters
            ----------
            msg
                The sent message.
            """

    @overload
    async def wait_for(
        self,
        event: Literal[
            "connect",
            "disconnect",
            "ready",
            "login",
            "logout",
        ],
        *,
        check: Callable[[], bool] = ...,
        timeout: float | None = ...,
    ) -> None:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["error"],
        *,
        check: Callable[[str, Exception, tuple[Any, ...], dict[str, Any]], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[str, Exception, tuple[Any, ...], dict[str, Any]]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["message"],
        *,
        check: Callable[[Message], bool] = ...,
        timeout: float | None = ...,
    ) -> Message:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["comment"],
        *,
        check: Callable[[Comment], bool] = ...,
        timeout: float | None = ...,
    ) -> Comment:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["user_update"],
        *,
        check: Callable[[User, User], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[User, User]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["clan_update"],
        *,
        check: Callable[[Clan, Clan], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[Clan, Clan]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["group_update"],
        *,
        check: Callable[[Group, Group], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[Group, Group]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["typing"],
        *,
        check: Callable[[User, datetime.datetime], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[User, datetime.datetime]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "trade_receive",
            "trade_send",
            "trade_accept",
            "trade_decline",
            "trade_cancel",
            "trade_expire",
            "trade_counter",
        ],
        *,
        check: Callable[[TradeOffer], bool] = ...,
        timeout: float | None = ...,
    ) -> TradeOffer:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "user_invite",
            "user_invite_accept",
            "user_invite_decline",
        ],
        *,
        check: Callable[[UserInvite], bool] = ...,
        timeout: float | None = ...,
    ) -> UserInvite:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "friend_add",
            "friend_remove",
        ],
        *,
        check: Callable[[Friend], bool] = ...,
        timeout: float | None = ...,
    ) -> User:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "clan_invite",
            "clan_invite_accept",
            "clan_invite_decline",
        ],
        *,
        check: Callable[[ClanInvite], bool] = ...,
        timeout: float | None = ...,
    ) -> ClanInvite:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "clan_join",
            "clan_leave",
        ],
        *,
        check: Callable[[Clan], bool] = ...,
        timeout: float | None = ...,
    ) -> Clan:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "group_join",
            "group_leave",
        ],
        *,
        check: Callable[[Group], bool] = ...,
        timeout: float | None = ...,
    ) -> Group:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["event_create"],
        *,
        check: Callable[[Event], bool] = ...,
        timeout: float | None = ...,
    ) -> Event:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["announcement_create"],
        *,
        check: Callable[[Announcement], bool] = ...,
        timeout: float | None = ...,
    ) -> Announcement:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "socket_receive",
            "socket_send",
        ],
        *,
        check: Callable[[Msgs], bool] = ...,
        timeout: float | None = ...,
    ) -> Msgs:
        ...

    async def wait_for(
        self,
        event: str,
        *,
        check: Callable[..., bool] = return_true,
        timeout: float | None = None,
    ) -> Any:
        """Wait for the first event to be dispatched that meets the requirements, this by default is the first event
        with a matching event name.

        Parameters
        ----------
        event
            The event name from the :ref:`event reference <event-reference>`, but without the ``on_`` prefix, to wait
            for.
        check
            A callable predicate that checks the received event. The arguments must match the parameters of the
            ``event`` being waited for and must return a :class:`bool`.
        timeout
            By default, :meth:`wait_for` function does not timeout, however, in the case a ``timeout`` parameter is
            passed after the amount of seconds passes :exc:`asyncio.TimeoutError` is raised.

        Raises
        ------
        :exc:`asyncio.TimeoutError`
            If the provided timeout was reached.

        Returns
        -------
        Returns ``None``, a single argument or a :class:`tuple` of multiple arguments that mirrors the parameters for
        the ``event`` parameter from the :ref:`event reference <event-reference>`.
        """
        future = self.loop.create_future()

        event_lower = event.lower()
        try:
            listeners = self._listeners[event_lower]
        except KeyError:
            listeners = []
            self._listeners[event_lower] = listeners

        listeners.append((future, check))
        return await asyncio.wait_for(future, timeout)
