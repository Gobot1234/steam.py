.. currentmodule:: steam

API reference
=============

Version Related Info
---------------------

.. data:: __version__

    A string representation of the version. e.g. ``'0.0.8a'``. This is based
    off of :pep:`440`.


Client
-------------------

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
        async def on_trade_receive(self, trade):
            print(f'Received trade: #{trade.id}')
            print('From user:', trade.partner.name, 'Is one-sided:', trade.is_one_sided())
            print('We are sending:')
            print('\n'.join([item.name if item.name else item.asset_id for item in trade.items_to_give])
                  if trade.items_to_give else 'Nothing')
            print('We are receiving:')
            print('\n'.join([item.name if item.name else item.asset_id for item in trade.items_to_receive])
                  if trade.items_to_receive else 'Nothing')


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

    This function can be called many times.

.. function:: on_ready()

    Called when the client is done preparing the data received from Steam. Usually after login is successful.

    .. warning::

        This function is not guaranteed to be the first event called.
        Likewise, this function is **not** guaranteed to only be called
        once. This library implements reconnection logic and will therefore
        end up calling this event whenever a RESUME request fails.

.. function:: on_login()

    Called when the client has logged into https://steamcommunity.com.

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

    Called when the client receives a trade offer.
    
    :param trade: The trade offer that was received.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_send(trade)

    Called when the client sends a trade offer
    
    :param trade: The trade offer that was sent.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_accept(trade)

    Called when the client accepts a trade offer
    
    :param trade: The trade offer that was accepted.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_decline(trade)

    Called when the client declines a trade offer
    
    :param trade: The trade offer that was declined.
    :type trade: :class:`~steam.TradeOffer`

.. function:: on_trade_cancel(trade)

    Called when the client cancels a trade offer
    
    :param trade: The trade offer that was canceled.
    :type trade: :class:`~steam.TradeOffer`

   
Enumerations
-------------

.. autoclass:: EResult
    :members:
    :undoc-members:

.. autoclass:: EType
    :members:

.. autoclass:: EPersonaState
    :members:
    :undoc-members:

.. autoclass:: ECurrencyCode
    :members:
    :undoc-members:

.. autoclass:: ETradeOfferState
    :members:
    :undoc-members:

Guard
------------------

.. autofunction:: steam.guard.generate_one_time_code(shared_secret: str, timestamp: int = time.time())

.. autofunction:: steam.guard.generate_confirmation_key(identity_secret: str, tag: str, timestamp: int = time.time())

.. autofunction:: steam.guard.generate_device_id

Market
-------------------

.. autoclass:: steam.market.Market()
    :members:

.. autoclass:: PriceOverview()
    :members:

Abstract Base Classes
-----------------------

An :term:`py:abstract base class` (also known as an ``abc``) is a class that models can inherit their behaviour from.
They are only used for subclassing.

.. autoclass:: steam.abc.BaseUser
    :members:

.. autoclass:: steam.abc.Messageable
    :members:

Steam Models
---------------

Game
~~~~~~~~~~~~~~~

.. autoclass:: Game
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

Comments
~~~~~~~~~~~~~~~

.. autoclass:: Comment()
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

Exceptions
------------

The following exceptions are thrown by the library.

.. autoexception:: SteamException

.. autoexception:: ClientException

.. autoexception:: HTTPException

.. autoexception:: LoginError

.. autoexception:: InvalidCredentials

.. autoexception:: SteamAuthenticatorError

.. autoexception:: ConfirmationError

.. autoexception:: Forbidden

.. autoexception:: NotFound
