# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz
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

import asyncio
import datetime
import logging
import sys
import traceback
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union, overload

import aiohttp
from typing_extensions import Literal, Protocol

from . import errors, utils
from .abc import SteamID
from .gateway import *
from .guard import generate_one_time_code
from .http import HTTPClient
from .iterators import TradesIterator
from .models import PriceOverview, community_route
from .state import ConnectionState

if TYPE_CHECKING:
    from types import CodeType

    import steam

    from .clan import Clan
    from .comment import Comment
    from .enums import EPersonaState, EPersonaStateFlag, EUIMode
    from .game import Game
    from .group import Group
    from .invite import ClanInvite, Invite, UserInvite
    from .protobufs import Msg, MsgProto
    from .trade import TradeOffer
    from .user import ClientUser, User


__all__ = ("Client",)

log = logging.getLogger(__name__)


class EventType(Protocol):
    # would be a FunctionType subclass to make things nicer, but alas "type 'function' is not an acceptable base type"
    __code__: "CodeType"
    __annotations__: Dict[str, Any]
    __name__: str

    async def __call__(self, *args, **kwargs) -> None:
        ...


def _cancel_tasks(loop: asyncio.AbstractEventLoop) -> None:
    tasks = asyncio.all_tasks(loop=loop)

    if not tasks:
        return

    log.info(f"Cleaning up after {len(tasks)} tasks.")
    for task in tasks:
        task.cancel()

    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    log.info("All tasks finished cancelling.")

    for task in tasks:
        if task.cancelled():
            continue
        if task.exception() is not None:
            loop.call_exception_handler(
                {
                    "message": "unhandled exception during Client.run shutdown.",
                    "exception": task.exception(),
                    "task": task,
                }
            )


class ClientEventTask(asyncio.Task):
    def __init__(
        self, original_coro: EventType, event_name: str, coro: Awaitable[None], *, loop: asyncio.AbstractEventLoop
    ):
        super().__init__(coro, loop=loop)
        self.__event_name = event_name
        self.__original_coro = original_coro

    def __repr__(self):
        info = [
            ("state", self._state.lower()),
            ("event", self.__event_name),
            ("coro", repr(self.__original_coro)),
        ]
        if self._exception is not None:
            info.append(("exception", repr(self._exception)))
        return f'<ClientEventTask {" ".join(f"{t}={t!r}" for t in info)}>'


class Client:
    """Represents a client connection that connects to Steam. This class is used to interact with the Steam API and CMs.

    Parameters
    ----------
    loop: Optional[:class:`asyncio.AbstractEventLoop`]
        The :class:`asyncio.AbstractEventLoop` used for asynchronous operations. Defaults to ``None``, in which case the
        default event loop is used via :func:`asyncio.get_event_loop()`.
    game: :class:`~steam.Game`
        A games to set your status as on connect.
    games: List[:class:`~steam.Game`]
        A list of games to set your status to on connect.
    state: :class:`~steam.EPersonaState`
        The state to show your account as on connect.

        .. note::
            Setting your status to :attr:`~steam.EPersonaState.Offline`, will stop you receiving persona state updates
            and by extension :meth:`on_user_update` will stop being dispatched.

    ui_mode: :class:`~steam.EUIMode`
        The UI mode to set your status to on connect.
    force_kick: :class:`bool`
        Whether or not to forcefully kick any other playing sessions on connect.

    Attributes
    -----------
    loop: :class:`asyncio.AbstractEventLoop`
        The event loop that the client uses for HTTP requests.
    ws:
        The connected websocket/CM server, this can be used to directly send messages to said CM.
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, **options):
        self.loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()

        self.http = HTTPClient(client=self)
        self._connection = ConnectionState(loop=self.loop, client=self, http=self.http, **options)
        self.ws: Optional[SteamWebSocket] = None

        self.username: Optional[str] = None
        self.api_key: Optional[str] = None
        self.password: Optional[str] = None
        self.shared_secret: Optional[str] = None
        self.identity_secret: Optional[str] = None
        self.token: Optional[str] = None

        self._closed = True
        self._cm_list: Optional["CMServerList"] = None
        self._listeners: Dict[str, List[Tuple[asyncio.Future, Callable[..., bool]]]] = {}
        self._ready = asyncio.Event()

        for base in reversed(self.__class__.__mro__):
            for name, attr in tuple(base.__dict__.items()):
                if name[:3] != "on_":  # not an event
                    continue
                if "error" in name:  # an error event, we shouldn't delete these
                    continue
                try:
                    if attr.__code__.co_filename == __file__:
                        delattr(base, name)
                except AttributeError:
                    pass

    @property
    def user(self) -> Optional["ClientUser"]:
        """Optional[:class:`~steam.ClientUser`]: Represents the connected client. ``None`` if not logged in."""
        return self.http.user

    @property
    def users(self) -> List["User"]:
        """List[:class:`~steam.User`]: Returns a list of all the users the account can see."""
        return self._connection.users

    @property
    def trades(self) -> List["TradeOffer"]:
        """List[:class:`~steam.TradeOffer`]: Returns a list of all the trades the connected client has seen."""
        return self._connection.trades

    @property
    def groups(self) -> List["Group"]:
        """List[:class:`~steam.Group`]: Returns a list of all the groups the connected client is in."""
        return self._connection.groups

    @property
    def clans(self) -> List["Clan"]:
        """List[:class:`~steam.Clan`]: Returns a list of all the clans the connected client is in."""
        return self._connection.clans

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a heartbeat send and the heartbeat interval in seconds."""
        return float("nan") if self.ws is None else self.ws.latency

    async def code(self) -> str:
        """|coro|

        .. warning::
            Will wait for a Steam guard code using :func:`input` in an executor if no shared_secret is passed to
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

    def event(self, coro: EventType) -> EventType:
        """A decorator that registers an event to listen to.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Usage: ::

            @client.event
            async def on_ready():
                print('Ready!')

        Raises
        --------
        :exc:`TypeError`
            The function passed is not a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError(f"Registered events must be a coroutines, {coro.__name__} is not")

        setattr(self, coro.__name__, coro)
        log.debug(f"{coro.__name__} has successfully been registered as an event")
        return coro

    async def _run_event(self, coro: EventType, event_name: str, *args, **kwargs) -> None:
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            try:
                await self.on_error(event_name, exc, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    def _schedule_event(self, coro: EventType, event_name: str, *args, **kwargs) -> ClientEventTask:
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        # schedules the task
        return ClientEventTask(original_coro=coro, event_name=event_name, coro=wrapped, loop=self.loop)

    def dispatch(self, event: str, *args, **kwargs) -> None:
        log.debug(f"Dispatching event {event}")
        method = f"on_{event}"

        listeners = self._listeners.get(event)
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

        try:
            coro = getattr(self, method)
        except AttributeError:
            pass
        else:
            self._schedule_event(coro, method, *args, **kwargs)

    def _handle_ready(self) -> None:
        self._ready.set()
        self.dispatch("ready")

    def run(self, *args, **kwargs) -> None:
        """A blocking call that abstracts away the event loop initialisation from you.

        This is roughly equivalent to::

            asyncio.run(client.start(username, password))

        If you want more control over the event loop then this function should not be used. It is not recommended to
        subclass this, it is normally favourable to subclass :meth:`start` or :meth:`login` as they are
        :ref:`coroutines <coroutine>`.

        .. note::

            This takes the same arguments as :meth:`start`.
        """
        loop = self.loop

        async def runner():
            try:
                await self.start(*args, **kwargs)
            finally:
                if not self._closed:
                    await self.close()

        try:
            loop.run_until_complete(runner())
        except KeyboardInterrupt:
            log.info("Received signal to terminate the client and event loop.")
        finally:
            log.info("Cleaning up tasks.")
            try:
                _cancel_tasks(loop)
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                log.info("Closing the event loop.")
                loop.close()

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
        :exc:`.HTTPException`
            An unknown HTTP related error occurred.
        :exc:`.NoCMsFound`
            No community managers could be found to connect to.
        """
        log.info(f"Logging in to steamcommunity.com")
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
        if self._closed:
            return

        await self.http.close()
        self._closed = True

        if self.ws is not None:
            try:
                await self.ws.handle_close()
            except ConnectionClosed:
                pass

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

        Raises
        ------
        :exc:`.InvalidCredentials`
            The wrong credentials are passed.
        :exc:`.HTTPException`
            An unknown HTTP related error occurred.
        :exc:`.NoCMsFound`
            No community managers could be found to connect to.
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
                resp = await self.http.request("GET", url=community_route("chat/clientjstoken"))
                if not resp["logged_in"]:  # we got logged out :(
                    await self.http.login(self.username, self.password, shared_secret=self.shared_secret)
                    continue
                self.token = resp["token"]
                coro = SteamWebSocket.from_client(self, cms=self._cm_list)
                self.ws: SteamWebSocket = await asyncio.wait_for(coro, timeout=60)
                while 1:
                    await self.ws.poll_event()
            except (
                OSError,
                aiohttp.ClientError,
                asyncio.TimeoutError,
                errors.HTTPException,
            ):
                self.dispatch("disconnect")
            except ConnectionClosed as exc:
                self._cm_list = exc.cm_list
                self.dispatch("disconnect")
            finally:
                if self.is_closed():
                    return

                log.info(f"Attempting to connect to another CM")
                await asyncio.sleep(5)

    # state stuff

    def get_user(self, *args, **kwargs) -> Optional["User"]:
        """Returns a user from cache with a matching ID.

        Parameters
        ----------
        *args
            The arguments to pass to :meth:`~steam.utils.make_id64`.
        **kwargs
            The keyword arguments to pass to :meth:`~steam.utils.make_id64`.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        steam_id = SteamID(*args, **kwargs)
        return self._connection.get_user(steam_id.id64)

    async def fetch_user(self, *args, **kwargs) -> Optional["User"]:
        """|coro|
        Fetches a user from the API with a matching ID.

        Parameters
        ----------
        *args
            The arguments to pass to :meth:`~steam.utils.make_id64`.
        **kwargs
            The keyword arguments to pass to :meth:`~steam.utils.make_id64`.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        steam_id = SteamID(*args, **kwargs)
        return await self._connection.fetch_user(steam_id.id64)

    async def fetch_users(self, *ids: int) -> List[Optional["User"]]:
        """|coro|
        Fetches a list of :class:`~steam.User` from their IDs from the API with a matching ID. The
        :class:`~steam.User` objects returned are unlikely to retain the order they were originally in.

        Parameters
        ----------
        *ids: :class:`int`
            The user's IDs.

        Returns
        -------
        List[Optional[:class:`~steam.User`]]
            A list of the users or ``None`` if the user was not found.
        """
        steam_ids = [SteamID(id).id64 for id in ids]
        return await self._connection.fetch_users(steam_ids)

    async def fetch_user_named(self, name: str) -> Optional["User"]:
        """|coro|
        Fetches a user from https://steamcommunity.com from there community URL name.

        Parameters
        ----------
        name: :class:`str`
            The name of the Steam user.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        steam_id = await SteamID.from_url(community_route(f"id/{name}"), self.http._session)
        if not steam_id:
            return None
        return await self._connection.fetch_user(steam_id.id64)

    def get_trade(self, id: int) -> Optional["TradeOffer"]:
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

    async def fetch_trade(self, id: int) -> Optional["TradeOffer"]:
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

    def get_group(self, *args, **kwargs) -> Optional["Group"]:
        """Get a group from cache with a matching ID.

        Parameters
        ----------
        *args
            The arguments to pass to :meth:`~steam.utils.make_id64`.
        **kwargs
            The keyword arguments to pass to :meth:`~steam.utils.make_id64`.

        Returns
        -------
        Optional[:class:`~steam.Group`]
            The group or ``None`` if the group was not found.
        """
        kwargs["type"] = "Chat"
        steam_id = SteamID(*args, **kwargs)
        return self._connection.get_group(steam_id.id)

    def get_clan(self, *args, **kwargs) -> Optional["Clan"]:
        """Get a clan from cache with a matching ID.

        Parameters
        ----------
        *args
            The arguments to pass to :meth:`~steam.utils.make_id64`.
        **kwargs
            The keyword arguments to pass to :meth:`~steam.utils.make_id64`.

        Returns
        -------
        Optional[:class:`~steam.Clan`]
            The clan or ``None`` if the clan was not found.
        """
        kwargs["type"] = "Clan"
        steam_id = SteamID(*args, **kwargs)
        return self._connection.get_clan(steam_id.id)

    async def fetch_clan(self, *args, **kwargs) -> Optional["Clan"]:
        """|coro|
        Fetches a clan from the websocket with a matching ID.

        Parameters
        ----------
        *args
            The arguments to pass to :meth:`~steam.utils.make_id64`.
        **kwargs
            The keyword arguments to pass to :meth:`~steam.utils.make_id64`.

        Returns
        -------
        Optional[:class:`~steam.Clan`]
            The clan or ``None`` if the clan was not found.
        """
        kwargs["type"] = "Clan"
        steam_id = SteamID(*args, **kwargs)
        return await self._connection.fetch_clan(steam_id.id64)

    async def fetch_clan_named(self, name: str) -> Optional["Clan"]:
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
        steam_id = await SteamID.from_url(community_route(f"clans/{name}"), self.http._session)
        if steam_id is None:
            return None
        return await self._connection.fetch_clan(steam_id.id64)

    def trade_history(
        self,
        limit: Optional[int] = 100,
        before: Optional[datetime.datetime] = None,
        after: Optional[datetime.datetime] = None,
        active_only: bool = False,
    ) -> TradesIterator:
        """An :class:`~steam.iterators.AsyncIterator` for accessing a :class:`ClientUser`'s :class:`~steam.TradeOffer`
        objects.

        Examples
        -----------

        Usage: ::

            async for trade in client.trade_history(limit=10):
                print('Partner:', trade.partner, 'Sent:')
                print(', '.join(item.name if item.name else str(item.asset_id) for item in trade.items_to_receive)
                      if trade.items_to_receive else 'Nothing')

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

    # misc

    async def change_presence(
        self,
        *,
        game: Optional["Game"] = None,
        games: Optional[List["Game"]] = None,
        state: Optional["EPersonaState"] = None,
        ui_mode: Optional["EUIMode"] = None,
        flag: Optional["EPersonaStateFlag"] = None,
        flags: Optional[List["EPersonaStateFlag"]] = None,
        force_kick: bool = False,
    ) -> None:
        """|coro|
        Set your status.

        Parameters
        ----------
        game: :class:`~steam.Game`
            A games to set your status as.
        games: List[:class:`~steam.Game`]
            A list of games to set your status to.
        state: :class:`~steam.EPersonaState`
            The state to show your account as.

            .. warning::
                Setting your status to :attr:`~steam.EPersonaState.Offline`, will stop you receiving persona state
                updates and by extension :meth:`on_user_update` will stop being dispatched.

        ui_mode: :class:`~steam.EUIMode`
            The UI mode to set your status to.
        flag: Optional[:class:`EPersonaStateFlag`]
            The flag to update your account with.
        flags: Optional[List[:class:`EPersonaStateFlag`]
            The flags to update your account with.
        force_kick: :class:`bool`
            Whether or not to forcefully kick any other playing sessions.
        """
        games = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games.append(game.to_dict())
        flags = flags or self.user.flags
        if flag is not None:
            flags.append(flag)
        flag_value = 0
        for flag in flags:
            flag_value |= flag
        await self.ws.change_presence(
            games=games, state=state, flags=flag_value, ui_mode=ui_mode, force_kick=force_kick
        )

    async def wait_until_ready(self) -> None:
        """|coro|
        Waits until the client's internal cache is all ready.
        """
        await self._ready.wait()

    async def fetch_price(self, name: str, game: "Game", currency: Optional[int] = None) -> PriceOverview:
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

    async def on_connect(self):
        """|coro|
        Called when the client has successfully connected to Steam. This is not the same as the client being
        fully prepared, see :func:`on_ready` for that.

        The warnings on :meth:`on_ready` also apply.
        """

    async def on_disconnect(self):
        """|coro|
        Called when the client has disconnected from Steam. This could happen either through the internet
        disconnecting, an explicit call to logout, or Steam terminating the connection.

        This function can be called multiple times.
        """

    async def on_ready(self):
        """|coro|
        Called after a successful login and the client has handled setting up trade and notification polling,
        along with setup the confirmation manager.

        .. note::
            In future this will be called when the client is done preparing the data received from Steam.
            Usually after login to a CM is successful.

        .. warning::

            This function is not guaranteed to be the first event called. Likewise, this function is **not**
            guaranteed to only be called once. This library implements reconnection logic and will therefore
            end up calling this event whenever a CM disconnects.
        """

    async def on_login(self):
        """|coro|
        Called when the client has logged into https://steamcommunity.com and the :attr:`user` is setup.
        """

    async def on_logout(self):
        """|coro|
        Called when the client has logged out of https://steamcommunity.com.
        """

    async def on_message(self, message: "steam.Message"):
        """|coro|
        Called when a message is created.

        Parameters
        ----------
        message: :class:`~steam.Message`
            The message that was received.
        """

    async def on_typing(self, user: "steam.User", when: "datetime.datetime"):
        """|coro|
        Called when typing is started.

        Parameters
        ----------
        user: :class:`~steam.User`
            The user that started typing.
        when: :class:`datetime.datetime`
            The time the user started typing at.
        """

    async def on_trade_receive(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when the client receives a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was received.
        """

    async def on_trade_send(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when the client sends a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was sent.
        """

    async def on_trade_accept(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when the client or the trade partner accepts a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was accepted.
        """

    async def on_trade_decline(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when the client or the trade partner declines a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was declined.
        """

    async def on_trade_cancel(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when the client or the trade partner cancels a trade offer.

        .. note::
            This is called when the trade state becomes :attr:`~steam.ETradeOfferState.Canceled` and
            :attr:`~steam.ETradeOfferState.CanceledBySecondaryFactor`.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was cancelled.
        """

    async def on_trade_expire(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when a trade offer expires due to being active for too long.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that expired.
        """

    async def on_trade_counter(self, trade: "steam.TradeOffer"):
        """|coro|
        Called when the client or the trade partner counters a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was countered.
        """

    async def on_comment(self, comment: "steam.Comment"):
        """|coro|
        Called when the client receives a comment notification.

        Parameters
        ----------
        comment: :class:`~steam.Comment`
            The comment received.
        """

    async def on_user_invite(self, invite: "steam.UserInvite"):
        """|coro|
        Called when the client receives/sends an invite from/to a :class:`~steam.User` to become a friend.

        Parameters
        ----------
        invite: :class:`~steam.UserInvite`
            The invite received.
        """

    async def on_user_invite_accept(self, invite: "steam.UserInvite"):
        """|coro|
        Called when the client/invitee accepts an invite from/to a :class:`~steam.User` to become a friend.

        Parameters
        ----------
        invite: :class:`~steam.UserInvite`
            The invite that was accepted.
        """

    async def on_clan_invite(self, invite: "steam.ClanInvite"):
        """|coro|
        Called when the client receives/sends an invite from/to a :class:`~steam.User` to join a :class:`~steam.Clan`.

        Parameters
        ----------
        invite: :class:`~steam.ClanInvite`
            The invite received.
        """

    async def on_clan_invite_accept(self, invite: "steam.ClanInvite"):
        """|coro|
        Called when the client/invitee accepts an invite to join a :class:`~steam.Clan`.

        Parameters
        ----------
        invite: :class:`~steam.ClanInvite`
            The invite that was accepted.
        """

    async def on_user_update(self, before: "steam.User", after: "steam.User"):
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

    async def on_socket_receive(self, msg: Union["Msg", "MsgProto"]):
        """|coro|
        Called when the connected web-socket parses a received
        ``Msg``/``MsgProto``

        Parameters
        ----------
        msg: Union[:class:`~steam.protobufs.Msg`, :class:`~steam.protobufs.MsgProto`]
            The received message.
        """

    async def on_socket_raw_receive(self, message: bytes):
        """|coro|
        Called when the connected web-socket receives
        raw :class:`bytes`. This isn't likely to be very useful.

        Parameters
        ----------
        message: bytes
            The raw received message.
        """

    async def on_socket_send(self, msg: Union["Msg", "MsgProto"]):
        """|coro|
        Called when the client sends a parsed ``Msg``/``MsgProto``
        to the connected web-socket.

        Parameters
        ----------
        msg: Union[:class:`~steam.protobufs.Msg`, :class:`~steam.protobufs.MsgProto`]
            The sent message.
        """

    async def on_socket_raw_send(self, message: bytes):
        """|coro|
        Called when the client sends raw :class:`bytes`
        to the connected web-socket.
        This isn't likely to be very useful.

        Parameters
        ----------
        message: bytes
            The raw sent message.
        """

    @overload
    def wait_for(
        self, event: str, *, check: Optional[Callable[..., bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[Any]":
        ...

    @overload
    def wait_for(
        self, event: Literal["connect"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[None]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["disconnect"],
        *,
        check: Optional[Callable[[], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[None]":
        ...

    @overload  # don't know why you'd do this
    def wait_for(
        self, event: Literal["ready"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[None]":
        ...

    @overload
    def wait_for(
        self, event: Literal["login"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> "asyncio.Future[None]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["error"],
        *,
        check: Optional[Callable[[str, Exception, Any, Any], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[str, Exception, Any, Any]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["message"],
        *,
        check: Optional[Callable[["steam.Message"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[steam.Message]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["comment"],
        *,
        check: Optional[Callable[["Comment"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Comment]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["user_update"],
        *,
        check: Optional[Callable[["User", "User"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[User, User]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["typing"],
        *,
        check: Optional[Callable[["User", datetime.datetime], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Tuple[User, datetime.datetime]]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_receive"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_send"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_accept"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_decline"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_cancel"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_expire"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["trade_counter"],
        *,
        check: Optional[Callable[["TradeOffer"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[TradeOffer]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["user_invite"],
        *,
        check: Optional[Callable[["UserInvite"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[UserInvite]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["clan_invite"],
        *,
        check: Optional[Callable[["ClanInvite"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[ClanInvite]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_receive"],
        *,
        check: Optional[Callable[[Msgs], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Msgs]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_raw_receive"],
        *,
        check: Optional[Callable[[bytes], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[bytes]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_send"],
        *,
        check: Optional[Callable[["Msgs"], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[Msgs]":
        ...

    @overload
    def wait_for(
        self,
        event: Literal["socket_raw_send"],
        *,
        check: Optional[Callable[[bytes], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> "asyncio.Future[bytes]":
        ...

    def wait_for(
        self, event: str, *, check: Optional[Callable[..., bool]] = None, timeout: Optional[float] = None
    ) -> "asyncio.Future[Any]":
        """|coro|
        Wait for the first event to be dispatched that meets the requirements, this by default is the first event
        with a matching event name.

        Parameters
        -----------
        event: :class:`str`
            The event name from the `event reference <https://steampy.rtfd.io/en/latest/api.html#id1>`_, but without
            the ``on_`` prefix, to wait for.
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
        Returns ``None``, a single argument, or a :class:`tuple` of multiple arguments that mirrors the
        parameters for the ``event`` parameter from the `event reference <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_.
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
        return asyncio.wait_for(future, timeout)
