# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.

This is a slightly modified version of
https://github.com/Rapptz/discord.py/blob/master/discord/client.py
"""

import asyncio
import logging
import signal
import sys
import traceback
from typing import Union, List

import aiohttp
import websockets

from . import errors
from .enums import ECurrencyCode
from .gateway import SteamWebSocket, ResumeSocket
from .guard import generate_one_time_code
from .http import HTTPClient
from .market import Market
from .models import Game
from .state import State
from .user import make_steam64

log = logging.getLogger(__name__)


def _cancel_tasks(loop):
    try:
        task_retriever = asyncio.Task.all_tasks
    except AttributeError:
        # future proofing for 3.9 I guess
        task_retriever = asyncio.all_tasks

    tasks = {t for t in task_retriever(loop=loop) if not t.done()}

    if not tasks:
        return

    log.info(f'Cleaning up after {len(tasks)} tasks.')
    for task in tasks:
        task.cancel()

    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
    log.info('All tasks finished cancelling.')

    for task in tasks:
        if task.cancelled():
            continue
        if task.exception() is not None:
            loop.call_exception_handler({
                'message': 'Unhandled exception during Client.run shutdown.',
                'exception': task.exception(),
                'task': task
            })


def _cleanup_loop(loop):
    try:
        _cancel_tasks(loop)
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        log.info('Closing the event loop.')
        loop.close()


class _ClientEventTask(asyncio.Task):
    def __init__(self, original_coro, event_name, coro, *, loop):
        super().__init__(coro, loop=loop)
        self.__event_name = event_name
        self.__original_coro = original_coro

    def __repr__(self):
        info = [
            ('state', self._state.lower()),
            ('event', self.__event_name),
            ('coro', repr(self.__original_coro)),
        ]
        if self._exception is not None:
            info.append(('exception', repr(self._exception)))
        return f'<ClientEventTask {" ".join(f"{t}={t}" for t in info)}>'


class Client:
    """Represents a client connection that connects to Steam.
    This class is used to interact with the Steam API.

    Parameters
    ----------
    loop: Optional[:class:`asyncio.AbstractEventLoop`]
        The :class:`asyncio.AbstractEventLoop` used for asynchronous operations.
        Defaults to ``None``, in which case the default event loop is used via
        :func:`asyncio.get_event_loop()`.
    currency: Optional[Union[:class:`~steam.ECurrencyCode`, :class:`int`, :class:`str`]]
        The currency used for market interactions.
        Defaults to :class:`~steam.ECurrencyCode.USD`.

    Attributes
    -----------
    loop: :class:`asyncio.AbstractEventLoop`
        The event loop that the client uses for HTTP requests.
    """

    def __init__(self, loop=None, **options):
        self.loop = loop or asyncio.get_event_loop()
        self._session = aiohttp.ClientSession(loop=self.loop)

        self.http = HTTPClient(loop=self.loop, session=self._session, client=self)
        self._connection = State(loop=self.loop, client=self, http=self.http)
        self._market = Market(http=self.http, currency=options.get('currency', ECurrencyCode.USD))

        self.username = None
        self.api_key = None
        self.password = None
        self.shared_secret = None
        self.identity_secret = None
        self.shared_secret = None

        self._user = None
        self._closed = True
        self._state = None
        self._listeners = {}
        self._ready = asyncio.Event()

    @property
    def user(self):
        """Optional[:class:`~steam.ClientUser`]: Represents the connected client.
        ``None`` if not logged in."""
        return self._user

    @property
    def users(self):
        """List[:class:`~steam.User`]: Returns a list of all the users the account can see."""
        return self._connection.users

    @property
    def trades(self):
        """List[:class:`~steam.TradeOffer`]: Returns a list of all the trades the user has seen."""
        return self._connection.trades

    @property
    def code(self):
        """Optional[:class:`str`]: The current steam guard code.
        ``None`` if no shared_secret is passed"""
        return generate_one_time_code(self.shared_secret) if self.shared_secret else None

    @property
    def latency(self):
        return float('nan') if self.ws is None else self.ws.latency

    def event(self, coro):
        """A decorator that registers an event to listen to.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Example
        ---------

        Usage::

            @client.event
            async def on_ready():
                print('Ready!')

        Raises
        --------
        TypeError
            The coroutine passed is not a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('Event registered must be a coroutine function')

        setattr(self, coro.__name__, coro)
        log.debug(f'{coro.__name__} has successfully been registered as an event')
        return coro

    async def _run_event(self, coro, event_name, *args, **kwargs):
        try:
            await coro(*args, **kwargs)
        except asyncio.CancelledError:
            pass
        except Exception:
            try:
                await self.on_error(event_name, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    def _schedule_event(self, coro, event_name, *args, **kwargs):
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        # Schedules the task
        return _ClientEventTask(original_coro=coro, event_name=event_name, coro=wrapped, loop=self.loop)

    def dispatch(self, event, *args, **kwargs):
        log.debug(f'Dispatching event {event}')
        method = f'on_{event}'

        listeners = self._listeners.get(event)
        if listeners:
            removed = []
            for i, (future, condition) in enumerate(listeners):
                if future.cancelled():
                    removed.append(i)
                    continue

                try:
                    result = condition(*args)
                except Exception as exc:
                    future.set_exception(exc)
                    removed.append(i)
                else:
                    if result:
                        if len(args) == 0:
                            future.set_result(None)
                        elif len(args) == 1:
                            future.set_result(args[0])
                        else:
                            future.set_result(args)
                        removed.append(i)

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

    def is_ready(self):
        """Specifies if the client's internal cache is ready for use."""
        return self._ready.is_set()

    def run(self, *args, **kwargs):
        """A blocking call that abstracts away the event loop
        initialisation from you.

        If you want more control over the event loop then this
        function should not be used. Use :meth:`start` coroutine
        or :meth:`login`."""
        loop = self.loop

        try:
            loop.add_signal_handler(signal.SIGINT, lambda: loop.stop())
            loop.add_signal_handler(signal.SIGTERM, lambda: loop.stop())
        except NotImplementedError:
            pass

        async def runner():
            try:
                await self.start(*args, **kwargs)
            finally:
                await self.close()

        def stop_loop_on_completion(f):
            loop.stop()

        task = loop.create_task(runner())
        task.add_done_callback(stop_loop_on_completion)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            log.info('Received signal to terminate bot and event loop.')
        finally:
            task.remove_done_callback(stop_loop_on_completion)
            log.info('Cleaning up tasks.')
            _cleanup_loop(loop)

        if not task.cancelled():
            return task.result()

    def is_closed(self):
        """Indicates if the API connection is closed."""
        return self._closed

    async def on_error(self, event_method, *args, **kwargs):
        """|coro|
        The default error handler provided by the client.
        """
        print(f'Ignoring exception in {event_method}', file=sys.stderr)
        traceback.print_exc()

    async def login(self, username: str, password: str, api_key: str,
                    shared_secret: str = None, identity_secret: str = None):
        """|coro|
        Logs in a Steam account and the Steam API with the specified credentials.

        Parameters
        ----------
        username: :class:`str`
            The username of the desired Steam account.
        password: :class:`str`
            The password of the desired Steam account.
        api_key: Optional[:class:`str`]
            The accounts api key for fetching info about the account.
            This can be left and the library will fetch it for you.
        shared_secret: Optional[:class:`str`]
            The shared_secret of the desired Steam account,
            used to generate the 2FA code for login.
        identity_secret: Optional[:class:`str`]
            The identity_secret of the desired Steam account,
            used to generate trade confirmations.

        Raises
        ------
        :exc:`.InvalidCredentials`
            The wrong credentials are passed.
        :exc:`.HTTPException`
            An unknown HTTP related error occurred.
        """
        log.info(f'Logging in as {username}')
        self.api_key = api_key
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        if identity_secret is None:
            log.info('Trades will not be automatically accepted when sent as no identity_secret was passed')

        await self.http.login(username=username, password=password, api_key=api_key,
                              shared_secret=shared_secret, identity_secret=identity_secret)
        self._user = self.http.user
        self._closed = False

    async def close(self):
        """|coro|
        Closes the connection to Steam CMs and logs out.
        """
        if self._closed:
            return

        # await self.ws.close()
        await self.http.logout()
        await self._session.close()
        self._closed = True
        self._ready.clear()

    def clear(self):
        """Clears the internal state of the bot.
        After this, the bot can be considered "re-opened", i.e. :meth:`is_closed`
        and :meth:`is_ready` both return ``False``.
        """
        self._closed = False
        self._ready.clear()
        self.http.recreate()
        #self.loop.create_task(self.ws.close())

    async def start(self, *args, **kwargs):
        """|coro|
        A shorthand coroutine for :meth:`login` and :meth:`connect`

        Raises
        ------
        TypeError
            An unexpected keyword argument was received.
        :exc:`.InvalidCredentials`
            The wrong credentials are passed.
        :exc:`.HTTPException`
            An unknown HTTP related error occurred.
        """
        api_key = kwargs.pop('api_key', None)
        username = kwargs.pop('username', None)
        password = kwargs.pop('password', None)
        shared_secret = kwargs.pop('shared_secret', None)
        identity_secret = kwargs.pop('identity_secret', None)
        if kwargs:
            raise TypeError(f"Unexpected keyword argument(s) {list(kwargs.keys())}")
        if not (username or password):
            raise errors.LoginError("One or more required login detail is missing")

        await self.login(username=username, password=password, api_key=api_key,
                         shared_secret=shared_secret, identity_secret=identity_secret)
        await self._connection.poll_trades()
        #await self.connect()
        while 1:
            await asyncio.sleep(5)

    async def _connect(self):
        self.ws = SteamWebSocket()
        coro = self.ws.from_client(self)
        await asyncio.wait_for(coro, timeout=180.0)
        while 1:
            try:
                await self.ws.poll_event()
            except ResumeSocket:
                log.info('Got a request to RESUME the websocket.')
                self.dispatch('disconnect')
                coro = self.ws.from_client(self)
                await asyncio.wait_for(coro, timeout=180.0)

    async def connect(self):
        while not self.is_closed():
            try:
                await self._connect()
            except (OSError,
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    errors.HTTPException,
                    websockets.InvalidHandshake,
                    websockets.WebSocketProtocolError):
                self.dispatch('disconnect')
                if self.is_closed():
                    break

    def get_user(self, user_id):
        """Returns a user with the given ID.

        Parameters
        ----------
        user_id: Union[:class:`int`, :class:`str`]
            The ID to search for. For accepted IDs see
            :meth:`~steam.make_steam64`

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if not found.
        """
        id64 = make_steam64(user_id)
        return self._connection.get_user(id64)

    async def fetch_user(self, user_id):
        """|coro|
        Fetches a user from the API with the given ID.

        Parameters
        ----------
        user_id: Union[:class:`int`, :class:`str`]
            The ID to search for. For accepted IDs see
            :meth:`~steam.make_steam64`

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if not found.
        """
        id64 = make_steam64(user_id)
        return await self._connection.fetch_user(id64)

    def get_trade(self, id):
        """Get a trade from cache.

        Parameters
        ----------
        id: :class:`int`
            The id of the trade to search for from the cache.

        Returns
        -------
        Optional[:class:`~steam.TradeOffer`]
            The trade offer or ``None`` if not found.
        """
        return self._connection.get_trade(id)

    async def fetch_trade(self, id):
        """|coro|
        Fetches a trade from the API with the given ID.

        .. note::
            The partner's id from the API is often incorrect,
            relying the on getting the correct partner would be inadvisable.

        Parameters
        ----------
        id: :class:`int`
            The id of the trade to search for from the API.

        Returns
        -------
        Optional[:class:`~steam.TradeOffer`]
            The trade offer or ``None`` if not found.
        """
        return await self._connection.fetch_trade(id)

    async def fetch_price(self, item_name: str, game: Game):
        """Gets the price(s) and volume sales of an item.

        Parameters
        ----------
        item_name: str
            The name of the item to fetch the price of.
        game: :class:`~steam.Game`
            The game the item is from.

        Returns
        -------
        :class:`PriceOverview`
            A class to represent the data from these transactions
        """
        return await self._market.fetch_price(item_name, game)

    async def fetch_prices(self, item_names: List[str], games: Union[List[Game], Game]):
        """Get the price(s) and volume of each item in the list.

        Parameters
        ----------
        item_names: List[:class:`str`]
            A list of the items to get the prices for.
        games: Union[List[:class:`~steam.Game`], :class:`~steam.Game`]
            A list of :class:`~steam.Game`s or :class:`~steam.Game` the items are from.

        Returns
        -------
        Mapping
            A mapping of the prices. {item_name: :class:`PriceOverview`}
        """
        return self._market.fetch_prices(item_names, games)

    async def create_listing(self, item_name: str, game: Game, *, price: float):
        """Creates a market listing for an item.

        .. note::
            This could result in an account termination,
            this is just added for completeness sake.

        Parameters
        ----------
        item_name: :class:`str`
            The name of the item to order.
        game: :class:`~steam.Game`
            The game the item is from.
        price: Union[:class:`int`, :class:`float`]
            The price to pay for the item in decimal form.
            eg. $1 = 1.00 or £2.50 = 2.50 etc.
        """
        return self._market.create_listing(item_name, game, price=price)

    async def create_listings(self, item_names: List[str], games: Union[List[Game], Game],
                              prices: Union[List[Union[int, float]], Union[int, float]]):
        """Creates market listing for items.

        .. note::
            This could result in an account termination,
            this is just added for completeness sake.

        Parameters
        ----------
        item_names: List[:class:`str`]
            A list of item names to order.
        games: Union[List[:class:`~steam.Game`], :class:`~steam.Game`]
            The game the item(s) is/are from.
        prices: Union[List[Union[:class:`int`, :class:`float`]], Union[:class:`int`, :class:`float`]]
            The price to pay for each item in decimal form.
            eg. $1 = 1.00 or £2.50 = 2.50 etc.
        """
        return await self._market.create_listings(item_names, games, prices=prices)

    async def wait_until_ready(self):
        """|coro|
        Waits until the client's internal cache is all ready.
        """
        await self._ready.wait()

    def wait_for(self, event, *, check=None, timeout=None):
        """|coro|
        Waits for an event to be dispatched.

        The ``timeout`` parameter is passed onto :func:`asyncio.wait_for`. By default,
        it does not timeout. Note that this does propagate the
        :exc:`asyncio.TimeoutError` for you in case of timeout and is provided for
        ease of use.
        In case the event returns multiple arguments, a :class:`tuple` containing those
        arguments is returned instead. Please check the
        :ref:`documentation <steam-api-event-reference>` for a list of events and their
        parameters.
        This function returns the **first event that meets the requirements**.

        Parameters
        ------------
        event: :class:`str`
            The event name, similar to the :ref:`event reference <steam-api-event-reference>`,
            but without the ``on_`` prefix, to wait for.
        check: Optional[Callable[..., :class:`bool`]]
            A predicate to check what to wait for. The arguments must meet the
            parameters of the event being waited for.
        timeout: Optional[:class:`float`]
            The number of seconds to wait before timing out and raising
            :exc:`asyncio.TimeoutError`.

        Raises
        -------
        asyncio.TimeoutError
            If a timeout is provided and it was reached.

        Returns
        --------
        Any
            Returns no arguments, a single argument, or a :class:`tuple` of multiple
            arguments that mirrors the parameters passed in the
            :ref:`event reference <steam-api-event-reference>`.
        """

        future = self.loop.create_future()
        if check is None:
            def _check(*args):
                return True

            check = _check

        ev = event.lower()
        try:
            listeners = self._listeners[ev]
        except KeyError:
            listeners = []
            self._listeners[ev] = listeners

        listeners.append((future, check))
        return asyncio.wait_for(future, timeout)
