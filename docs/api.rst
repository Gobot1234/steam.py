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

This page outlines the different types of events listened for by the :class:`Client`.

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

.. automethod:: Client.on_listing_sell
    :async:


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