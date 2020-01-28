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

from aiohttp import ClientSession, CookieJar

from . import __version__
from .https import HTTPClient
from .market import Market
from .state import State
from .user import User, SteamID

log = logging.getLogger(__name__)


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
    """

    def __init__(self, loop=None, **options):
        self.loop = asyncio.get_event_loop() if loop is None else loop
        self._session = ClientSession(
            loop=loop, cookie_jar=CookieJar(),
            headers={"User-Agent": f'steam.py/{__version__}'}
        )

        self.http = HTTPClient(loop=self.loop, session=self._session, client=self)
        self.state = State(loop=self.loop, http=self.http)
        self.market = Market(session=self._session)

        self.username = None
        self.password = None
        self.shared_secret = None
        self.identity_secret = None
        self.shared_secret = None

        self._user = None
        self._keep_alive = None
        self._listeners = {}
        self._closed = True
        self._handlers = {
            'ready': self._handle_ready
        }
        self._ready = asyncio.Event()

    @property
    def user(self):
        """Optional[:class:`user.ClientUser`]: Represents the connected client.
        ``None`` if not logged in."""
        return self._user

    def event(self, coro):
        """A decorator that registers an event to listen to.
        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.
        """
        if not asyncio.iscoroutinefunction(coro):
            self.loop.run_until_complete(self.http.logout())
            raise TypeError('Event registered must be a coroutine function')

        setattr(self, coro.__name__, coro)
        log.debug(f'{coro.__name__} has successfully been registered as an event', )
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

        future = asyncio.ensure_future(runner(), loop=loop)
        future.add_done_callback(stop_loop_on_completion)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            log.info('Received signal to terminate bot and event loop.')
        finally:
            future.remove_done_callback(stop_loop_on_completion)
            log.info('Cleaning up tasks.')
            loop.close()

        if not future.cancelled():
            return future.result()

    def _handle_ready(self):
        self._ready.set()

    def is_closed(self):
        """Indicates if the API connection is closed."""
        return self._closed

    async def on_error(self, event_method, *args, **kwargs):
        """|coro|
        The default error handler provided by the client.
        """
        print(f'Ignoring exception in {event_method}', file=sys.stderr)
        traceback.print_exc()

    async def login(self, username: str, password: str, shared_secret: str, identity_secret: str = None):
        """|coro|
        Logs in a Steam account and the Steam API with the specified credentials.

        Parameters
        ----------
        username: :class:`str`
            The username of the desired Steam account.
        password: :class:`str`
            The password of the desired Steam account.
        shared_secret: :class:`str`
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
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        await self.http.login(username=self.username, password=self.password,
                              shared_secret=self.shared_secret)
        self._user = self.http._user
        self._closed = False
        self._handle_ready()

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
        """
        username = kwargs.pop('username', None)
        password = kwargs.pop('password', None)
        shared_secret = kwargs.pop('shared_secret', None)
        identity_secret = kwargs.pop('identity_secret', None)
        if kwargs:
            raise TypeError(f"Unexpected keyword argument(s) {list(kwargs.keys())}")

        await self.login(username=username, password=password,
                         shared_secret=shared_secret, identity_secret=identity_secret)

    async def get_user(self, user_id):  # TODO cache these to make this not a coro
        """Returns a user with the given ID.

        Parameters
        ----------
        user_id: :class:`Union`[:class:`int`, :class:`str`]
            The ID to search for. For accepted IDs see
            :meth:`~steam.User.make_steam64`

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if not found.
        """
        user = SteamID(user_id)
        data = await self.http.mini_profile(user.as_steam3)
        data['id64'] = user.as_64
        return User(state=self.state, data=data)
