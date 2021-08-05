.. currentmodule:: steam

API reference
=============

The following document outlines the front facing aspects of steam.py.

.. note::
    This module uses Python's logging module to debug, give information and diagnose errors, it is recommended to
    configure this if necessary as errors or warnings will not be propagated properly.

Version Related Info
---------------------

.. data:: __version__

    A string representation of the version. e.g. ``'0.1.3'``. This is based off of :pep:`440`.

.. data:: version_info

    A :class:`typing.NamedTuple` similar to :obj:`sys.version_info` except without a serial field.

Client
------

.. autoclass:: Client
    :members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment, on_user_invite, on_user_invite_accept,
                      on_clan_invite, on_clan_invite_accept, on_user_update, on_socket_receive, on_socket_send


.. _event-reference:

Event Reference
---------------

This page outlines the different types of events listened for by the :class:`Client`.

There are two ways to register an event, the first way is through the use of :meth:`Client.event`. The second way is
through subclassing :class:`Client` and overriding the specific events. For example: ::

    import steam


    class MyClient(steam.Client):
        async def on_trade_receive(self, trade: steam.TradeOffer) -> None:
            await trade.partner.send('Thank you for your trade')
            print(f'Received trade: #{trade.id}')
            print('Trade partner is:', trade.partner)
            print('We would send:', len(trade.items_to_send), 'items')
            print('We would receive:', len(trade.items_to_receive), 'items')

            if trade.is_gift():
                print('Accepting the trade as it is a gift')
                await trade.accept()


If an event handler raises an exception, :meth:`Client.on_error` will be called to handle it, which by default prints a
traceback and ignoring the exception.

.. warning::
    All the events must be a :term:`coroutine function`. If they aren't, a :exc:`TypeError` will be raised.

.. automethod:: Client.on_connect

.. automethod:: Client.on_disconnect

.. automethod:: Client.on_ready

.. automethod:: Client.on_login

.. automethod:: Client.on_error

.. automethod:: Client.on_message

.. automethod:: Client.on_typing

.. automethod:: Client.on_trade_receive

.. automethod:: Client.on_trade_send

.. automethod:: Client.on_trade_accept

.. automethod:: Client.on_trade_decline

.. automethod:: Client.on_trade_cancel

.. automethod:: Client.on_trade_expire

.. automethod:: Client.on_trade_counter

.. automethod:: Client.on_comment

.. automethod:: Client.on_user_invite

.. automethod:: Client.on_clan_invite

.. automethod:: Client.on_user_update

.. automethod:: Client.on_socket_receive

.. automethod:: Client.on_socket_send


Utilities
----------

steam.py provides some utility functions.

.. autofunction:: steam.utils.make_id64

.. autofunction:: steam.utils.parse_trade_url

Then some functions from discord.py

.. autofunction:: steam.utils.get

.. autofunction:: steam.utils.find


Enumerations
-------------

.. autoclass:: Result()
    :members:
    :undoc-members:

.. autoclass:: Universe()
    :members:
    :undoc-members:

.. autoclass:: Type()
    :members:
    :undoc-members:

.. autoclass:: TypeChar()
    :members:
    :undoc-members:

.. autoclass:: InstanceFlag()
    :members:
    :undoc-members:

.. autoclass:: FriendRelationship()
    :members:
    :undoc-members:

.. autoclass:: PersonaState()
    :members:
    :undoc-members:

.. autoclass:: PersonaStateFlag()
    :members:
    :undoc-members:

.. autoclass:: CommunityVisibilityState()
    :members:
    :undoc-members:

.. autoclass:: TradeOfferState()
    :members:
    :undoc-members:

.. autoclass:: ChatEntryType()
    :members:
    :undoc-members:

.. autoclass:: UIMode()
    :members:
    :undoc-members:

.. autoclass:: UserBadge()
    :members:
    :undoc-members:

.. autoclass:: ReviewType()
    :members:
    :undoc-members:

.. autoclass:: GameServerRegion()
    :members:
    :undoc-members:


Guard
---------------

.. autofunction:: steam.guard.generate_one_time_code

.. autofunction:: steam.guard.generate_confirmation_code

.. autofunction:: steam.guard.generate_device_id


Async Iterators
-----------------

An async iterator is a class that is capable of being used with the syntax :ref:`async for <py:async for>`.

They can be used as follows:

.. code-block:: python3


.. autoclass:: steam.iterators.AsyncIterator()
    :members:


Abstract Base Classes
-----------------------

An :term:`abstract base class` (also known as an ``abc``) is a class that models can inherit their behaviour from.

.. autoclass:: steam.abc.BaseUser()
    :members:

.. autoclass:: steam.abc.Channel()
    :members:
    :inherited-members:

.. autoclass:: steam.abc.Messageable()
    :members:

Steam Models
---------------

steam.py provides wrappers around common Steam API objects.
These are not meant to be constructed by the user instead you receive them from methods/events.

Badge
~~~~~~~~~~~~~~~

.. autoclass:: Badge()
    :members:

.. autoclass:: UserBadges()
    :members:

Ban
~~~~~~~~~~~~~~~

.. autoclass:: Ban()
    :members:

Channel
~~~~~~~~~~~~~~~

.. autoclass:: DMChannel()
    :members:
    :inherited-members:

.. autoclass:: GroupChannel()
    :members:
    :inherited-members:

.. autoclass:: ClanChannel()
    :members:
    :inherited-members:


Clan
~~~~~~~~~~~~~~~

.. autoclass:: Clan()
    :members:
    :inherited-members:


Comment
~~~~~~~~~~~~~~~

.. autoclass:: Comment()
    :members:

Game Servers
~~~~~~~~~~~~~~~

.. autoclass:: GameServer()
    :members:
    :inherited-members:

.. autoclass:: Query()
    :members:


Group
~~~~~~~~~~~~~~~

.. autoclass:: Group()
    :members:

Invite
~~~~~~~~~~~~~~~

.. autoclass:: UserInvite()
    :members:
    :inherited-members:

.. autoclass:: ClanInvite()
    :members:
    :inherited-members:

Message
~~~~~~~~~~~~~~~

.. autoclass:: Message()
    :members:

.. autoclass:: UserMessage()
    :members:
    :inherited-members:

.. autoclass:: GroupMessage()
    :members:
    :inherited-members:

.. autoclass:: ClanMessage()
    :members:
    :inherited-members:

PriceOverview
~~~~~~~~~~~~~~~

.. autoclass:: PriceOverview()
    :members:

Trading
~~~~~~~~~~~~~~~

.. autoclass:: Inventory()
    :members:

.. autoclass:: Item()
    :members:
    :inherited-members:

.. autoclass:: Asset()
    :members:


Users
~~~~~~~~~~~~~~~

.. autoclass:: ClientUser()
    :members:
    :inherited-members:

.. autoclass:: User()
    :members:
    :inherited-members:


Data-Classes
---------------

There are a few classes that can be constructed by the user, these include.

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

Games can be manually constructed using there app id eg:

.. code-block:: python3

    my_rust_instance = steam.Game(id=252490, title="Rust")
    # this can then be used for trading a game title is not required for this
    # but it is for setting in game statuses if the game isn't a Steam game.

.. autofunction:: CUSTOM_GAME

.. autoclass:: UserGame()
    :inherited-members:
    :members:

.. autoclass:: WishlistGame()
    :inherited-members:
    :members:

.. autoclass:: FetchedGame()
    :inherited-members:
    :members:


Steam IDs
~~~~~~~~~~~~~~~

.. autoclass:: SteamID
    :members:

TradeOffers
~~~~~~~~~~~~~~~

.. autoclass:: TradeOffer
    :members:


Images
~~~~~~~~~~~~~~~

.. autoclass:: Image
    :members:

Exceptions
------------

The following exceptions are thrown by the library.

.. autoexception:: SteamException

.. autoexception:: ClientException

.. autoexception:: LoginError

.. autoexception:: InvalidCredentials

.. autoexception:: NoCMsFound

.. autoexception:: AuthenticatorError

.. autoexception:: ConfirmationError

.. autoexception:: HTTPException

.. autoexception:: Forbidden

.. autoexception:: NotFound

.. autoexception:: WSException

.. autoexception:: WSForbidden

.. autoexception:: WSNotFound

.. autoexception:: InvalidSteamID



Exception Hierarchy
~~~~~~~~~~~~~~~~~~~~~

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
            - :exc:`WSException`
                - :exc:`WSForbidden`
                - :exc:`WSNotFound`
            - :exc:`InvalidSteamID`
