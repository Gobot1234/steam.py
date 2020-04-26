.. currentmodule:: steam

API reference
=============

The following document outlines the front facing aspects of steam.py.

.. note::
    This module uses Python's logging module to debug, give information and
    diagnose errors, it is recommended to configure this if necessary as errors or warnings
    will not be propagated properly.

Version Related Info
---------------------

.. data:: __version__

    A string representation of the version. e.g. ``'0.0.8a'``. This is based
    off of :pep:`440`.

Client
---------------

.. autoclass:: Client
    :members:

Event Reference
---------------

This page outlines the different types of events listened by :class:`Client`.

There are two ways to register an event, the first way is through the use of
:meth:`Client.event`. The second way is through subclassing :class:`Client` and
overriding the specific events. For example: ::

    import steam


    class MyClient(steam.Client):
        async def on_trade_receive(self, trade: steam.TradeOffer):
            print(f'Received trade: #{trade.id}')
            print('Trade partner is:', trade.partner.name)
            print('We are going to send:')
            print('\n'.join([item.name if item.name else str(item.asset_id) for item in trade.items_to_send])
                  if trade.items_to_send else 'Nothing')
            print('We are going to receive:')
            print('\n'.join([item.name if item.name else str(item.asset_id) for item in trade.items_to_receive])
                  if trade.items_to_receive else 'Nothing')

            if trade.is_gift():
                print('Accepting the trade as it is a gift')
                await trade.accept()


If an event handler raises an exception, :func:`on_error` will be called
to handle it, which defaults to print a traceback and ignoring the exception.

.. warning::

    All the events must be a |coroutine_link|_. If they aren't, then you might get unexpected
    errors. In order to turn a function into a coroutine they must be ``async def``
    functions.

.. function:: on_connect()

    Called when the client has successfully connected to Steam. This is not
    the same as the client being fully prepared, see :func:`on_ready` for that.

    The warnings on :func:`on_ready` also apply.

.. function:: on_disconnect()

    Called when the client has disconnected from Steam. This could happen either through
    the internet disconnecting, an explicit call to logout, or Steam terminating the connection.

    This function can be called multiple times.

.. function:: on_ready()

    Called after a successful login and the client has handled setting up trade and notification polling,
    along with setup the confirmation manager.

    .. note::
        In future this will be called when the client is done preparing the data received from Steam.
        Usually after login to a CM is successful.

    .. warning::

        This function is not guaranteed to be the first event called.
        Likewise, this function is **not** guaranteed to only be called
        once. This library implements reconnection logic and will therefore
        end up calling this event whenever a RESUME request fails.

.. function:: on_login()

    Called when the client has logged into https://steamcommunity.com and
    the :class:`~steam.ClientUser` is setup along with its friends list.

.. function:: on_error(event, \*args, \*\*kwargs)

    Usually when an event raises an uncaught exception, a traceback is
    printed to stderr and the exception is ignored. If you want to
    change this behaviour and handle the exception for whatever reason
    yourself, this event can be overridden. Which, when done, will
    suppress the default action of printing the traceback.

    The information of the exception raised and the exception itself can
    be retrieved with a standard call to :func:`sys.exc_info`.

    If you want exception to propagate out of the :class:`Client` class
    you can define an ``on_error`` handler consisting of a single empty
    :ref:`py:raise`.  Exceptions raised by ``on_error`` will not be
    handled in any way by :class:`Client`.

    :param event: The name of the event that raised the exception.
    :type event: :class:`str`

    :param args: The positional arguments for the event that raised the
        exception.
    :param kwargs: The keyword arguments for the event that raised the
        exception.

.. function:: on_trade_receive(trade)

    Called when the client receives a trade offer from a user.
    
    :param trade: The trade offer that was received.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_send(trade)

    Called when the client or a user sends a trade offer.
    
    :param trade: The trade offer that was sent.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_accept(trade)

    Called when the client or the trade partner accepts a trade offer.
    
    :param trade: The trade offer that was accepted.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_decline(trade)

    Called when the client or the trade partner declines a trade offer.
    
    :param trade: The trade offer that was declined.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_cancel(trade)

    Called when the client or the trade partner cancels a trade offer.

    .. note::
        This is called when the trade state becomes
        :attr:`~steam.ETradeOfferState.Canceled` and
        :attr:`~steam.ETradeOfferState.CanceledBySecondaryFactor`.
    
    :param trade: The trade offer that was canceled.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_expire(trade)

    Called when a trade offer expires due to being active for too long.

    :param trade: The trade offer that expired.
    :type trade: :class:`~steam.TradeOffer`


.. function:: on_trade_counter(before, after)

    Called when the client or the trade partner counters a trade offer.
    The trade in the after parameter will also be heard by either
    :func:`~steam.on_trade_receive()` or :func:`~steam.on_trade_send()`.

    :param before: The trade offer before it was countered.
    :type before: :class:`~steam.TradeOffer`
    :param after: The trade offer after it was countered.
    :type after: :class:`~steam.TradeOffer`

.. function:: on_comment(comment)

    Called when the client receives a comment notification.

    :param comment: The comment received.
    :type comment: :class:`~steam.Comment`

.. function:: on_invite(invite)

    Called when the client receives an invite notification.

    :param invite: The invite received.
    :type invite: :class:`~steam.Invite`

.. function:: on_listing_create(listing)

    Called when a new listing is created on the community market.

    :param listing: The listing that was created.
    :type listing: :class:`~steam.Listing`

.. function:: on_listing_buy(listing)

    Called when an item/listing is bought on the community market.

    .. warning::
        This event isn't fully tested.

    :param listing: The listing that was bought.
    :type listing: :class:`~steam.Listing`


.. function:: on_listing_sell(listing)

    Called when an item/listing is sold on the community market.

    .. warning::
        This event isn't fully tested.

    :param listing: The listing that sold.
    :type listing: :class:`~steam.Listing`


.. function:: on_listing_cancel(listing)

    Called when an item/listing is cancelled on the community market.

    .. warning::
        This event isn't fully tested.

    :param listing: The listing that sold.
    :type listing: :class:`~steam.Listing`


Utilities
----------

steam.py provides some utility functions for Steam related problems.

.. autofunction:: steam.utils.parse_trade_url_token

Then some functions from discord.py

.. autofunction:: steam.utils.get

.. code-block:: python3

    bff = steam.utils.get(client.users, name="Gobot1234")
    trade = steam.utils.get(client.trades, state=ETradeOfferState.Active, partner=ctx.author)
    # multiple attributes are also accepted

.. autofunction:: steam.utils.find

.. code-block:: python3

    active = steam.utils.find(lambda trade: trade.state == ETradeOfferState.Active, client.trades)
    # how to get an object using condition

Enumerations
-------------

.. autoclass:: EResult
    :members:
    :undoc-members:

.. autoclass:: EType
    :members:
    :undoc-members:

.. autoclass:: EPersonaState
    :members:
    :undoc-members:

.. autoclass:: ECurrencyCode
    :members:
    :undoc-members:

.. autoclass:: ETradeOfferState
    :members:
    :undoc-members:

.. autoclass:: EMarketListingState
    :members:
    :undoc-members:

.. autoclass:: EPersonaStateFlag
    :members:
    :undoc-members:

.. TODO make these individually

Guard
---------------

.. autofunction:: steam.guard.generate_one_time_code(shared_secret, timestamp=time.time())

.. autofunction:: steam.guard.generate_confirmation_code(identity_secret, tag, timestamp=time.time())

.. autofunction:: steam.guard.generate_device_id


Abstract Base Classes
-----------------------

An :term:`py:abstract base class` (also known as an ``abc``) is a class that models can inherit their behaviour from.
They are only used for subclassing.

.. autoclass:: steam.abc.BaseUser()
    :members:

.. autoclass:: steam.abc.Messageable()
    :members:

Steam Models
---------------

steam.py provides wrappers around common Steam API objects.

Badges
~~~~~~~~~~~~~~~

.. autoclass:: Badge()
    :members:

Bans
~~~~~~~~~~~~~~~

.. autoclass:: Ban()
    :members:

Comments
~~~~~~~~~~~~~~~

.. autoclass:: Comment()
    :members:

Game
~~~~~~~~~~~~~~~

.. autoclass:: Game(app_id, title=None, *, is_steam_game=True, context_id=2)
    :members:

There are some predefined games which are:

+---------------------------------+-----------------+
| Game Title                      | Accessed via    |
+=================================+=================+
| Team Fortress 2                 | ``steam.TF2``   |
+---------------------------------+-----------------+
| DOTA2                           | ``steam.DOTA2`` |
+---------------------------------+-----------------+
| Counter Strike Global-Offensive | ``steam.CSGO``  |
+---------------------------------+-----------------+
| Steam                           | ``steam.STEAM`` |
+---------------------------------+-----------------+

Games can be manually constructed using there app id eg:

.. code-block:: python3

    my_rust_instance = steam.Game(252490, 'Rust')
    # this can then be used for trading
    # a game title is not required for this

Groups
~~~~~~~~~~~~~~~

.. autoclass:: Group()
    :members:

Invites
~~~~~~~~~~~~~~~

.. autoclass:: Invite()
    :members:

Market
~~~~~~~~~~~~~~~

.. autoclass:: Listing()
    :members:
    :inherited-members:

.. autoclass:: PriceOverview()
    :members:

Message
~~~~~~~~~~~~~~~

This is currently under development and does **not** currently function.

.. autoclass:: Message()
    :members:

Trading
~~~~~~~~~~~~~~~

.. autoclass:: TradeOffer()
    :members:

.. autoclass:: Inventory()
    :members:

.. autoclass:: Item()
    :members:
    :inherited-members:

.. autoclass:: Asset()
    :members:

Steam IDs
~~~~~~~~~~~~~~~

.. autoclass:: SteamID
    :members:

Users
~~~~~~~~~~~~~~~

.. autofunction:: make_steam64

.. autoclass:: ClientUser()
    :members:
    :inherited-members:

.. autoclass:: User()
    :members:
    :inherited-members:

.. autoclass:: UserBadges()
    :members:

Exceptions
------------

The following exceptions are thrown by the library.

.. autoexception:: SteamException

.. autoexception:: ClientException

.. autoexception:: HTTPException

.. autoexception:: LoginError

.. autoexception:: InvalidCredentials

.. autoexception:: NoCMsFound

.. autoexception:: AuthenticatorError

.. autoexception:: ConfirmationError

.. autoexception:: Forbidden

.. autoexception:: NotFound


Exception Hierarchy
~~~~~~~~~~~~~~~~~~~~~

.. totally not from discord.py https://github.com/Rapptz/discord.py/blob/master/docs/extensions/exception_hierarchy.py

.. exception_hierarchy::

    - :exc:`Exception`
        - :exc:`SteamException`
            - :exc:`ClientException`
                - :exc:`AuthenticatorError`
                    - :exc:`ConfirmationError`
                - :exc:`LoginError`
                    - :exc:`InvalidCredentials`
                    - :exc:`NoCMsFound`
            - :exc:`HTTPException`
                - :exc:`Forbidden`
                - :exc:`NotFound`