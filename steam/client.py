import asyncio
import logging
import sys
import traceback
import signal

from aiohttp import ClientSession, CookieJar

from .https import HTTPClient
from .state import State
from .user import ClientUser


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


# this all looks rather familiar
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
        self._session = ClientSession(loop=loop, cookie_jar=CookieJar(),
                                      headers={"User-Agent": f'steam.py/{__import__("steam").__version__}'})

        self.http = HTTPClient(loop=self.loop, session=self._session, client=self)
        self.state = State(loop=self.loop, http=self.http)
        self.username = None
        self.password = None
        self.shared_secret = None
        self.identity_secret = None
        self.shared_secret = None

        self._user = None
        self._listeners = {}
        self._closed = True
        self._handlers = {
            'ready': self._handle_ready
        }
        self._ready = asyncio.Event()

    def event(self, coro):
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

    @property
    def user(self):
        """Optional[:class:`.ClientUser`]: Represents the connected client. None if not logged in."""
        return self._user

    async def on_error(self, event_method, *args, **kwargs):
        """|coro|
        The default error handler provided by the client.
        """
        print(f'Ignoring exception in {event_method}', file=sys.stderr)
        traceback.print_exc()

    async def login(self, username: str, password: str, shared_secret: str,
                    identity_secret: str = None):
        """|coro|
        Login to the Steam API and an account.
        """
        log.info(f'Logging in as {username}')
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        await self.http.login(username=self.username, password=self.password,
                              shared_secret=self.shared_secret)
        self._user = ClientUser(state=self.state)
        self._closed = False
        print(self._user)

    async def close(self):
        """|coro|
        Closes the connection to the Steam web API and logs out.
        """
        if self._closed:
            return

        await self.http.logout()
        self._closed = True
        self._ready.clear()

    async def start(self, *args, **kwargs):
        username = kwargs.pop('username', None)
        password = kwargs.pop('password', None)
        shared_secret = kwargs.pop('shared_secret', None)
        identity_secret = kwargs.pop('identity_secret', None)
        if kwargs:
            raise TypeError(f"unexpected keyword argument(s) {list(kwargs.keys())}")

        await self.login(username=username, password=password,
                         shared_secret=shared_secret, identity_secret=identity_secret)
