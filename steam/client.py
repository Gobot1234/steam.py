"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz
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

This is a slightly modified version of discord.py's client
https://github.com/Rapptz/discord.py/blob/master/discord/client.py
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import random
import sys
import time
import traceback
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar, overload

import aiohttp
from typing_extensions import Literal, ParamSpec, TypeAlias, final

from . import errors, utils
from .abc import SteamID
from .enums import Type
from .game import FetchedGame, Game, StatefulGame
from .game_server import GameServer, Query
from .gateway import *
from .guard import generate_one_time_code
from .http import HTTPClient
from .iterators import TradesIterator
from .models import TASK_HAS_NAME, URL, PriceOverview, return_true
from .state import ConnectionState
from .utils import make_id64

if TYPE_CHECKING:
    import steam

    from .abc import Message
    from .clan import Clan
    from .comment import Comment
    from .enums import PersonaState, PersonaStateFlag, UIMode
    from .event import Announcement, Event
    from .group import Group
    from .invite import ClanInvite, UserInvite
    from .protobufs import Msg, MsgProto
    from .trade import TradeOffer
    from .user import ClientUser, User

__all__ = ("Client",)

log = logging.getLogger(__name__)
EventType: TypeAlias = "Callable[..., Coroutine[Any, Any, Any]]"
EventDeco: TypeAlias = "Callable[[E], E] | E"
E = TypeVar("E", bound=EventType)
S = ParamSpec("S", bound="Client.start")  # 90% sure this is the way to use ParamSpec


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
    game
        A games to set your status as on connect.
    games
        A list of games to set your status to on connect.
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
        Whether or not to forcefully kick any other playing sessions on connect. Defaults to ``False``.
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
        max_messages: int | None = ...,
        game: Game | None = ...,
        games: list[Game] = ...,
        state: PersonaState | None = ...,
        ui_mode: UIMode | None = ...,
        flags: PersonaStateFlag | None = ...,
        force_kick: bool = ...,
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
        self._connection = self._get_state(**options)
        self.ws: SteamWebSocket = None  # type: ignore

        self.username: str | None = None
        self.password: str | None = None
        self.shared_secret: str | None = None
        self.identity_secret: str | None = None

        self._closed = True
        self._cm_list: CMServerList | None = None
        self._listeners: dict[str, list[tuple[asyncio.Future, Callable[..., bool]]]] = {}
        self._ready = asyncio.Event()

    def _get_state(self, **options: Any) -> ConnectionState:
        return ConnectionState(client=self, **options)

    @property
    def user(self) -> ClientUser:
        """Represents the connected client. ``None`` if not logged in."""
        return self.http.user  # type: ignore

    @property
    def users(self) -> list[User]:
        """A list of all the users the connected client can see."""
        return self._connection.users

    @property
    def trades(self) -> list[TradeOffer]:
        """A list of all the trades the connected client can see."""
        return self._connection.trades

    @property
    def groups(self) -> list[Group]:
        """A list of all the groups the connected client is in."""
        return self._connection.groups

    @property
    def clans(self) -> list[Clan]:
        """A list of all the clans the connected client is in."""
        return self._connection.clans

    @property
    def latency(self) -> float:
        """Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return float("nan") if self.ws is None else self.ws.latency

    @property
    async def token(self) -> str:
        resp = await self.http.get(URL.COMMUNITY / "chat/clientjstoken")
        if not resp["logged_in"]:  # we got logged out :(
            await self.http.login(self.username, self.password, shared_secret=self.shared_secret)  # type: ignore
            return await self.token
        return resp["token"]

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

    def _schedule_event(self, coro: EventType, event_name: str, *args: Any, **kwargs: Any) -> asyncio.Task:
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        return (
            self.loop.create_task(wrapped, name=f"task_{event_name}")
            if TASK_HAS_NAME
            else self.loop.create_task(wrapped)
        )

    def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        log.debug(f"Dispatching event {event}")
        method = f"on_{event}"

        listeners = self._listeners.get(event)
        # remove the dispatched listener
        if listeners:
            removed = []
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
                        if len(args) == 0:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(idx)

            if len(removed) == len(listeners):
                self._listeners.pop(event)
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

    @final
    def run(self, *args: S.args, **kwargs: S.kwargs) -> None:
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
                await self.start(*args, **kwargs)
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

    async def login(self, username: str, password: str, *, shared_secret: str | None = None) -> None:
        """Login a Steam account and the Steam API with the specified credentials.

        Parameters
        ----------
        username
            The username of the user's account.
        password
            The password of the user's account.
        shared_secret
            The shared_secret of the desired Steam account, used to generate the 2FA code for login. If ``None`` is
            passed, the code will need to be inputted by the user via :meth:`code`.

        Raises
        ------
        :exc:`.InvalidCredentials`
            Invalid credentials were passed.
        :exc:`.LoginError`
            An unknown login related error occurred.
        :exc:`.NoCMsFound`
            No community managers could be found to connect to.
        """
        log.info("Logging in to steamcommunity.com")
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        await self.http.login(username, password, shared_secret=shared_secret)
        self._closed = False
        self.loop.create_task(self._connection.__ainit__())

    async def close(self) -> None:
        """Close the connection to Steam."""
        if self.is_closed():
            return

        self._closed = True

        if self.ws is not None:
            try:
                await self.change_presence(game=Game(id=0))  # disconnect from games
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
        self._connection.clear()
        self.http.clear()

    async def start(
        self,
        username: str,
        password: str,
        *,
        shared_secret: str | None = None,
        identity_secret: str | None = None,
    ) -> None:
        """A shorthand coroutine for :meth:`login` and :meth:`connect`.

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
        """

        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        if identity_secret is None:
            log.info("Trades will not be automatically accepted when sent as no identity_secret was passed.")

        await self.login(username, password, shared_secret=shared_secret)
        await self.connect()

    async def connect(self) -> None:
        """Initialize a connection to a Steam CM after logging in."""
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
            sleep = random.random() * 4 if between > 600 else 100 / between ** 0.5
            log.info(f"Attempting to connect to another CM in {sleep}")
            await asyncio.sleep(sleep)

        while not self.is_closed():
            last_connect = time.monotonic()

            try:
                self.ws = await asyncio.wait_for(SteamWebSocket.from_client(self, cm_list=self._cm_list), timeout=60)
            except exceptions:
                await throttle()
                continue

            try:
                while True:
                    await self.ws.poll_event()
            except exceptions as exc:
                if isinstance(exc, ConnectionClosed):
                    self._cm_list = exc.cm_list
                self.dispatch("disconnect")
            finally:
                if not self.is_closed():
                    await throttle()

    # state stuff

    def get_user(self, id: utils.Intable) -> User | None:
        """Returns a user from cache with a matching ID or ``None`` if the user was not found.

        Parameters
        ----------
        id
            The ID of the user, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.
        """
        id64 = make_id64(id=id, type=Type.Individual)
        return self._connection.get_user(id64)

    async def fetch_user(self, id: utils.Intable) -> User | None:
        """Fetches a user with a matching ID or ``None`` if the user was not found.

        Parameters
        ----------
        id
            The ID of the user, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.
        """
        id64 = make_id64(id=id, type=Type.Individual)
        return await self._connection.fetch_user(id64)

    async def fetch_users(self, *ids: utils.Intable) -> list[User | None]:
        """Fetches a list of :class:`~steam.User` or ``None`` if the user was not found, from their IDs.

        Note
        ----
        The :class:`~steam.User` objects returned are unlikely to retain the order they were originally in.

        Parameters
        ----------
        ids
            The user's IDs.
        """
        id64s = [make_id64(id, type=Type.Individual) for id in ids]
        return await self._connection.fetch_users(id64s)

    async def fetch_user_named(self, name: str) -> User | None:
        """Fetches a user from https://steamcommunity.com from their community URL name.

        Parameters
        ----------
        name
            The name of the user after https://steamcommunity.com/id
        """
        id64 = await utils.id64_from_url(URL.COMMUNITY / f"id/{name}", self.http._session)
        return await self._connection.fetch_user(id64) if id64 is not None else None

    def get_trade(self, id: int) -> TradeOffer | None:
        """Get a trade from cache with a matching ID or ``None`` if the trade was not found.

        Parameters
        ----------
        id
            The id of the trade to search for from the cache.
        """
        return self._connection.get_trade(id)

    async def fetch_trade(self, id: int) -> TradeOffer | None:
        """Fetches a trade with a matching ID or ``None`` if the trade was not found.

        Parameters
        ----------
        id
            The ID of the trade to search for from the API.
        """
        return await self._connection.fetch_trade(id)

    def get_group(self, id: utils.Intable) -> Group | None:
        """Get a group from cache with a matching ID or ``None`` if the group was not found.

        Parameters
        ----------
        id
            The ID of the group, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.
        """
        steam_id = SteamID(id=id, type=Type.Chat)
        return self._connection.get_group(steam_id.id)

    def get_clan(self, id: utils.Intable) -> Clan | None:
        """Get a clan from cache with a matching ID or ``None`` if the group was not found.

        Parameters
        ----------
        id
            The ID of the clan, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.
        """
        steam_id = SteamID(id=id, type=Type.Clan)
        return self._connection.get_clan(steam_id.id)

    async def fetch_clan(self, id: utils.Intable) -> Clan | None:
        """Fetches a clan from the websocket with a matching ID or ``None`` if the clan was not found.

        Parameters
        ----------
        id
            The ID of the clan, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.
        """
        id64 = make_id64(id=id, type=Type.Clan)
        return await self._connection.fetch_clan(id64)

    async def fetch_clan_named(self, name: str) -> Clan | None:
        """Fetches a clan from https://steamcommunity.com with a matching name or ``None`` if the clan was not found.

        Parameters
        ----------
        name
            The name of the Steam clan.
        """
        steam_id = await SteamID.from_url(URL.COMMUNITY / "clans" / name, self.http._session)
        return await self._connection.fetch_clan(steam_id.id64) if steam_id is not None else None

    def get_game(self, id: int | Game) -> StatefulGame:
        """Creates a stateful game from its ID.

        Parameters
        ----------
        id
            The app id of the game or a :class:`~steam.Game` instance.
        """
        return StatefulGame(self._connection, id=getattr(id, "id", id))

    async def fetch_game(self, id: int | Game) -> FetchedGame | None:
        """Fetch a game from its ID or ``None`` if the game was not found.

        Parameters
        ----------
        id
            The app id of the game or a :class:`~steam.Game` instance.
        """
        id = id if isinstance(id, int) else id.id
        resp = await self.http.get_game(id)
        if resp is None:
            return None
        data = resp[str(id)]
        if not data["success"]:
            return None
        return FetchedGame(self._connection, data["data"])

    @overload
    async def fetch_server(self, *, id: utils.Intable) -> GameServer | None:
        ...

    @overload
    async def fetch_server(
        self,
        *,
        ip: str,
        port: int | None = ...,
    ) -> GameServer | None:
        ...

    async def fetch_server(
        self,
        *,
        id: utils.Intable | None = None,
        ip: str | None = None,
        port: int | str | None = None,
    ) -> GameServer | None:
        """Fetch a :class:`.GameServer` from its ip and port or its SteamID or ``None`` if fetching the server failed.

        Parameters
        ----------
        ip
            The ip of the server.
        port
            The port of the server.
        id
            The ID of the game server, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id2` or an :attr:`.SteamID.id3`.
            If this is passed, it makes a call to the master server to fetch its ip and port.

        Note
        ----
        Passing an ``ip``, ``port`` and ``id`` to this function will raise an :exc:`TypeError`.
        """

        if all((id, ip, port)):
            raise TypeError("Too many arguments passed to fetch_server")
        if id:
            # we need to fetch the ip and port
            servers = await self._connection.fetch_server_ip_from_steam_id(make_id64(id, type=Type.GameServer))
            if not servers:
                raise ValueError(f"The master server didn't find a matching server for {id}")
            ip, _, port = servers[0].addr.partition(":")
        elif not ip:
            raise TypeError(f"fetch_server missing argument ip")

        servers = await self.fetch_servers(Query.ip / f"{ip}{f':{port}' if port is not None else ''}", limit=1)
        return servers[0] if servers else None

    async def fetch_servers(self, query: Query[Any], limit: int = 100) -> list[GameServer]:
        """Query game servers.

        Parameters
        ----------
        query
            The query to match servers with.
        limit
            The maximum amount of servers to return.
        """
        servers = await self._connection.fetch_servers(query.query, limit)
        return [GameServer(self._connection, server) for server in servers]

    # miscellaneous stuff

    def trade_history(
        self,
        limit: int | None = 100,
        before: datetime.datetime | None = None,
        after: datetime.datetime | None = None,
    ) -> TradesIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`steam.ClientUser`'s
        :class:`steam.TradeOffer` objects.

        Examples
        --------

        Usage:

        .. code-block:: python3

            async for trade in client.trade_history(limit=10):
                items = [getattr(item, "name", str(item.asset_id)) for item in trade.items_to_receive]
                items = ", ".join(items) or "Nothing"
                print("Partner:", trade.partner)
                print("Sent:", items)

        Flattening into a list:

        .. code-block:: python3

            trades = await client.trade_history(limit=50).flatten()
            # trades is now a list of TradeOffer

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

        Yields
        ---------
        :class:`~steam.TradeOffer`
        """
        return TradesIterator(state=self._connection, limit=limit, before=before, after=after)

    async def change_presence(
        self,
        *,
        game: Game | None = None,
        games: list[Game] | None = None,
        state: PersonaState | None = None,
        ui_mode: UIMode | None = None,
        flags: PersonaStateFlag | None = None,
        force_kick: bool = False,
    ) -> None:
        """Set your status.

        Parameters
        ----------
        game
            A games to set your status as.
        games
            A list of games to set your status to.
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
            Whether or not to forcefully kick any other playing sessions.
        """
        games_ = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games_.append(game.to_dict())
        await self.ws.change_presence(games=games_, state=state, flags=flags, ui_mode=ui_mode, force_kick=force_kick)

    async def trade_url(self, generate_new: bool = False) -> str:
        """Fetches this account's trade url.

        Parameters
        ----------
        generate_new
            Whether or not to generate a new trade token, defaults to ``False``.
        """
        return await self._connection.fetch_trade_url(generate_new)

    async def wait_until_ready(self) -> None:
        """Waits until the client's internal cache is all ready."""
        await self._ready.wait()

    async def fetch_price(self, name: str, game: Game, currency: int | None = None) -> PriceOverview:
        """Fetch the :class:`PriceOverview` for an item.

        Parameters
        ----------
        name
            The name of the item.
        game
            The game the item is from.
        currency
            The currency to fetch the price in.
        """
        price = await self.http.get_price(game.id, name, currency)
        return PriceOverview(price)

    # events to be subclassed

    async def on_error(self, event: str, error: Exception, *args, **kwargs):
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

    if TYPE_CHECKING or utils.DOCS_BUILDING:
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
                - :attr:`~steam.User.game`

            Parameters
            ----------
            before
                The user's state before it was updated.
            after
                The user's state now.
            """

        async def on_user_remove(self, user: "steam.User") -> None:
            """Called when you or the ``user`` remove each other from your friends lists.

            Parameters
            ----------
            user
                The user who was removed.
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

        async def on_socket_receive(self, msg: "Msg | MsgProto") -> None:
            """Called when the connected CM parses a received ``Msg``/``MsgProto``

            Parameters
            ----------
            msg
                The received message.
            """

        async def on_socket_send(self, msg: "Msg | MsgProto") -> None:
            """Called when the client sends a ``Msg``/``MsgProto`` to the connected CM.

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
        event: Literal["user_remove"],
        *,
        check: Callable[[User], bool] = ...,
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
            passed after the amount of seconds pass :exc:`asyncio.TimeoutError` is raised.

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
