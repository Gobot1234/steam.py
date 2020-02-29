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

import aiohttp

from . import errors
from .guard import generate_one_time_code
from .http import HTTPClient
from .market import Market
from .trade import TradeOffer
from .user import User, SteamID

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
    r"""Represents a client connection that connects to Steam.
    This class is used to interact with the Steam API.

    Parameters
    ----------
    loop: Optional[:class:`asyncio.AbstractEventLoop`]
        The :class:`asyncio.AbstractEventLoop` used for asynchronous operations.
        Defaults to ``None``, in which case the default event loop is used via
        :func:`asyncio.get_event_loop()`.

    Attributes
    -----------
    loop: :class:`asyncio.AbstractEventLoop`
        The event loop that the client uses for HTTP requests.
    market: :class:`~steam.Market`
        Represents the market instance given to the client
    """

    def __init__(self, loop=None, **options):
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self._session = aiohttp.ClientSession(loop=self.loop)

        self.http = HTTPClient(loop=self.loop, session=self._session, client=self)
        self.market = Market(http=self.http, currency=options.get('currency', 1))

        self.username = None
        self.api_key = None
        self.password = None
        self.shared_secret = None
        self.identity_secret = None
        self.shared_secret = None

        self._user = None
        self._users = {}
        self._trades = {}
        self._closed = True
        self._listeners = {}
        self._handlers = {
            'ready': self._handle_ready
        }
        self._ready = asyncio.Event()

    @property
    def user(self):
        """Optional[:class:`~steam.user.ClientUser`]: Represents the connected client.
        ``None`` if not logged in."""
        return self._user

    @property
    def users(self):
        """List[:class:`~steam.User`]: Returns a list of all the users the account can see."""
        return list(self._users.values())

    @property
    def code(self):
        """Optional[:class:`str`]: The current steam guard code.
        ``None`` if no shared_secret is passed"""
        return generate_one_time_code(self.shared_secret) if self.shared_secret else None

    def event(self, coro):
        """A decorator that registers an event to listen to.
        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.
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
                await asyncio.sleep(120)
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

    def _handle_ready(self):
        self._ready.set()

    def is_closed(self):
        """Indicates if the API connection is closed."""
        return self._closed

    def is_logged_in(self):
        """Indicates if the bot is logged in."""
        return self.http._logged_in

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
        api_key: :class:`str`
            The accounts api key for fetching info about the account.
        shared_secret: Optional[:class:`str`]
            The shared_secret of the desired Steam account,
            used to generate the 2FA code for login.
        identity_secret: Optional[:class:`str`]
            The identity_secret of the desired Steam account,
            used to generate trade confirmations.

        Raises
        ------
        :exc:`.LoginFailure`
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

        await self.http.login(username=username, password=password,
                              api_key=api_key, shared_secret=shared_secret,
                              identity_secret=identity_secret)
        self._user = self.http._user
        self._closed = False

    async def close(self):
        """|coro|
        Closes the connection to the Steam web API and logs out.
        """
        if self._closed:
            return

        await self.http.logout()
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

    async def start(self, *args, **kwargs):
        """|coro|
        A shorthand coroutine for :meth:`login`.
        Doesn't do much at the moment.

        Raises
        ------
        TypeError
            An unexpected keyword argument was received.
        :class:`~steam.errors.LoginError`
            Login details were missing
        """
        api_key = kwargs.pop('api_key', None)
        username = kwargs.pop('username', None)
        password = kwargs.pop('password', None)
        shared_secret = kwargs.pop('shared_secret', None)
        identity_secret = kwargs.pop('identity_secret', None)
        if kwargs:
            raise TypeError(f"Unexpected keyword argument(s) {list(kwargs.keys())}")
        if not (api_key or username or password):
            raise errors.LoginError("One or more required login detail is missing")

        await self.login(username=username, password=password, api_key=api_key,
                         shared_secret=shared_secret, identity_secret=identity_secret)

    def get_user(self, user_id):
        """Returns a user with the given ID.

        Parameters
        ----------
        user_id: Union[:class:`int`, :class:`str`]
            The ID to search for. For accepted IDs see
            :meth:`~steam.User.make_steam64`

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if not found.
        """
        steam_id = SteamID(user_id)
        return self._users.get(steam_id.as_64)

    async def fetch_user(self, user_id):
        """|coro|
        Fetches a user from the API with the given ID.

        Parameters
        ----------
        user_id: Union[:class:`int`, :class:`str`]
            The ID to search for. For accepted IDs see
            :meth:`~steam.User.make_steam64`

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if not found.
        """
        steam_id = SteamID(user_id)
        data = await self.http.fetch_profile(steam_id.as_64)
        if data:
            self._store_user(data)
        return None

    def _store_user(self, data):
        # this way is 300% faster than `dict.setdefault`.
        try:
            return self._users[int(data['steamid'])]
        except KeyError:
            user = User(state=self.http._state, data=data)
            self._users[user.id64] = user
            return user

    def get_trade(self, trade_id):
        """Get a trade from cache.

        Parameters
        ----------
        trade_id: int
            The id to search for from the cache.

        Returns
        -------
        Optional[:class:`~steam.TradeOffer`]
            The trade offer or ``None`` if not found.
        """
        return self._trades.get(trade_id)

    async def fetch_trade(self, trade_id):
        data = await self.http.fetch_trade(trade_id)
        self._store_trade(data)

    def _store_trade(self, data):
        try:
            return self._trades[data['tradeofferid']]
        except KeyError:
            offer = TradeOffer(state=self.http._state, data=data)
            self._trades[offer.id] = offer
            return offer
