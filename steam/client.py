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

This is a slightly modified version of discord's client
https://github.com/Rapptz/discord.py/blob/master/discord/client.py
"""

import asyncio
import logging
import math
import signal
import sys
import traceback
from datetime import datetime
from typing import Union, List, Optional, Any, Callable, Mapping, TYPE_CHECKING

import aiohttp

from . import errors
from .enums import ECurrencyCode
from .gateway import *
from .group import Group
from .guard import generate_one_time_code
from .http import HTTPClient
from .iterators import MarketListingsIterator, TradesIterator
from .market import convert_items, Listing, FakeItem, MarketClient, PriceOverview
from .models import URL
from .state import ConnectionState
from .user import make_steam64
from .utils import find

if TYPE_CHECKING:
    from .game import Game
    from .models import Comment, Invite
    from .trade import TradeOffer
    from .user import ClientUser, User

    import steam

__all__ = (
    'Client',
)

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


class ClientEventTask(asyncio.Task):
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
    This class is used to interact with the Steam API and CMs.

    Parameters
    ----------
    loop: Optional[:class:`asyncio.AbstractEventLoop`]
        The :class:`asyncio.AbstractEventLoop` used for asynchronous operations.
        Defaults to ``None``, in which case the default event loop is used via
        :func:`asyncio.get_event_loop()`.
    currency: Optional[Union[:class:`~steam.ECurrencyCode`, :class:`int`, :class:`str`]]
        The currency used for market interactions. Defaults to :class:`~steam.ECurrencyCode.USD`.

    Attributes
    -----------
    loop: :class:`asyncio.AbstractEventLoop`
        The event loop that the client uses for HTTP requests.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop = None, **options):
        self.loop = loop or asyncio.get_event_loop()
        self._session = aiohttp.ClientSession(loop=self.loop)

        self.http = HTTPClient(loop=self.loop, session=self._session, client=self)
        self._connection = ConnectionState(loop=self.loop, client=self, http=self.http)
        self._market = MarketClient(loop=self.loop, session=self._session, client=self,
                                    currency=options.get('currency', ECurrencyCode.USD))
        self.username = None
        self.api_key = None
        self.password = None
        self.shared_secret = None
        self.identity_secret = None
        self.shared_secret = None
        self.token = None

        self._user = None
        self._closed = True
        self._cm_list = None
        self._confirmation_manager = None
        self._listeners = {}
        self._ready = asyncio.Event()

    @property
    def user(self) -> Optional['ClientUser']:
        """Optional[:class:`~steam.ClientUser`]: Represents the connected client.
        ``None`` if not logged in."""
        return self.http.user

    @property
    def users(self) -> List['User']:
        """List[:class:`~steam.User`]: Returns a list of all the users the account can see."""
        return self._connection.users

    @property
    def trades(self) -> List['TradeOffer']:
        """List[:class:`~steam.TradeOffer`]: Returns a list of all the trades the user has seen."""
        return self._connection.trades

    @property
    def listings(self) -> List[Listing]:
        """List[:class:`~steam.Listing`]: Returns a list of all the listings the ClientUser has."""
        return self._connection.listings

    @property
    def code(self) -> Optional[str]:
        """Optional[:class:`str`]: The current steam guard code.

        .. warning::
            Will wait for a Steam guard code using :func``input`
            if no shared_secret is passed to :meth:`run` or :meth:`start`.
            **This could be blocking.**
        """
        if self.shared_secret:
            return generate_one_time_code(self.shared_secret)
        else:
            return input('Please enter a Steam guard code\n>>> ')

    @property
    def latency(self) -> float:
        """:class:`float`: Measures latency between a HEARTBEAT and a HEARTBEAT_ACK in seconds."""
        return float('nan') if self.ws is None else self.ws.latency

    def event(self, coro):
        """A decorator that registers an event to listen to.

        The events must be a :ref:`coroutine <coroutine>`, if not, :exc:`TypeError` is raised.

        Usage::

            @client.event
            async def on_ready():
                print('Ready!')

        Raises
        --------
        TypeError
            The function passed is not a coroutine.
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
        except Exception as exc:
            try:
                await self.on_error(event_name, exc, *args, **kwargs)
            except asyncio.CancelledError:
                pass

    def _schedule_event(self, coro, event_name, *args, **kwargs):
        wrapped = self._run_event(coro, event_name, *args, **kwargs)
        # schedules the task
        return ClientEventTask(original_coro=coro, event_name=event_name, coro=wrapped, loop=self.loop)

    def dispatch(self, event: str, *args, **kwargs) -> None:
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

    def is_ready(self) -> bool:
        """Specifies if the client's internal cache is ready for use."""
        return self._ready.is_set()

    def run(self, *args, **kwargs):
        """
        A blocking call that abstracts away the event loop
        initialisation from you.

        If you want more control over the event loop then this
        function should not be used. Use :meth:`start` coroutine
        or :meth:`login`.
        """
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

        def stop_loop_on_completion(_):
            loop.stop()

        task = loop.create_task(runner())
        task.add_done_callback(stop_loop_on_completion)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            log.info('Received signal to terminate the client and event loop.')
        finally:
            task.remove_done_callback(stop_loop_on_completion)
            log.info('Cleaning up tasks.')
            _cleanup_loop(loop)

        if not task.cancelled():
            return task.result()

    def is_closed(self) -> bool:
        """Indicates if the API connection is closed."""
        return self._closed

    async def login(self, username: str, password: str, api_key: str, shared_secret: str = None) -> None:
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

        Raises
        ------
        :exc:`.InvalidCredentials`
            The wrong credentials are passed.
        :exc:`.HTTPException`
            An unknown HTTP related error occurred.
        :exc:`.NoCMFound`
            No community managers could be found to connect to.
        """
        log.info(f'Logging in as {username}')
        self.api_key = api_key
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        await self.http.login(username=username, password=password, api_key=api_key, shared_secret=shared_secret)

    async def close(self) -> None:
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

    def clear(self) -> None:
        """Clears the internal state of the bot.
        After this, the bot can be considered "re-opened", i.e. :meth:`is_closed`
        and :meth:`is_ready` both return ``False``.
        """
        self._closed = False
        self._ready.clear()
        self.http.recreate()
        # self.loop.create_task(self.ws.close())

    async def start(self, *args, **kwargs) -> None:
        """|coro|
        A shorthand coroutine for :meth:`login` and :meth:`connect`.
        If no shared_secret is passed, you will have to manually
        enter a Steam guard code.

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
        self.api_key = api_key
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.identity_secret = identity_secret

        if identity_secret is None:
            log.info('Trades will not be automatically accepted when sent as no identity_secret was passed')
        if kwargs:
            raise TypeError(f"Unexpected keyword argument(s) {list(kwargs.keys())}")
        if not (username or password):
            raise errors.LoginError("One or more required login detail is missing")

        await self.login(username=username, password=password, api_key=api_key, shared_secret=shared_secret)
        await self._market.__ainit__()
        await self._connection.__ainit__()
        resp = await self.http.request('GET', url=f'{URL.COMMUNITY}/chat/clientjstoken')
        self.token = resp['token']
        self._closed = False
        self.dispatch('ready')

        # await self.connect()
        while 1:
            await asyncio.sleep(5)

    async def _connect(self):
        coro = SteamWebSocket.from_client(self)
        self.ws = await asyncio.wait_for(coro, timeout=60)
        while 1:
            try:
                await self.ws.poll_event()
            except ReconnectWebSocket as exc:
                log.info('Got a request to RESUME the websocket.')
                self.dispatch('disconnect')
                coro = SteamWebSocket.from_client(self, cm=exc.cm, cms=self._cm_list)
                self.ws = await asyncio.wait_for(coro, timeout=60)

    async def connect(self) -> None:
        while not self.is_closed():
            try:
                await self._connect()
            except (OSError,
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    errors.HTTPException):
                self.dispatch('disconnect')
            except ConnectionClosed as exc:
                self._cm_list = exc.cm_list
            finally:
                if self._closed:
                    return

                log.exception(f'Attempting a reconnect')
                # TODO add backoff

    # state stuff

    def get_user(self, *args, **kwargs) -> Optional['User']:
        """Returns a user with the given ID.

        Parameters
        ----------
        *args: Union[:class:`int`, :class:`str`]
            The arguments to pass to :meth:`~steam.make_steam64`.
        **kwargs: Union[:class:`int`, :class:`str`]
            The arguments to pass to :meth:`~steam.make_steam64`.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        id64 = make_steam64(*args, **kwargs)
        return self._connection.get_user(id64)

    async def fetch_user(self, *args, **kwargs) -> Optional['User']:
        """|coro|
        Fetches a user from the API with the given ID.

        Parameters
        ----------
        *args: Union[:class:`int`, :class:`str`]
            The arguments to pass to :meth:`~steam.make_steam64`.
        **kwargs: Union[:class:`int`, :class:`str`]
            The arguments to pass to :meth:`~steam.make_steam64`.

        Returns
        -------
        Optional[:class:`~steam.User`]
            The user or ``None`` if the user was not found.
        """
        id64 = make_steam64(*args, **kwargs)
        return await self._connection.fetch_user(id64)

    def get_trade(self, id) -> Optional['TradeOffer']:
        """Get a trade from cache.

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

    async def fetch_trade(self, id: int) -> Optional['TradeOffer']:
        """|coro|
        Fetches a trade from the API with the given ID.

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

    async def fetch_group(self, *args, **kwargs) -> Optional[Group]:
        """|coro|
        Fetches a group from https://steamcommunity.com with the given ID.

        Parameters
        ----------
        *args: Union[:class:`int`, :class:`str`]
            The arguments to pass to :meth:`~steam.make_steam64`.
        **kwargs: Union[:class:`int`, :class:`str`]
            The arguments to pass to :meth:`~steam.make_steam64`.

        Returns
        -------
        Optional[:class:`~steam.Group`]
            The group or ``None`` if the group was not found.
        """
        id = make_steam64(*args, **kwargs) & 0xFFffFFff
        group = Group(state=self._connection, id=id)
        await group.__ainit__()
        return group if group.name else None

    def get_listing(self, id) -> Optional[Listing]:
        """Gets a listing from cache.

        Parameters
        ----------
        id: :class:`int`
            The ID of the listing to get.

        Returns
        -------
        Optional[:class:`Listing`]
            The listing or ``None`` if the listing was not found.
        """
        return self._connection.get_listing(id)

    async def fetch_listings(self) -> List[Listing]:
        """|coro|
        Fetches a your market sell listings.

        Returns
        -------
        List[:class:`Listing`]
            A list of your listings.
        """
        resp = await self._market.fetch_pages()
        if not resp['total_count']:  # they have no listings just return
            return []

        total = math.ceil(resp['total_count'] / 100)
        listings = await self._market.fetch_listings(total)
        return [Listing(state=self._connection, data=listing) for listing in listings]

    def listing_history(self, limit=None, before: datetime = None, after: datetime = None) -> MarketListingsIterator:
        """An iterator for accessing a :class:`ClientUser`'s :class:`~steam.Listing` objects.

        Examples
        -----------

        Usage: ::

         async for listing in client.listing_history(limit=10):
            print('Sold listing:', listing.id)
            print('For:', listing.user_pays)

        Flattening into a list: ::

            listings = await client.listing_history(limit=50).flatten()
            # listings is now a list of Listing

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of listings to search through.
            Default is ``None`` which will fetch all the user's comments.
        before: Optional[:class:`datetime.datetime`]
            A time to search for trades before.
        after: Optional[:class:`datetime.datetime`]
            A time to search for trades after.

        Yields
        ---------
        :class:`~steam.Listing`
        """
        return MarketListingsIterator(state=self._connection, limit=limit, before=before, after=after)

    def trade_history(self, limit=100, before: datetime = None, after: datetime = None,
                      active_only: bool = False) -> TradesIterator:
        """An iterator for accessing a :class:`ClientUser`'s :class:`~steam.TradeOffer` objects.

        Examples
        -----------

        Usage: ::

            async for trade in client.trade_history(limit=10):
                print('Partner:', trade.partner, 'Sent:')
                print(', '.join([item.name if item.name else str(item.asset_id) for item in trade.items_to_receive])
                      if trade.items_to_receive else 'Nothing')

        Flattening into a list: ::

            trades = await client.trade_history(limit=50).flatten()
            # trades is now a list of TradeOffer

        All parameters are optional.

        Parameters
        ----------
        limit: Optional[:class:`int`]
            The maximum number of trades to search through.
            Default is 100 which will fetch the first 100 trades.
            Setting this to ``None`` will fetch all of the user's trades,
            but this will be a very slow operation.
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

    # market stuff

    async def fetch_price(self, item_name: str, game: 'Game') -> PriceOverview:
        """|coro|
        Fetches the price and volume sales of an item.

        Parameters
        ----------
        item_name: :class:`str`
            The name of the item to fetch the price of.
        game: :class:`~steam.Game`
            The game the item is from.

        Returns
        -------
        :class:`PriceOverview`
            The item's price overview.
        """
        item = FakeItem(item_name, game)
        return await self._market.fetch_price(item)

    async def fetch_prices(self, item_names: List[str],
                           games: Union[List['Game'], 'Game']) -> Mapping[str, PriceOverview]:
        """|coro|
        Fetches the price(s) and volume of each item in the list.

        Parameters
        ----------
        item_names: List[:class:`str`]
            A list of the items to get the prices for.
        games: Union[List[:class:`~steam.Game`], :class:`~steam.Game`]
            A list of :class:`~steam.Game`s or :class:`~steam.Game` the items are from.

        Returns
        -------
        Mapping[:class:`str`, :class:`PriceOverview`]
            A mapping of the prices of item names to price overviews.
        """
        items = convert_items(item_names, games)
        return await self._market.fetch_prices(items)

    async def create_sell_listing(self, item_name: str, game: 'Game', *, price: float) -> Listing:
        """|coro|
        Creates a market listing for an item.

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
            The price user pays for the item as a float.
            eg. $1 = 1.00 or £2.50 = 2.50 etc.
        """
        current_listings = await self.fetch_listings()
        item = FakeItem(item_name, game)
        await self._market.create_sell_listing(item, price=price)
        new_listing = find(lambda l: l not in current_listings, await self.fetch_listings())
        try:
            await new_listing.confirm()
        except errors.ConfirmationError:
            pass
        return new_listing

    async def create_sell_listings(self, item_names: List[str], games: Union[List['Game'], 'Game'],
                                   prices: Union[List[Union[int, float]], Union[int, float]]) -> List[Listing]:
        """|coro|
        Creates market listing for items.

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
            The price user pays for the item as a float.
            eg. $1 = 1.00 or £2.50 = 2.50 etc.
        """
        current_listings = await self.fetch_listings()
        to_list = []
        items = convert_items(item_names, games, prices)
        for (item, price) in items:
            final_price = price * items.count((item, price))
            to_list.append((item, final_price, items.count((item, price))))
            for (_, __) in items:
                items.remove((item, price))
        for (item, price) in items:  # idek wtf this is
            to_list.append((item, price, items.count((item, price))))
        await self._market.create_sell_listings(to_list)
        new_listings = [listing for listing in await self.fetch_listings() if listing not in current_listings]
        for listing in new_listings:
            try:
                await listing.confirm()
            except errors.ConfirmationError:
                pass
        return new_listings

    # misc

    async def wait_until_ready(self) -> None:
        """|coro|
        Waits until the client's internal cache is all ready.
        """
        await self._ready.wait()

    def wait_for(self, event: str, *, check: Callable[..., bool] = None, timeout: float = None) -> Any:
        """|coro|
        Waits for an event to be dispatched.

        The ``timeout`` parameter is passed to :func:`asyncio.wait_for`. By default,
        it does not timeout. Note that this does propagate the
        :exc:`asyncio.TimeoutError` for you in case of timeout and is provided for
        ease of use.
        In case the event returns multiple arguments, a :class:`tuple` containing those
        arguments is returned instead. Please check the
        `documentation <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_
        for a list of events and their parameters.

        .. note::
            This function returns the **first event that meets the requirements**.

        Parameters
        ------------
        event: :class:`str`
            The event name, similar to the
            `event reference <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_,
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
            If the provided timeout was reached.

        Returns
        --------
        Any
            Returns no arguments, a single argument, or a :class:`tuple` of multiple
            arguments that mirrors the parameters passed in the
            `event reference <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_.
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

    # events to be subclassed

    async def on_connect(self):
        """|coro|
        Called when the client has successfully connected to Steam. This is not
        the same as the client being fully prepared, see :func:`on_ready` for that.

        The warnings on :func:`on_ready` also apply.
        """
        pass

    async def on_disconnect(self):
        """|coro|
        Called when the client has disconnected from Steam. This could happen either through
        the internet disconnecting, an explicit call to logout, or Steam terminating the connection.

        This function can be called multiple times.
        """
        pass

    async def on_ready(self):
        """|coro|
        Called after a successful login and the client has handled setting up
        trade and notification polling, along with setup the confirmation manager.

        .. note::
            In future this will be called when the client is done preparing the data received from Steam.
            Usually after login to a CM is successful.

        .. warning::

            This function is not guaranteed to be the first event called.
            Likewise, this function is **not** guaranteed to only be called
            once. This library implements reconnection logic and will therefore
            end up calling this event whenever a RESUME request fails.
        """
        pass

    async def on_login(self):
        """|coro|
        Called when the client has logged into https://steamcommunity.com and
        the :class:`~steam.ClientUser` is setup along with its friends list.
        """
        pass

    async def on_error(self, event_method: str, error: Exception, *args, **kwargs):
        """|coro|
        The default error handler provided by the client.

        Usually when an event raises an uncaught exception, a traceback is
        printed to stderr and the exception is ignored. If you want to
        change this behaviour and handle the exception for whatever reason
        yourself, this event can be overridden. Which, when done, will
        suppress the default action of printing the traceback.

        The information of the exception raised and the exception itself can
        be retrieved with a standard call to :func:`sys.exc_info`.

        If you want exception to propagate out of the :class:`Client` class
        you can define an ``on_error`` handler consisting of a single empty
        :ref:`py:raise`. Exceptions raised by ``on_error`` will not be
        handled in any way by :class:`Client`.
        """
        print(f'Ignoring exception in {event_method}', file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__)

    async def on_trade_receive(self, trade: 'steam.TradeOffer'):
        """|coro|
        Called when the client receives a trade offer from a user.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was received.
        """
        pass

    async def on_trade_send(self, trade: 'steam.TradeOffer'):
        """|coro|
        Called when the client or a user sends a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was sent.
        """
        pass

    async def on_trade_accept(self, trade: 'steam.TradeOffer'):
        """|coro|
        Called when the client or the trade partner accepts a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was accepted.
        """
        pass

    async def on_trade_decline(self, trade: 'steam.TradeOffer'):
        """|coro|
        Called when the client or the trade partner declines a trade offer.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was declined.
        """
        pass

    async def on_trade_cancel(self, trade: 'steam.TradeOffer'):
        """|coro|
        Called when the client or the trade partner cancels a trade offer.

        .. note::
            This is called when the trade state becomes
            :attr:`~steam.ETradeOfferState.Canceled` and
            :attr:`~steam.ETradeOfferState.CanceledBySecondaryFactor`.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that was cancelled.
        """
        pass

    async def on_trade_expire(self, trade: 'steam.TradeOffer'):
        """|coro|
        Called when a trade offer expires due to being active for too long.

        Parameters
        ----------
        trade: :class:`~steam.TradeOffer`
            The trade offer that expired.
        """
        pass

    async def on_trade_counter(self, before: 'steam.TradeOffer', after: 'steam.TradeOffer'):
        """|coro|
        Called when the client or the trade partner counters a trade offer.
        The trade in the after parameter will also be heard by either
        :func:`~steam.on_trade_receive()` or :func:`~steam.on_trade_send()`.

        Parameters
        ----------
        before: :class:`~steam.TradeOffer`
            The trade offer before it was countered.
        after: :class:`~steam.TradeOffer`
            The trade offer after it was countered.
        """
        pass

    async def on_comment(self, comment: 'steam.Comment'):
        """|coro|
        Called when the client receives a comment notification.

        Parameters
        ----------
        comment: :class:`~steam.Comment`
            The comment received.
        """
        pass

    async def on_invite(self, invite: 'steam.Invite'):
        """|coro|
        Called when the client receives an invite notification.

        Parameters
        ----------
        invite: :class:`~steam.Invite`
            The invite received.
        """
        pass

    async def on_listing_create(self, listing: 'steam.Listing'):
        """|coro|
        Called when a new listing is created on the community market.

        Parameters
        ----------
        listing: :class:`~steam.Listing`
            The listing that was created.
        """
        pass

    async def on_listing_buy(self, listing: 'steam.Listing'):
        """|coro|
        Called when an item/listing is bought on the community market.

        .. warning::
            This event isn't fully tested.

        Parameters
        ----------
        listing: :class:`~steam.Listing`
            The listing that was bought.
        """
        pass

    async def on_listing_sell(self, listing: 'steam.Listing'):
        """|coro|
        Called when an item/listing is sold on the community market.

        .. warning::
            This event isn't fully tested.

        Parameters
        ----------
        listing: :class:`~steam.Listing`
            The listing that was sold.
        """
        pass

    async def on_listing_cancel(self, listing: 'steam.Listing'):
        """|coro|
        Called when an item/listing is cancelled on the community market.

        .. warning::
            This event isn't fully tested.

        Parameters
        ----------
        listing: :class:`~steam.Listing`
            The listing that was cancelled.
        """
        pass
