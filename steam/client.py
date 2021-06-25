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
import sys
import traceback
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Optional, TypeVar, Union, overload

import aiohttp
from typing_extensions import Literal, ParamSpec, TypeAlias, final

from . import errors, utils
from .abc import SteamID
from .enums import Type
from .game import FetchedGame, Game
from .game_server import GameServer, Query
from .gateway import *
from .guard import generate_one_time_code
from .http import HTTPClient
from .iterators import TradesIterator
from .models import TASK_HAS_NAME, URL, PriceOverview
from .state import ConnectionState
from .utils import make_id64

if TYPE_CHECKING:
    import steam

    from .abc import Message
    from .clan import Clan
    from .comment import Comment
    from .enums import PersonaState, PersonaStateFlag, UIMode
    from .group import Group
    from .invite import ClanInvite, UserInvite
    from .protobufs import Msg, MsgProto
    from .trade import TradeOffer
    from .user import ClientUser, User

__all__ = ("Client",)

log = logging.getLogger(__name__)
EventType: TypeAlias = "Callable[..., Coroutine[Any, Any, Any]]"
EventDeco: TypeAlias = "Union[Callable[[E], E], E]"
E = TypeVar("E", bound=EventType)
S = ParamSpec("S", bound="Client.start")  # 90% sure this is the way to use ParamSpec


class Client:
    """Represents a client connection that connects to Steam. This class is used to interact with the Steam API and CMs.

    Parameters
    ----------
    game: :class:`~steam.Game`
        A games to set your status as on connect.
    games: list[:class:`~steam.Game`]
        A list of games to set your status to on connect.
    state: :class:`~steam.PersonaState`
        The state to show your account as on connect.

        Note
        ----
        Setting your status to :attr:`~steam.EPersonaState.Offline`, will stop you receiving persona state updates
        and by extension :meth:`on_user_update` will stop being dispatched.

    ui_mode: :class:`~steam.UIMode`
        The UI mode to set your status to on connect.
    force_kick: :class:`bool`
        Whether or not to forcefully kick any other playing sessions on connect.

    Attributes
    -----------
    ws:
        The connected websocket/CM server, this can be used to directly send messages to said CM.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, **options: Any):
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
        self._connection = ConnectionState(client=self, **options)
        self.ws: Optional[SteamWebSocket] = None

        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.shared_secret: Optional[str] = None
        self.identity_secret: Optional[str] = None
        self.token: Optional[str] = None

        self._closed = True
        self._cm_list: Optional[CMServerList] = None
        self._listeners: dict[str, list[tuple[asyncio.Future, Callable[..., bool]]]] = {}
        self._ready = asyncio.Event()

    @property
    def user(self) -> Optional[ClientUser]:
        """Optional[:class:`~steam.ClientUser`]: Represents the connected client. ``None`` if not logged in."""
        return self.http.user

    @property
    def users(self) -> list[User]:
        """list[:class:`~steam.User`]: Returns a list of all the users the account can see."""
        return self._connection.users

    @property
    def trades(self) -> list[TradeOffer]:
        """list[:class:`~steam.TradeOffer`]: Returns a list of all the trades the connected client has seen."""
        return self._connection.trades

    @property
    def groups(self) -> list[Group]:
        """list[:class:`~steam.Group`]: Returns a list of all the groups the connected client is in."""
        return self._connection.groups

    @property
    def clans(self) -> list[Clan]:
        """list[:class:`~steam.Clan`]: Returns a list of all the clans the connected client is in."""
        return self._connection.clans

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return float("nan") if self.ws is None else self.ws.latency

    async def code(self) -> str:
        """|coro|

        Warning
        -------
        This function will wait for a Steam guard code using :func:`input` in an executor if no shared_secret is passed to
        :meth:`run` or :meth:`start` blocking exiting until one is entered.

        Returns
        -------
        :class:`str`
            The current steam guard code.
        """
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        print("Please enter a Steam guard code")
        code = await utils.ainput(">>> ")
        return code.strip()

    def is_ready(self) -> bool:
        """:class:`bool`: Specifies if the client's internal cache is ready for use."""
        return self._ready.is_set()

    def is_closed(self) -> bool:
        """:class:`bool`: Indicates if connection is closed to the API or CMs."""
        return self._closed

    @overload
    def event(self, coro: Literal[None] = ...) -> Callable[[E], E]:
        ...

    @overload
    def event(self, coro: E) -> E:
        ...

    def event(self, coro: Optional[EventDeco] = None) -> EventDeco:
        """|maybecallabledeco|
        Register an event to listen to.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Usage: ::

            @client.event
            async def on_ready():
                print('Ready!')

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

    def _handle_ready(self) -> None:
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

    async def login(self, username: str, password: str, *, shared_secret: Optional[str] = None) -> None:
        """|coro|
        Logs in a Steam account and the Steam API with the specified credentials.

        Parameters
        ----------
        username: :class:`str`
            The username of the user's account.
        password: :class:`str`
            The password of the user's account.
        shared_secret: Optional[:class:`str`]
            The shared_secret of the desired Steam account, used to generate the 2FA code for login. If ``None`` is
            passed, the code will need to be inputted by the user via :meth:`code`.

        Raises
        ------
        :exc:`TypeError`
            Unexpected keyword arguments were received.
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
        """|coro|
        Closes the connection to Steam.
        """
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
        self.http.recreate()

    async def start(
        self,
        username: str,
        password: str,
        *,
        shared_secret: Optional[str] = None,
        identity_secret: Optional[str] = None,
    ) -> None:
        """|coro|
        A shorthand coroutine for :meth:`login` and :meth:`connect`. If no ``shared_secret`` is passed, you will have to
        manually enter a Steam guard code using :meth:`code`.

        Parameters
        -----------
        username: :class:`str`
            The username of the account to login to.
        password: :class:`str`
            The password of the account to login to.
        shared_secret: Optional[:class:`str`]
            The shared secret for the account to login to.
        identity_secret: Optional[:class:`str`]
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
        """|coro|
        Initialize a connection to a Steam CM after logging in.
        """
        while not self.is_closed():
            try:
                resp = await self.http.get(URL.COMMUNITY / "chat/clientjstoken")
                if not resp["logged_in"]:  # we got logged out :(
                    await self.http.login(self.username, self.password, shared_secret=self.shared_secret)
                    continue
                self.token = resp["token"]
                coro = SteamWebSocket.from_client(self, cm_list=self._cm_list)
                self.ws: SteamWebSocket = await asyncio.wait_for(coro, timeout=60)
                while True:
                    await self.ws.poll_event()
            except (
                OSError,
                ConnectionClosed,
                aiohttp.ClientError,
                ConnectionResetError,
                asyncio.TimeoutError,
                errors.HTTPException,
            ) as exc:
                if isinstance(exc, ConnectionClosed):
                    self._cm_list = exc.cm_list
                self.dispatch("disconnect")
            finally:
                if not self.is_closed():
                    log.info(f"Attempting to connect to another CM")
                    await asyncio.sleep(5)

    # state stuff

    def get_user(self, id: utils.Intable) -> Optional[User]:
        """Returns a user from cache with a matching ID.

        Parameters
        ----------
        id: Union[:class:`int`, :class:`str`]
            The ID of the user, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        id64 = make_id64(id=id, type="Individual")
        return self._connection.get_user(id64)

    async def fetch_user(self, id: utils.Intable) -> Optional[User]:
        """|coro|
        Fetches a user from the API with a matching ID.

        Parameters
        ----------
        id: Union[:class:`int`, :class:`str`]
            The ID of the user, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        id64 = make_id64(id=id, type=Type.Individual)
        return await self._connection.fetch_user(id64)

    async def fetch_users(self, *ids: utils.Intable) -> list[Optional[User]]:
        """|coro|
        Fetches a list of :class:`~steam.User` from their IDs from the API with a matching ID. The
        :class:`~steam.User` objects returned are unlikely to retain the order they were originally in.

        Parameters
        ----------
        *ids: Union[:class:`int`, :class:`str`]
            The user's IDs.

        Returns
        -------
        list[Optional[:class:`~steam.User`]]
            A list of the users or ``None`` if the user was not found.
        """
        id64s = [make_id64(id, type=Type.Individual) for id in ids]
        return await self._connection.fetch_users(id64s)

    async def fetch_user_named(self, name: str) -> Optional[User]:
        """|coro|
        Fetches a user from https://steamcommunity.com from there community URL name.

        Parameters
        ----------
        name: :class:`str`
            The name of the user after https://steamcommunity.com/id

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        id64 = await utils.id64_from_url(URL.COMMUNITY / "id" / name, self.http._session)
        return await self._connection.fetch_user(id64) if id64 is not None else None

    def get_trade(self, id: int) -> Optional[TradeOffer]:
        """Get a trade from cache with a matching ID.

        Parameters
        ----------
        id: :class:`int`
            The id of the trade to search for from the cache.

        Returns
        -------
        Optional[:class:`~steam.TradeOffer`]
            The trade offer or ``None`` if the trade was not found.
        """
        return self._connection.get_trade(id)

    async def fetch_trade(self, id: int) -> Optional[TradeOffer]:
        """|coro|
        Fetches a trade from the API with a matching ID.

        Parameters
        ----------
        id: :class:`int`
            The ID of the trade to search for from the API.

        Returns
        -------
        Optional[:class:`~steam.TradeOffer`]
            The trade offer or ``None`` if the trade was not found.
        """
        return await self._connection.fetch_trade(id)

    def get_group(self, id: utils.Intable) -> Optional[Group]:
        """Get a group from cache with a matching ID.

        Parameters
        ----------
        id: Union[:class:`int`, :class:`str`]
            The ID of the group, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.

        Returns
        -------
        Optional[:class:`~steam.Group`]
            The group or ``None`` if the group was not found.
        """
        steam_id = SteamID(id=id, type=Type.Chat)
        return self._connection.get_group(steam_id.id)

    def get_clan(self, id: utils.Intable) -> Optional[Clan]:
        """Get a clan from cache with a matching ID.

        Parameters
        ----------
        id: Union[:class:`int`, :class:`str`]
            The ID of the clan, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.

        Returns
        -------
        Optional[:class:`~steam.Clan`]
            The clan or ``None`` if the clan was not found.
        """
        steam_id = SteamID(id=id, type=Type.Clan)
        return self._connection.get_clan(steam_id.id)

    async def fetch_clan(self, id: utils.Intable) -> Optional[Clan]:
        """|coro|
        Fetches a clan from the websocket with a matching ID.

        Parameters
        ----------
        id: Union[:class:`int`, :class:`str`]
            The ID of the clan, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id`, :attr:`.SteamID.id2` or an
            :attr:`.SteamID.id3`.


        Returns
        -------
        Optional[:class:`~steam.Clan`]
            The clan or ``None`` if the clan was not found.
        """
        id64 = make_id64(id=id, type=Type.Clan)
        return await self._connection.fetch_clan(id64)

    async def fetch_clan_named(self, name: str) -> Optional[Clan]:
        """|coro|
        Fetches a clan from https://steamcommunity.com with a matching name.

        Parameters
        ----------
        name: :class:`str`
            The name of the Steam clan.

        Returns
        -------
        Optional[:class:`~steam.Clan`]
            The clan or ``None`` if the clan was not found.
        """
        steam_id = await SteamID.from_url(URL.COMMUNITY / "clans" / name, self.http._session)
        return await self._connection.fetch_clan(steam_id.id64) if steam_id is not None else None

    async def fetch_game(self, id: Union[int, Game]) -> Optional[FetchedGame]:
        """|coro|
        Fetch a game from its ID.

        Parameters
        ----------
        id: :class:`int`
            The app id of the game or a :class:`~steam.Game` instance.

        Returns
        -------
        Optional[:class:`.FetchedGame`]
            The fetched game or ``None`` if the game was not found.
        """
        id = id if isinstance(id, int) else id.id
        data = await self.http.get_game(id)
        if data is None:
            return None
        if not data[str(id)]["success"]:
            return None
        return FetchedGame(data[str(id)]["data"])

    @overload
    async def fetch_server(self, *, id: utils.Intable) -> Optional[GameServer]:
        ...

    @overload
    async def fetch_server(
        self,
        *,
        ip: str,
        port: int,
    ) -> Optional[GameServer]:
        ...

    async def fetch_server(
        self,
        *,
        id: Optional[utils.Intable] = None,
        ip: Optional[str] = None,
        port: Optional[int] = None,
    ) -> Optional[GameServer]:
        """|coro|
        Fetch a specific game server from its ip and port.

        Parameters
        ----------
        id: Union[:class:`int`, :class:`str`]
            The ID of the game server, can be an :attr:`.SteamID.id64`, :attr:`.SteamID.id2` or an :attr:`.SteamID.id3`.
        ip: :class:`str`
            The ip of the server.
        port: :class:`int`
            The port of the server.

        Returns
        -------
        Optional[:class:`GameServer`]
            The found game server or ``None`` if fetching the server failed.
        """

        if all((id, ip, port)):
            raise TypeError("Too many arguments passed to fetch_server")
        if id:
            # we need to fetch the ip and port
            servers = await self._connection.fetch_server_ip_from_steam_id(make_id64(id, type=Type.GameServer))
            ip, port = servers[0].addr.split(":")
        elif not (ip and port):
            raise TypeError(f"fetch_server missing argument {'ip' if not ip else 'port'}")

        servers = await self.fetch_servers(Query.ip / f"{ip}:{port}", limit=1)
        return servers[0] if servers else None

    async def fetch_servers(self, query: Query, limit: int = 100) -> list[GameServer]:
        """|coro|
        Query game servers.

        Parameters
        ----------
        query: :class:`Query`
            The query to match servers with.
        limit: :class:`int`
            The maximum amount of servers to return.

        Returns
        -------
        list[:class:`.GameServer`]
            The matched servers.
        """
        servers = await self._connection.fetch_servers(query.query, limit)
        return [GameServer(server) for server in servers]

    # miscellaneous stuff

    def trade_history(
        self,
        limit: Optional[int] = 100,
        before: Optional[datetime.datetime] = None,
        after: Optional[datetime.datetime] = None,
        active_only: bool = False,
    ) -> TradesIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`steam.ClientUser`'s
        :class:`steam.TradeOffer` objects.

        Examples
        --------

        Usage: ::

            async for trade in client.trade_history(limit=10):
                print("Partner:", trade.partner)
                print(
                    "Sent:",
                    item.name or str(item.asset_id) for item in trade.items_to_receive
                    if trade.items_to_receive
                    else "Nothing",
                )

        Flattening into a list: ::

            trades = await client.trade_history(limit=50).flatten()
            # trades is now a list of TradeOffer

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of trades to search through. Default is 100 which will fetch the first 100 trades.
            Setting this to ``None`` will fetch all of the user's trades, but this will be a very slow operation.
        before: Optional[:class:`datetime.datetime`]
            A time to search for trades before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for trades after.
        active_only: Optional[:class:`bool`]
            Whether or not to fetch only active trades defaults to ``True``.

        Yields
        ---------
        :class:`~steam.TradeOffer`
        """
        return TradesIterator(state=self._connection, limit=limit, before=before, after=after, active_only=active_only)

    async def change_presence(
        self,
        *,
        game: Optional[Game] = None,
        games: Optional[list[Game]] = None,
        state: Optional[PersonaState] = None,
        ui_mode: Optional[UIMode] = None,
        flag: Optional[PersonaStateFlag] = None,
        flags: Optional[list[PersonaStateFlag]] = None,
        force_kick: bool = False,
    ) -> None:
        """|coro|
        Set your status.

        Parameters
        ----------
        game: Optional[:class:`~steam.Game`]
            A games to set your status as.
        games: Optional[list[:class:`~steam.Game`]]
            A list of games to set your status to.
        state: Optional[:class:`~steam.PersonaState`]
            The state to show your account as.

            Warning
            -------
            Setting your status to :attr:`~steam.PersonaState.Offline`, will stop you receiving persona state updates
            and by extension :meth:`on_user_update` will stop being dispatched.

        ui_mode: Optional[:class:`~steam.UIMode`]
            The UI mode to set your status to.
        flag: Optional[:class:`PersonaStateFlag`]
            The flag to update your account with.
        flags: Optional[list[:class:`PersonaStateFlag`]
            The flags to update your account with.
        force_kick: :class:`bool`
            Whether or not to forcefully kick any other playing sessions.
        """
        games = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games.append(game.to_dict())
        flags = flags or getattr(self.user, "flags", [])
        if flag is not None:
            flags.append(flag)
        flag_value = 0
        for flag in flags:
            flag_value |= flag
        await self.ws.change_presence(
            games=games, state=state, flags=flag_value, ui_mode=ui_mode, force_kick=force_kick
        )

    async def trade_url(self, generate_new: bool = False) -> str:
        """|coro|
        Fetches this accounts trade url.

        Parameters
        ----------
        generate_new: :class:`bool`
            Whether or not to generate a new trade token, defaults to ``False``.
        """
        return await self._connection.get_trade_url(generate_new)

    async def wait_until_ready(self) -> None:
        """|coro|
        Waits until the client's internal cache is all ready.
        """
        await self._ready.wait()

    async def fetch_price(self, name: str, game: Game, currency: Optional[int] = None) -> PriceOverview:
        """|coro|
        Fetch the price for an item.

        Parameters
        ----------
        name: :class:`str`
            The name of the item.
        game: :class:`.Game`
            The game the item is from.
        currency: :class:`int`
            The currency to fetch the price in.

        Returns
        --------
        :class:`.PriceOverview`
            The price overview for the item.
        """
        price = await self.http.get_price(game.id, name, currency)
        return PriceOverview(price)

    # events to be subclassed

    async def on_error(self, event: str, error: Exception, *args, **kwargs):
        """|coro|
        The default error handler provided by the client.

        Usually when an event raises an uncaught exception, a traceback is printed to :attr:`sys.stderr` and the
        exception is ignored. If you want to change this behaviour and handle the exception yourself, this event can
        be overridden. Which, when done, will suppress the default action of printing the traceback.

        If you want exception to propagate out of the :class:`Client` class you can define an ``on_error`` handler
        consisting of a single empty :ref:`py:raise`. Exceptions raised by ``on_error`` will not be handled in any
        way by :class:`Client`.

        Parameters
        ----------
        event: :class:`str`
            The name of the event that errored.
        error: :exc:`Exception`
            The error that was raised.
        *args:
            The positional arguments associated with the event.
        **kwargs:
            The key-word arguments associated with the event.
        """
        print(f"Ignoring exception in {event}", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    if TYPE_CHECKING:  # these methods shouldn't exist at runtime unless subclassed to prevent pollution of logs

        async def on_connect(self) -> None:
            """|coro|
            Called when the client has successfully connected to Steam. This is not the same as the client being
            fully prepared, see :func:`on_ready` for that.

            The warnings on :meth:`on_ready` also apply.
            """

        async def on_disconnect(self) -> None:
            """|coro|
            Called when the client has disconnected from Steam. This could happen either through the internet
            disconnecting, an explicit call to logout, or Steam terminating the connection.

            This function can be called multiple times.
            """

        async def on_ready(self) -> None:
            """|coro|
            Called after a successful login and the client has handled setting up everything.

            Warning
            -------
            This function is not guaranteed to be the first event called. Likewise, this function is **not**
            guaranteed to only be called once. This library implements reconnection logic and will therefore
            end up calling this event whenever a CM disconnects.
            """

        async def on_login(self) -> None:
            """|coro|
            Called when the client has logged into https://steamcommunity.com.
            """

        async def on_logout(self) -> None:
            """|coro|
            Called when the client has logged out of https://steamcommunity.com.
            """

        async def on_message(self, message: "steam.Message") -> None:
            """|coro|
            Called when a message is created.

            Parameters
            ----------
            message: :class:`~steam.Message`
                The message that was received.
            """

        async def on_typing(self, user: "steam.User", when: "datetime.datetime") -> None:
            """|coro|
            Called when typing is started.

            Parameters
            ----------
            user: :class:`~steam.User`
                The user that started typing.
            when: :class:`datetime.datetime`
                The time the user started typing at.
            """

        async def on_trade_receive(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when the client receives a trade offer.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that was received.
            """

        async def on_trade_send(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when the client sends a trade offer.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that was sent.
            """

        async def on_trade_accept(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when the client or the trade partner accepts a trade offer.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that was accepted.
            """

        async def on_trade_decline(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when the client or the trade partner declines a trade offer.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that was declined.
            """

        async def on_trade_cancel(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when the client or the trade partner cancels a trade offer.

            Note
            ----
            This is called when the trade state becomes :attr:`~steam.TradeOfferState.Canceled` and
            :attr:`~steam.TradeOfferState.CanceledBySecondaryFactor`.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that was cancelled.
            """

        async def on_trade_expire(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when a trade offer expires due to being active for too long.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that expired.
            """

        async def on_trade_counter(self, trade: "steam.TradeOffer") -> None:
            """|coro|
            Called when the client or the trade partner counters a trade offer.

            Parameters
            ----------
            trade: :class:`~steam.TradeOffer`
                The trade offer that was countered.
            """

        async def on_comment(self, comment: "steam.Comment") -> None:
            """|coro|
            Called when the client receives a comment notification.

            Parameters
            ----------
            comment: :class:`~steam.Comment`
                The comment received.
            """

        async def on_user_invite(self, invite: "steam.UserInvite") -> None:
            """|coro|
            Called when the client receives/sends an invite from/to a :class:`~steam.User` to become a friend.

            Parameters
            ----------
            invite: :class:`~steam.UserInvite`
                The invite received.
            """

        async def on_user_invite_accept(self, invite: "steam.UserInvite") -> None:
            """|coro|
            Called when the client/invitee accepts an invite from/to a :class:`~steam.User` to become a friend.

            Parameters
            ----------
            invite: :class:`~steam.UserInvite`
                The invite that was accepted.
            """

        async def on_clan_invite(self, invite: "steam.ClanInvite") -> None:
            """|coro|
            Called when the client receives/sends an invite from/to a :class:`~steam.User` to join a
            :class:`~steam.Clan`.

            Parameters
            ----------
            invite: :class:`~steam.ClanInvite`
                The invite received.
            """

        async def on_clan_invite_accept(self, invite: "steam.ClanInvite") -> None:
            """|coro|
            Called when the client/invitee accepts an invite to join a :class:`~steam.Clan`.

            Parameters
            ----------
            invite: :class:`~steam.ClanInvite`
                The invite that was accepted.
            """

        async def on_user_update(self, before: "steam.User", after: "steam.User") -> None:
            """|coro|
            Called when a user's their state, due to one or more of the following attributes changing:

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
            before: :class:`~steam.User`
                The user's state before it was updated.
            after: :class:`~steam.User`
                The user's state now.
            """

        async def on_socket_receive(self, msg: "Union[Msg, MsgProto]") -> None:
            """|coro|
            Called when the connected web-socket parses a received ``Msg``/``MsgProto``

            Parameters
            ----------
            msg: Union[:class:`~steam.protobufs.Msg`, :class:`~steam.protobufs.MsgProto`]
                The received message.
            """

        async def on_socket_send(self, msg: "Union[Msg, MsgProto]") -> None:
            """|coro|
            Called when the client sends a parsed ``Msg``/``MsgProto`` to the connected web-socket.

            Parameters
            ----------
            msg: Union[:class:`~steam.protobufs.Msg`, :class:`~steam.protobufs.MsgProto`]
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
        check: Optional[Callable[[], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> None:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["error"],
        *,
        check: Optional[Callable[[str, Exception, tuple[Any, ...], dict[str, Any]], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> tuple[str, Exception, tuple, dict]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["message"],
        *,
        check: Optional[Callable[[Message], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Message:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["comment"],
        *,
        check: Optional[Callable[[Comment], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Comment:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["user_update"],
        *,
        check: Optional[Callable[[User, User], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> tuple[User, User]:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal["typing"],
        *,
        check: Optional[Callable[[User, datetime.datetime], bool]] = ...,
        timeout: Optional[float] = ...,
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
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> TradeOffer:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "user_invite",
            "user_invite_accept",
        ],
        *,
        check: Optional[Callable[[UserInvite], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> UserInvite:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "clan_invite",
            "clan_invite_accept",
        ],
        *,
        check: Optional[Callable[[ClanInvite], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> ClanInvite:
        ...

    @overload
    async def wait_for(
        self,
        event: Literal[
            "socket_receive",
            "socket_send",
        ],
        *,
        check: Optional[Callable[[Msgs], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Msgs:
        ...

    async def wait_for(
        self,
        event: str,
        *,
        check: Optional[Callable[..., bool]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """|coro|
        Wait for the first event to be dispatched that meets the requirements, this by default is the first event
        with a matching event name.

        Parameters
        -----------
        event: :class:`str`
            The event name from the :ref:`event reference <event-reference>`, but without the ``on_`` prefix, to wait
            for.
        check: Optional[Callable[..., :class:`bool`]]
            A callable predicate that checks the received event. The arguments must match the parameters of the
            ``event`` being waited for and must return a :class:`bool`.
        timeout: Optional[:class:`float`]
            By default, :meth:`wait_for` function does not timeout, however, in the case a ``timeout`` parameter is
            passed after the amount of seconds pass :exc:`asyncio.TimeoutError` is raised.

        Raises
        -------
        :exc:`asyncio.TimeoutError`
            If the provided timeout was reached.

        Returns
        --------
        Optional[Any]
            Returns ``None``, a single argument, or a :class:`tuple` of multiple arguments that mirrors the parameters
            for the ``event`` parameter from the :ref:`event reference <event-reference>`.
        """
        future = self.loop.create_future()
        check = check or return_true

        event_lower = event.lower()
        try:
            listeners = self._listeners[event_lower]
        except KeyError:
            listeners = []
            self._listeners[event_lower] = listeners

        listeners.append((future, check))
        return await asyncio.wait_for(future, timeout)
