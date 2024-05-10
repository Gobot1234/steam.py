"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/Rapptz/discord.py/blob/master/discord/client.py
The appropriate license is in LICENSE
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import random
import sys
import time
import traceback
from collections.abc import AsyncGenerator, Callable, Collection, Coroutine, Iterable, Sequence
from contextlib import nullcontext
from ipaddress import IPv4Address
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    Literal,
    ParamSpec,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
    final,
    overload,
)

from yarl import URL as URL_

from . import utils
from ._const import DOCS_BUILDING, STATE, UNIX_EPOCH, URL, TaskGroup, timeout
from .achievement import UserNewsAchievement
from .app import App, AppListApp, AuthenticationTicket, FetchedApp, PartialApp
from .bundle import Bundle, FetchedBundle, PartialBundle
from .chat import ChatGroup
from .enums import *
from .errors import WSException
from .game_server import GameServer, Query
from .gateway import *
from .guard import get_authentication_code
from .http import HTTPClient
from .id import _ID64_TO_ID32
from .models import CDNAsset, PriceOverview, Wallet, return_true
from .package import FetchedPackage, License, Package, PartialPackage
from .protobufs import store
from .state import ConnectionState
from .store import AppStoreItem, BundleStoreItem, PackageStoreItem, TransactionReceipt
from .types.id import ID64, AppID, BundleID, PackageID, PublishedFileID, TradeOfferID
from .user_news import UserNews
from .utils import DateTime, TradeURLInfo

if TYPE_CHECKING:
    import datetime
    from ssl import SSLContext

    import aiohttp
    from typing_extensions import Self, Unpack

    import steam
    from steam.ext import commands

    from .abc import Message
    from .clan import Clan
    from .comment import Comment
    from .event import Announcement, Event
    from .ext.commands.bot import Bot
    from .friend import Friend
    from .group import Group
    from .invite import AppInvite, ClanInvite, GroupInvite, UserInvite
    from .manifest import AppInfo, PackageInfo
    from .media import Media
    from .post import Post
    from .published_file import PublishedFile
    from .reaction import ClientEffect, ClientEmoticon, ClientSticker, MessageReaction
    from .trade import Asset, Item, MovedItem, TradeOffer
    from .types.http import IPAdress
    from .types.user import IndividualID
    from .user import ClientUser, User


__all__ = ("Client",)

log = logging.getLogger(__name__)

CoroFunc: TypeAlias = Callable[..., Coroutine[Any, Any, Any]]
F = TypeVar("F", bound=CoroFunc)
P = ParamSpec("P")


class ClientKwargs(TypedDict, total=False):
    proxy: str | None
    proxy_auth: aiohttp.BasicAuth | None
    connector: aiohttp.BaseConnector | None
    intents: Intents
    max_messages: int | None
    app: App | None
    apps: list[App]
    state: PersonaState
    ui_mode: UIMode
    flags: PersonaStateFlag
    force_kick: bool
    language: Language
    auto_chunk_chat_groups: bool
    ssl: SSLContext | Literal[False] | aiohttp.Fingerprint


class Client:
    """Represents a client connection that connects to Steam. This class is used to interact with the Steam API and CMs.

    .. container:: operations

        .. describe:: async with x

            Initialises the client and closes it when the context is exited.

    Parameters
    ----------
    proxy
        A proxy URL to use for requests.
    proxy_auth
        The proxy authentication to use with requests.
    connector
        The connector to use with the :class:`aiohttp.ClientSession`.
    intents
        The intents you wish to start the client with.
    max_messages
        The maximum number of messages to store in the internal cache, default is 1000.
    app
        An app to set your status as on connect. This will take precedence over any apps set using ``apps`` as your
        current status.
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
    ssl
        Any ``ssl`` parameters to pass to the underlying :class:`~aiohttp.ClientSession`.

        .. versionadded:: 1.0.1
    """

    def __init__(self, **options: Unpack[ClientKwargs]):
        self.http = HTTPClient(client=self, **options)
        self._state = self._get_state(**options)
        self.ws: SteamWebSocket | None = None

        self.username: str | None = None
        self.password: str | None = None
        self.shared_secret: str | None = None
        self.identity_secret: str | None = None

        self._closed = True
        self._listeners: dict[str, list[tuple[asyncio.Future[Any], Callable[..., bool]]]] = {}
        self._ready = asyncio.Event()
        self._aentered = False

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
    def trades(self) -> Sequence[TradeOffer[Asset[User], Asset[ClientUser], User]]:
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
    def effects(self) -> Sequence[ClientEffect]:
        """A read-only list of all the effects the client has."""
        return self._state.effects

    @property
    def latency(self) -> float:
        """Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return float("nan") if self.ws is None else self.ws.latency

    @property
    def refresh_token(self) -> str | None:
        """The refresh token for the logged in account, can be used to login."""
        return None if self.ws is None else self.ws.refresh_token

    @property
    def wallet(self) -> Wallet:
        """The wallet info for the logged in account."""
        return self._state.wallet

    async def code(self) -> str:
        """Get the current steam guard code.

        Warning
        -------
        This will read from :attr:`sys.stdin` if no `shared_secret` was passed to :meth:`login`.
        """
        if self.shared_secret:
            return get_authentication_code(self.shared_secret)
        code = await utils.ainput(">>> ")
        return code.strip()

    def is_ready(self) -> bool:
        """Specifies if the client's internal cache is ready for use."""
        return self._ready.is_set()

    def is_closed(self) -> bool:
        """Indicates if connection is closed to the WebSocket."""
        return self._closed

    def event(self, coro: F) -> F:
        """A decorator that registers an event to listen to.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Usage:

        .. code:: python

            @client.event
            async def on_ready():
                print("Ready!")

        Raises
        ------
        :exc:`TypeError`
            The function passed is not a coroutine.
        """

        if not inspect.iscoroutinefunction(coro):
            raise TypeError(f"Registered events must be coroutine functions, {coro.__name__} is {type(coro).__name__}")

        setattr(self, coro.__name__, coro)
        log.debug("%s has been registered as an event", coro.__name__)
        return coro

    async def _run_event(self, coro: CoroFunc, event_name: str, *args: Any, **kwargs: Any) -> None:
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            try:
                await self.on_error(event_name, exc, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    def _schedule_event(self, coro: CoroFunc, event_name: str, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        return self._tg.create_task(
            self._run_event(coro, event_name, *args, **kwargs), name=f"steam.py task: {event_name}"
        )

    def dispatch(self, event: str, /, *args: Any, **kwargs: Any) -> None:
        log.debug("Dispatching event %s", event)
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

    async def __aenter__(self) -> Self:
        self._tg = TaskGroup()
        self._aentered = True
        await self._tg.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if not self.is_closed():
            await self.close()
        if self._aentered:
            await self._tg.__aexit__(*args)

    @overload
    @final
    def run(
        self,
        username: str,
        password: str,
        *,
        shared_secret: str = ...,
        identity_secret: str = ...,
        debug: bool = ...,
    ) -> object: ...

    @overload
    @final
    def run(
        self,
        *,
        refresh_token: str,
        shared_secret: str = ...,
        identity_secret: str = ...,
        debug: bool = ...,
    ) -> object: ...

    @final
    def run(self, *args: Any, debug: bool = False, **kwargs: Any) -> object:
        """A blocking method to start and run the client.

        Shorthand for:

        .. code:: python

            async def main():
                async with client:
                    await client.login(...)


            asyncio.run(main())

        It is not recommended to subclass this method, it is normally favourable to subclass :meth:`login` as it is a
        :ref:`coroutine <coroutine>`.

        Note
        ----
        This takes the same arguments as :meth:`login`.
        """

        async def runner() -> None:
            async with self:
                await self.login(*args, **kwargs)

        try:
            asyncio.run(runner(), debug=debug)
        except KeyboardInterrupt:
            log.info("Closing the event loop")

    async def close(self) -> None:
        """Close the connection to Steam."""
        if self.is_closed():
            return

        self._closed = True

        if self.ws is not None:
            try:
                if self._state._active_auth_tickets:
                    self._state._active_auth_tickets.clear()
                    await self._state.deactivate_auth_session_tickets()
                await self.change_presence(apps=[])  # disconnect from games
                await self._state.handle_close()
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
        if not self._aentered:
            self._tg = TaskGroup()

    async def _login(
        self,
        login_func: Callable[Concatenate[Self, P], Coroutine[None, None, SteamWebSocket]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> None:
        self.clear()
        async with nullcontext() if self._aentered else self._tg:
            state = self._state
            STATE.set(state)
            cm_list = None

            async def throttle() -> None:
                now = time.monotonic()
                between = now - last_connect
                sleep = random.random() * 4 if between > 300 else min(100 / between**0.5, 20)
                log.info("Attempting to connect to another CM in %ds", sleep)
                await asyncio.sleep(sleep)

            async def poll() -> None:
                while True:
                    await state.ws.poll_event()

            async def dispatch_ready() -> None:
                if state.intents & Intents.ChatGroups > 0:
                    await state.handled_chat_groups.wait()  # ensure group cache is ready
                if state.intents & Intents.ChatGroups > 0:
                    # due to a steam limitation we can't get these reliably on reconnect?  TODO check?
                    await state.handled_friends.wait()  # ensure friend cache is ready
                await state.handled_emoticons.wait()  # ensure emoticon cache is ready
                await state.handled_licenses.wait()  # ensure licenses are ready
                await state.handled_wallet.wait()  # ensure wallet is ready

                await self._handle_ready()

            while not self.is_closed():
                last_connect = time.monotonic()

                try:
                    async with timeout(60):
                        self.ws = cast(SteamWebSocket, await login_func(self, *args, **kwargs, cm_list=cm_list))  # type: ignore
                except RAISED_EXCEPTIONS:
                    if self.ws:
                        cm_list = self.ws.cm_list
                    await throttle()
                    continue

                if login_func != SteamWebSocket.anonymous_login_from_client:
                    self._tg.create_task(dispatch_ready())

                # this entire thing is a bit of a cluster fuck
                # but that's what you deserve for having async parsers

                # this future holds the future that finished first. either poll_task for a WS exception or callback_error for errors that occur in state.parsers
                done: asyncio.Future[asyncio.Future[None]] = asyncio.get_running_loop().create_future()

                poll_task = asyncio.create_task(poll())
                callback_error = state._task_error

                def maybe_set_result(future: asyncio.Future[None]) -> None:
                    if not done.done():
                        done.set_result(future)
                    else:
                        try:
                            future.exception()  # mark the exception as retrieved (the other set task should raise the error)
                        except asyncio.CancelledError:
                            pass

                poll_task.add_done_callback(maybe_set_result)
                callback_error.add_done_callback(maybe_set_result)

                try:
                    task = await done  # get which task is done
                except asyncio.CancelledError:  # KeyboardInterrupt
                    if not self.is_closed():
                        try:
                            await self.close()
                        except asyncio.CancelledError:
                            pass
                    for task in (poll_task, callback_error):  # cancel them
                        task.cancel()
                    await asyncio.gather(
                        poll_task, callback_error, return_exceptions=True
                    )  # and collect the results so that the event loop won't raise
                    return

                to_cancel = poll_task if task is callback_error else callback_error  # cancel the other task
                to_cancel.cancel()
                for task_ in self.ws._pending_parsers:
                    task_.cancel()
                await asyncio.gather(
                    *self.ws._pending_parsers, to_cancel, return_exceptions=True
                )  # same sort of thing as above gather
                self.ws._pending_parsers.clear()
                try:
                    await task  # handle the exception raised
                except (*RAISED_EXCEPTIONS, asyncio.CancelledError):
                    self.dispatch("disconnect")
                    if not self.is_closed():
                        await throttle()
                state._task_error = asyncio.get_running_loop().create_future()

    @overload
    async def login(
        self,
        username: str,
        password: str,
        *,
        shared_secret: str = ...,
        identity_secret: str = ...,
    ) -> None: ...

    @overload
    async def login(
        self,
        *,
        refresh_token: str,
        shared_secret: str = ...,
        identity_secret: str = ...,
    ) -> None: ...

    async def login(
        self,
        username: str | None = None,
        password: str | None = None,
        *,
        shared_secret: str | None = None,
        identity_secret: str | None = None,
        refresh_token: str | None = None,
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
        refresh_token
            The refresh token of the account to login to.
        """
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        if identity_secret is None:
            log.info("Trades will not be automatically accepted when sent as no identity_secret was passed.")

        await self._login(SteamWebSocket.from_client, refresh_token=refresh_token or self.refresh_token)

    async def anonymous_login(self) -> None:
        """Initialize a connection to a Steam CM and login anonymously."""
        await self._login(SteamWebSocket.anonymous_login_from_client)

    # state stuff
    def get_user(self, id: int, /) -> User | None:
        """Returns a user from cache with a matching ID or ``None`` if the user was not found.

        Parameters
        ----------
        id
            The ID64 of the user.
        """
        return self._state.get_user(_ID64_TO_ID32(id))

    async def fetch_user(self, id: int, /) -> User:
        """Fetches a user with a matching ID.

        Parameters
        ----------
        id
            The ID64 of the user.
        """
        return await self._state.fetch_user(ID64(id))

    async def fetch_users(self, *ids: int) -> Sequence[User]:
        """Fetches a list of :class:`~steam.User`.

        Note
        ----
        The :class:`~steam.User` objects returned are unlikely to retain the order they were originally in.

        Parameters
        ----------
        ids
            The user's ID64s.
        """
        return await self._state.fetch_users(cast("tuple[ID64, ...]", ids))

    def get_trade(self, id: int, /) -> TradeOffer | None:
        """Get a trade from cache with a matching ID or ``None`` if the trade was not found.

        Parameters
        ----------
        id
            The ID of the trade to search for from the cache.
        """
        return self._state.get_trade(TradeOfferID(id))

    async def fetch_trade(
        self, id: int, /, *, language: Language | None = None
    ) -> TradeOffer[Item[User], Item[ClientUser], User] | None:
        """Fetches a trade with a matching ID or ``None`` if the trade was not found.

        Parameters
        ----------
        id
            The ID of the trade to search for from the API.
        language
            The language to fetch the trade in. ``None`` uses the current language.
        """
        return await self._state.fetch_trade(TradeOfferID(id), language)

    def get_group(self, id: int, /) -> Group | None:
        """Get a group from cache with a matching ID or ``None`` if the group was not found.

        Parameters
        ----------
        id
            The ID64 of the group.
        """
        return self._state.get_group(_ID64_TO_ID32(id))

    def get_clan(self, id: int, /) -> Clan | None:
        """Get a clan from cache with a matching ID or ``None`` if the group was not found.

        Parameters
        ----------
        id
            The ID64 of the clan.
        """
        return self._state.get_clan(_ID64_TO_ID32(id))

    async def fetch_clan(self, id: int, /) -> Clan:
        """Fetches a clan from the websocket with a matching ID.

        Parameters
        ----------
        id
            The ID64 of the clan.
        """
        return await self._state.fetch_clan(ID64(id))

    async def create_clan(
        self,
        name: str,
        /,
        *,
        abbreviation: str | None = None,
        community_url: URL_ | str | None = None,
        public: bool = True,
        headline: str | None = None,
        summary: str | None = None,
        language: Language | None = None,
        country: str | None = None,
        state: str | None = None,
        city: str | None = None,
        apps: Iterable[App] | None = None,
        avatar: Media | None = None,
    ) -> Clan:
        """Create a clan.

        Parameters
        ----------
        name
            The name of the clan.
        avatar
            The avatar of the clan.
        abbreviation
            The abbreviation of the clan.
        community_url
            The community URL of the clan.
        public
            Whether the clan is public.
        headline
            The headline of the clan.
        summary
            The summary of the clan.
        language
            The language of the clan.
        country
            The country of the clan.
        state
            The state of the clan.
        city
            The city of the clan.
        apps
            The apps the clan is associated with.
        """
        if isinstance(community_url, str):
            community_url = URL_(community_url)
        if community_url is not None:
            community_url = community_url.parts[-1] or community_url.parts[-2]

        id64 = await self.http.create_clan(name, abbreviation, community_url, public)
        clan = await self._state._maybe_clan(id64, create=True)  # should just be created by steam for us
        await clan.edit(
            headline=headline,
            summary=summary,
            language=language,
            country=country,
            state=state,
            city=city,
            apps=apps,
            avatar=avatar,
        )
        try:
            await ChatGroup.join(clan)  # type: ignore  # should be removed one day
        except WSException:
            log.debug("Failed to join clan chat group", exc_info=True)
        return clan

    async def create_group(
        self,
        name: str,
        /,
        *,
        members: Iterable[IndividualID],
        avatar: Media | None = None,
        tagline: str | None = None,
    ) -> Group:
        """Create a group.

        Parameters
        ----------
        name
            The name of the group.
        members
            The members to add to the group.
        avatar
            The avatar of the group.
        tagline
            The tagline of the group.
        """
        group = await self._state.create_group(name, members)
        await group.edit(tagline=tagline, avatar=avatar)
        return group

    def get_app(self, id: int, /) -> PartialApp[None]:
        """Creates a :class:`PartialApp` instance from its ID.

        Parameters
        ----------
        id
            The app id of the app.
        """
        return PartialApp(self._state, id=id)

    async def fetch_app(self, id: int, /, *, language: Language | None = None) -> FetchedApp:
        """Fetch an app from its ID.

        Parameters
        ----------
        id
            The app id of the app.
        language
            The language to fetch the app in. If ``None`` uses the current language.

        Raises
        ------
        ValueError
            Passed `id` isn't for a valid app.
        """
        return await self._state.fetch_app(AppID(id), language)

    def get_package(self, id: int, /) -> PartialPackage:
        """Creates a :class:`PartialPackage` from its ID.

        Parameters
        ----------
        id
            The ID of the package.
        """
        return PartialPackage(self._state, id=id)

    async def fetch_package(self, id: int, /, *, language: Language | None = None) -> FetchedPackage:
        """Fetch a package from its ID.

        Parameters
        ----------
        id
            The ID of the package.
        language
            The language to fetch the package in. If ``None`` uses the current language.

        Raises
        ------
        ValueError
            Passed `id` isn't for a valid package.
        """
        return await self._state.fetch_package(PackageID(id), language)

    async def redeem_package(self, id: int, /) -> License:
        """Redeem a promotional free licenses package from its ID.

        Parameters
        ----------
        id
            The ID of the package to redeem.
        """
        id = PackageID(id)
        future: asyncio.Future[License] = asyncio.get_running_loop().create_future()
        async with self._state._license_lock:
            self._state.licenses_being_waited_for[id] = future
            await self.http.redeem_package(id)
            return await future

    def get_bundle(self, id: int, /) -> PartialBundle:
        """Creates a :class:`PartialBundle` instance from its ID.

        Parameters
        ----------
        id
            The ID of the bundle.
        """
        return PartialBundle(self._state, id=id)

    async def fetch_bundle(self, id: int, /, *, language: Language | None = None) -> FetchedBundle:
        """Fetch a bundle from its ID.

        Parameters
        ----------
        id
            The ID of the bundle.
        language
            The language to fetch the bundle in. If ``None`` uses the current language.
        """
        return await self._state.fetch_bundle(BundleID(id), language)

    @overload
    async def fetch_server(self, *, id: int) -> GameServer | None: ...

    @overload
    async def fetch_server(
        self,
        *,
        ip: IPAdress | str,
        port: int | None = None,
    ) -> GameServer | None: ...

    async def fetch_server(
        self,
        *,
        id: int | None = None,
        ip: IPAdress | str | None = None,
        port: int | str | None = None,
    ) -> GameServer | None:
        """Fetch a :class:`.GameServer` from its ip and port or its Steam ID or ``None`` if fetching the server failed.

        Parameters
        ----------
        ip
            The ip of the server.
        port
            The port of the server.
        id
            The ID64 of the game server. If passed, it makes a call to the master server to fetch its ip and port.

        Note
        ----
        Passing an ``ip``, ``port`` and ``id`` to this function will raise an :exc:`TypeError`.
        """

        if id is not None and ip is not None:
            raise TypeError("Too many arguments passed to fetch_server")
        if id:
            # we need to fetch the ip and port
            servers = await self._state.fetch_server_ip_from_steam_id(ID64(id))
            if not servers:
                raise ValueError(f"The master server didn't find a matching server for {id}")
            ip_, _, port = servers[0].addr.rpartition(":")
            ip = IPv4Address(ip_)
        elif not ip:
            raise TypeError("fetch_server missing argument ip")

        servers = await self.fetch_servers(Query.where(ip=f"{ip}{f':{port}' if port is not None else ''}"), limit=1)
        return servers[0] if servers else None

    async def fetch_servers(self, query: str | None = None, /, *, limit: int = 100) -> list[GameServer]:
        """Query game servers.

        Parameters
        ----------
        query
            The query to match servers with. If None returns all servers.
        limit
            The maximum amount of servers to return.

        See Also
        --------
        :meth:`.Query.where` to generate these programmatically.
        """
        servers = await self._state.fetch_servers(query or "", limit)
        return [GameServer(self._state, server) for server in servers]

    # content server related stuff

    @overload
    async def fetch_product_info(self, *, apps: Collection[App]) -> list[AppInfo]: ...

    @overload
    async def fetch_product_info(self, *, packages: Collection[Package]) -> list[PackageInfo]: ...

    @overload
    async def fetch_product_info(
        self, *, apps: Collection[App], packages: Collection[Package]
    ) -> tuple[list[AppInfo], list[PackageInfo]]: ...

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

    @overload
    async def fetch_store_item(
        self, *, apps: Sequence[App], language: Language | None = None
    ) -> list[AppStoreItem]: ...

    @overload
    async def fetch_store_item(
        self, *, packages: Sequence[Package], language: Language | None = None
    ) -> list[PackageStoreItem]: ...

    @overload
    async def fetch_store_item(
        self, *, bundles: Sequence[Bundle], language: Language | None = None
    ) -> list[BundleStoreItem]: ...

    @overload
    async def fetch_store_item(
        self, *, apps: Sequence[App], packages: Sequence[Package], language: Language | None = None
    ) -> tuple[list[AppStoreItem], list[PackageStoreItem]]: ...

    @overload
    async def fetch_store_item(
        self, *, packages: Sequence[Package], bundles: Sequence[Bundle], language: Language | None = None
    ) -> tuple[list[PackageStoreItem], list[BundleStoreItem]]: ...

    @overload
    async def fetch_store_item(
        self, *, apps: Sequence[App], bundles: Sequence[Bundle], language: Language | None = None
    ) -> tuple[list[AppStoreItem], list[BundleStoreItem]]: ...

    @overload
    async def fetch_store_item(
        self,
        *,
        apps: Sequence[App],
        packages: Sequence[Package],
        bundles: Sequence[Bundle],
        language: Language | None = None,
    ) -> tuple[list[AppStoreItem], list[PackageStoreItem], list[BundleStoreItem]]: ...

    async def fetch_store_item(
        self,
        *,
        apps: Sequence[App] = (),
        packages: Sequence[Package] = (),
        bundles: Sequence[Bundle] = (),
        language: Language | None = None,
    ) -> Any:
        """Fetch store items.

        Parameters
        ----------
        apps
            The apps to fetch store items for.
        packages
            The packages to fetch store items for.
        bundles
            The bundles to fetch store items for.
        language
            The language to fetch the store items in. If ``None``, the default language is used.
        """
        if not any((apps, packages, bundles)):
            raise TypeError("fetch_store_info missing arguments apps, packages or bundles")
        resp = await self._state.fetch_store_info(
            (app.id for app in apps), (package.id for package in packages), (bundle.id for bundle in bundles), language
        )
        language = language or self.http.language
        match apps, packages, bundles:
            case [*_], (), ():  # simple cases
                return [AppStoreItem(self._state, proto, language) for proto in resp]
            case (), [*_], ():
                return [PackageStoreItem(self._state, proto, language) for proto in resp]
            case (), (), [*_]:
                return [BundleStoreItem(self._state, proto, language) for proto in resp]

            case [*_], [*_], ():  # mixed
                return [
                    AppStoreItem(self._state, proto, language)
                    for proto in resp
                    if proto.item_type == store.EStoreItemType.App
                ], [
                    PackageStoreItem(self._state, proto, language)
                    for proto in resp
                    if proto.item_type == store.EStoreItemType.Package
                ]
            case (), [*_], [*_]:
                return [
                    PackageStoreItem(self._state, proto, language)
                    for proto in resp
                    if proto.item_type == store.EStoreItemType.Package
                ], [
                    BundleStoreItem(self._state, proto, language)
                    for proto in resp
                    if proto.item_type == store.EStoreItemType.Bundle
                ]
            case [*_], (), [*_]:
                return [
                    AppStoreItem(self._state, proto, language)
                    for proto in resp
                    if proto.item_type == store.EStoreItemType.App
                ], [
                    BundleStoreItem(self._state, proto, language)
                    for proto in resp
                    if proto.item_type == store.EStoreItemType.Bundle
                ]
            case _:
                return (
                    [
                        AppStoreItem(self._state, proto, language)
                        for proto in resp
                        if proto.item_type == store.EStoreItemType.App
                    ],
                    [
                        PackageStoreItem(self._state, proto, language)
                        for proto in resp
                        if proto.item_type == store.EStoreItemType.Package
                    ],
                    [
                        BundleStoreItem(self._state, proto, language)
                        for proto in resp
                        if proto.item_type == store.EStoreItemType.Bundle
                    ],
                )

    async def register_cd_key(self, key: str, /) -> TransactionReceipt:
        """Register a CD key.

        Parameters
        ----------
        key
            The CD key to register.
        """
        proto = await self._state.register_cd_key(key)
        return TransactionReceipt(self._state, proto)

    # miscellaneous stuff

    async def fetch_published_file(
        self,
        id: int,
        /,
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
        (file,) = await self._state.fetch_published_files((PublishedFileID(id),), revision, language)
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
        return await self._state.fetch_published_files(cast(tuple[PublishedFileID, ...], ids), revision, language)

    async def create_post(self, content: str, /, app: App | None = None) -> Post[ClientUser]:
        """Create a post.

        Parameters
        ----------
        content
            The content of the post.
        app
            The app to create the post for.
        """
        await self._state.create_user_post(content, app_id=AppID(0) if app is None else app.id)
        async for entry in self.user_news(flags=UserNewsType.Friend, app=app):
            if entry.app == app and entry.actor == self.user:
                post = await entry.post()
                if post.content == content:
                    return cast("Post[ClientUser]", post)
        raise RuntimeError("Post created has no ID, this should be unreachable")

    async def user_news(
        self,
        *,
        limit: int | None = None,
        before: datetime.datetime | None = None,
        after: datetime.datetime | None = None,
        app: App | None = None,
        flags: UserNewsType | None = None,
        language: Language | None = None,
    ) -> AsyncGenerator[UserNews, None]:
        """Fetch news for the user.

        Parameters
        ----------
        limit
            The maximum number of news entries to fetch.
        before
            The date to fetch news before.
        after
            The date to fetch news after.
        app
            The app to fetch news entries related to.
        flags
            The type of news to fetch.
        language
            The language to fetch the news in. If ``None``, the current language is used.
        """
        before = original_before = before or DateTime.now()
        after = after or UNIX_EPOCH
        if flags is None:
            flags = UserNewsType.Friend if app is None else UserNewsType.App

        while True:
            msg = await self._state.fetch_user_news(flags, app.id if app is not None else None, before, after, language)

            achievements = {
                achievements.appid: {
                    achievement.name: UserNewsAchievement(
                        achievement.name,
                        PartialApp(self._state, id=achievements.appid),
                        achievement.display_name,
                        achievement.display_description,
                        CDNAsset(
                            self._state,
                            f"{URL.CDN}/steamcommunity/public/images/apps/{achievements.appid}/{achievement.icon}",
                        ),
                        achievement.hidden,
                        round(achievement.unlocked_pct, 1),
                    )
                    for achievement in achievements.achievements
                }
                for achievements in msg.achievement_display_data
            }
            if not msg.news:
                return

            for news_item in msg.news:
                news = UserNews(self._state, news_item, achievements.get(news_item.gameid, {}))
                if after < news.created_at < original_before:
                    yield news
                else:
                    return
                before = news.created_at
                if limit is not None:
                    limit -= 1
                    if limit <= 0:
                        return

    async def trade_history(
        self,
        *,
        limit: int | None = 100,
        before: datetime.datetime | None = None,
        after: datetime.datetime | None = None,
        language: Language | None = None,
        include_failed: bool = True,
    ) -> AsyncGenerator[TradeOffer[MovedItem[User], MovedItem[ClientUser], User], None]:
        """An :term:`asynchronous iterator` for accessing a :class:`steam.ClientUser`'s
        :class:`steam.TradeOffer` objects.

        Examples
        --------

        Usage:

        .. code:: python

            async for trade in client.trade_history(limit=10):
                items = [getattr(item, "name", str(item.id)) for item in trade.receiving]
                items = ", ".join(items) or "Nothing"
                print("Partner:", trade.user)
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
        include_failed
            Whether to include trades that failed.

        Yields
        ---------
        :class:`~steam.TradeOffer`
        """
        from .trade import TradeOffer

        total: int | None = None
        previous_time = 0
        after = after or UNIX_EPOCH
        before = before or DateTime.now()
        after_timestamp = after.timestamp()
        before_timestamp = before.timestamp()
        yielded = 0

        async def get_trades(
            page: int = 100,
        ) -> list[TradeOffer[MovedItem[User], MovedItem[ClientUser], User]]:
            nonlocal total, previous_time
            data = await self.http.get_trade_history(page, include_failed, previous_time, language)
            if total is None:
                total = data.get("total_trades", 0)
            if not total:
                return []

            descriptions = data.get("descriptions", ())
            trades = [
                TradeOffer._from_history(self._state, trade, descriptions)
                for trade in data.get("trades", ())
                if after_timestamp < trade["time_init"] < before_timestamp
            ]
            previous_created_at = trades[-1].created_at
            assert previous_created_at is not None
            previous_time = previous_created_at.timestamp()
            for trade, partner in zip(trades, await self._state._maybe_users(trade.user.id64 for trade in trades)):
                trade.user = partner
                for item in trade.receiving:
                    item.owner = partner
            return cast(
                "list[TradeOffer[MovedItem[User], MovedItem[ClientUser], User]]", trades
            )  # this should be safe at this point

        for trade in await get_trades():
            if limit is not None and yielded >= limit:
                return
            yield trade
            yielded += 1

        assert total is not None
        if total < 100:
            for page in range(200, math.ceil((total + 100) / 100) * 100, 100):
                for trade in await get_trades(page):
                    if limit is not None and yielded >= limit:
                        return
                    yield trade
                    yielded += 1

    async def all_apps(
        self,
        *,
        limit: int | None = None,
        modified_after: datetime.datetime | None = None,
        include_games: bool = True,
        include_dlc: bool = True,
        include_software: bool = True,
        include_videos: bool = True,
        include_hardware: bool = True,
    ) -> AsyncGenerator[AppListApp, None]:
        """An :term:`asynchronous iterator` over all the apps on Steam.

        Parameters
        ----------
        limit
            The maximum number of apps to search through. Default is ``None``. Setting this to ``None`` will fetch all
            of the apps, but this will be a very slow operation.
        modified_after
            A time to search for apps after.
        include_games
            Whether to include games.
        include_dlc
            Whether to include DLC.
        include_software
            Whether to include software.
        include_videos
            Whether to include videos.
        include_hardware
            Whether to include hardware.

        Yields
        ------
        :class:`~steam.AppListApp`
        """
        async for app in self.http.get_all_apps(
            include_games,
            include_dlc,
            include_software,
            include_videos,
            include_hardware,
            limit=limit,
            chunk_size=min(limit if limit is not None else 10_000, 50_000),
            modified_after=modified_after,
        ):
            yield AppListApp(self._state, app)

    @utils.todo
    async def all_tags(self) -> Any:
        raise NotImplementedError

    @utils.todo
    async def all_categories(self) -> Any:
        raise NotImplementedError

    @utils.todo
    async def all_genres(self) -> Any:
        raise NotImplementedError

    @utils.todo
    async def all_stickers(self) -> Any:
        raise NotImplementedError  # QueryRewardItemsRequest

    async def change_presence(
        self,
        *,
        app: App | None = None,
        apps: Iterable[App] | None = None,
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
        if self.ws is None:
            raise RuntimeError("Client is not logged in")
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

    async def fetch_price(self, name: str, app: App, currency: Currency | None = None) -> PriceOverview:
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
        return PriceOverview(price, currency or Currency.USD)

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
        traceback.print_exception(error, file=sys.stderr)

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

        async def on_message(self, message: steam.Message, /) -> None:
            """Called when a message is created.

            Parameters
            ----------
            message
                The message that was received.
            """

        async def on_typing(self, user: steam.User, when: datetime.datetime, /) -> None:
            """Called when typing is started.

            Parameters
            ----------
            user
                The user that started typing.
            when
                The time the user started typing at.
            """

        async def on_reaction_add(self, reaction: MessageReaction, /) -> None:
            """Called when a reaction is added to a message.

            Parameters
            ----------
            reaction
                The reaction that was added.
            """

        async def on_reaction_remove(self, reaction: MessageReaction, /) -> None:
            """Called when a reaction is removed from a message.

            Parameters
            ----------
            reaction
                The reaction that was removed.
            """

        async def on_trade(self, trade: steam.TradeOffer, /) -> None:
            """Called when the client sends/receives a trade offer.

            Parameters
            ----------
            trade
                The trade offer that was received/send.
            """

        async def on_trade_update(self, before: steam.TradeOffer, after: steam.TradeOffer, /) -> None:
            """Called when the client or the trade partner updates a trade offer.

            Parameters
            ----------
            before
                The trade offer that was updated prior to the update.
            after
                The trade offer now.
            """

        async def on_comment(self, comment: steam.Comment, /) -> None:
            """Called when the client receives a comment notification.

            Parameters
            ----------
            comment
                The comment received.
            """

        async def on_invite(self, invite: steam.Invite, /) -> None:
            """Called when the client receives/sends an invitation.

            Parameters
            ----------
            invite
                The invite received.
            """

        async def on_invite_accept(self, invite: steam.Invite, /) -> None:
            """Called when the client/author accepts an invitation.

            Parameters
            ----------
            invite
                The invite that was accepted.
            """

        async def on_invite_decline(self, invite: steam.Invite, /) -> None:
            """Called when the client/author declines an invitation.

            Parameters
            ----------
            invite
                The invite that was declined.
            """

        async def on_user_update(self, before: steam.User, after: steam.User, /) -> None:
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

        async def on_friend_add(self, friend: steam.Friend, /) -> None:
            """Called when a friend is added to the client's friends list.

            Parameters
            ----------
            friend
                The friend that was added.
            """

        async def on_friend_remove(self, friend: steam.Friend, /) -> None:
            """Called when you or the ``friend`` remove each other from your friends lists.

            Parameters
            ----------
            friend
                The friend who was removed.
            """

        async def on_clan_join(self, clan: steam.Clan, /) -> None:
            """Called when the client joins a new clan.

            Parameters
            ----------
            clan
                The joined clan.
            """

        async def on_clan_update(self, before: steam.Clan, after: steam.Clan, /) -> None:
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

        async def on_clan_leave(self, clan: steam.Clan, /) -> None:
            """Called when the client leaves a clan.

            Parameters
            ----------
            clan
                The left clan.
            """

        async def on_group_join(self, group: steam.Group, /) -> None:
            """Called when the client joins a new group.

            Parameters
            ----------
            group
                The joined group.
            """

        async def on_group_update(self, before: steam.Group, after: steam.Group, /) -> None:
            """Called when a group is updated.

            Parameters
            ----------
            before
                The group's state before it was updated.
            after
                The group's state now.
            """

        async def on_group_leave(self, group: steam.Group, /) -> None:
            """Called when the client leaves a group.

            Parameters
            ----------
            group
                The left group.
            """

        async def on_event_create(self, event: steam.Event, /) -> None:
            """Called when an event in a clan is created.

            Parameters
            ----------
            event
                The event that was created.
            """

        async def on_announcement_create(self, announcement: steam.Announcement, /) -> None:
            """Called when an announcement in a clan is created.

            Parameters
            ----------
            announcement
                The announcement that was created.
            """

        async def on_authentication_ticket_update(
            self, ticket: steam.AuthenticationTicket, response: steam.AuthSessionResponse, state: int, /
        ) -> None:
            """Called when the client's authentication ticket is updated.

            Parameters
            ----------
            ticket
                The updated ticket.
            response
                The response code from the CM.
            state
                The state of the ticket.
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
    ) -> None: ...

    @overload
    async def wait_for(
        self,
        event: Literal["error"],
        *,
        check: Callable[[str, Exception, tuple[Any, ...], dict[str, Any]], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[str, Exception, tuple[Any, ...], dict[str, Any]]: ...

    @overload
    async def wait_for(
        self,
        event: Literal["message"],
        *,
        check: Callable[[Message], bool] = ...,
        timeout: float | None = ...,
    ) -> Message: ...

    @overload
    async def wait_for(
        self,
        event: Literal["comment"],
        *,
        check: Callable[[Comment], bool] = ...,
        timeout: float | None = ...,
    ) -> Comment: ...

    @overload
    async def wait_for(
        self,
        event: Literal["user_update"],
        *,
        check: Callable[[User, User], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[User, User]: ...

    @overload
    async def wait_for(
        self,
        event: Literal["clan_update"],
        *,
        check: Callable[[Clan, Clan], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[Clan, Clan]: ...

    @overload
    async def wait_for(
        self,
        event: Literal["group_update"],
        *,
        check: Callable[[Group, Group], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[Group, Group]: ...

    @overload
    async def wait_for(
        self,
        event: Literal["typing"],
        *,
        check: Callable[[User, datetime.datetime], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[User, datetime.datetime]: ...

    @overload
    async def wait_for(
        self,
        event: Literal["trade"],
        *,
        check: Callable[[TradeOffer], bool] = ...,
        timeout: float | None = ...,
    ) -> TradeOffer: ...

    @overload
    async def wait_for(
        self,
        event: Literal["trade_update",],
        *,
        check: Callable[[TradeOffer, TradeOffer], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[TradeOffer, TradeOffer]: ...

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
    ) -> User: ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "invite",
            "invite_accept",
            "invite_decline",
        ],
        *,
        check: Callable[[UserInvite | ClanInvite | GroupInvite | AppInvite], bool] = ...,
        timeout: float | None = ...,
    ) -> UserInvite | ClanInvite | GroupInvite | AppInvite: ...

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
    ) -> Clan: ...

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
    ) -> Group: ...

    @overload
    async def wait_for(
        self,
        event: Literal["event_create"],
        *,
        check: Callable[[Event], bool] = ...,
        timeout: float | None = ...,
    ) -> Event: ...

    @overload
    async def wait_for(
        self,
        event: Literal["announcement_create"],
        *,
        check: Callable[[Announcement], bool] = ...,
        timeout: float | None = ...,
    ) -> Announcement: ...

    @overload
    async def wait_for(
        self,
        event: Literal["authentication_ticket_update"],
        *,
        check: Callable[[AuthenticationTicket, AuthSessionResponse, int], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[AuthenticationTicket, AuthSessionResponse, int]: ...

    @overload
    async def wait_for(
        self: Bot,
        event: Literal["command_error"],
        *,
        check: Callable[[commands.Context, Exception], bool] = ...,
        timeout: float | None = ...,
    ) -> tuple[commands.Context, Exception]: ...

    @overload
    async def wait_for(
        self: Bot,
        event: Literal[
            "command",
            "command_completion",
        ],
        *,
        check: Callable[[commands.Context], bool] = ...,
        timeout: float | None = ...,
    ) -> commands.Context: ...

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
        future = asyncio.get_running_loop().create_future()

        event_lower = event.lower()
        try:
            listeners = self._listeners[event_lower]
        except KeyError:
            listeners = []
            self._listeners[event_lower] = listeners

        listeners.append((future, check))
        return await asyncio.wait_for(future, timeout)
