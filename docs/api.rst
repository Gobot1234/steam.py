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

.. attributetable:: Client

.. autoclass:: Client
    :members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error,
                      on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment,
                      on_user_invite, on_user_invite_accept, on_user_invite_decline, on_user_update, on_user_remove,
                      on_clan_invite, on_clan_invite_accept, on_clan_invite_decline, on_clan_join, on_clan_update,
                      on_clan_leave,
                      on_group_join, on_group_update, on_group_leave,
                      on_event_create, on_announcement_create,
                      on_socket_receive, on_socket_send


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

.. automethod:: Client.on_user_invite_accept

.. automethod:: Client.on_user_invite_decline

.. automethod:: Client.on_user_remove

.. automethod:: Client.on_clan_invite

.. automethod:: Client.on_clan_invite_accept

.. automethod:: Client.on_clan_invite_decline

.. automethod:: Client.on_clan_join

.. automethod:: Client.on_clan_update

.. automethod:: Client.on_clan_leave

.. automethod:: Client.on_group_join

.. automethod:: Client.on_group_update

.. automethod:: Client.on_group_leave

.. automethod:: Client.on_event_create

.. automethod:: Client.on_announcement_create

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

    async for trade in client.trade_history():
        ...  # do stuff with trade here


.. autoclass:: steam.iterators.AsyncIterator()
    :members:


Abstract Base Classes
-----------------------

An :term:`abstract base class` (also known as an ``abc``) is a class that models can inherit their behaviour from.

.. attributetable:: steam.abc.BaseUser

.. autoclass:: steam.abc.BaseUser()
    :members:
    :inherited-members:

.. attributetable:: steam.abc.Channel

.. autoclass:: steam.abc.Channel()
    :members:
    :inherited-members:

.. attributetable:: steam.abc.Messageable

.. autoclass:: steam.abc.Messageable()
    :members:

Steam Models
---------------

steam.py provides wrappers around common Steam API objects.
These are not meant to be constructed by the user instead you receive them from methods/events.

Announcements
~~~~~~~~~~~~~~~

.. attributetable:: Announcement

.. autoclass:: Announcement
    :members:
    :inherited-members:


Badge
~~~~~~~~~~~~~~~

.. attributetable:: Badge

.. autoclass:: Badge()
    :members:

.. attributetable:: UserBadges

.. autoclass:: UserBadges()
    :members:

.. attributetable:: FavouriteBadge

.. autoclass:: FavouriteBadge()
    :members:

Ban
~~~~~~~~~~~~~~~

.. attributetable:: Ban

.. autoclass:: Ban()
    :members:

Channel
~~~~~~~~~~~~~~~

.. attributetable:: DMChannel

.. autoclass:: DMChannel()
    :members:
    :inherited-members:

.. attributetable:: GroupChannel

.. autoclass:: GroupChannel()
    :members:
    :inherited-members:

.. attributetable:: ClanChannel

.. autoclass:: ClanChannel()
    :members:
    :inherited-members:


Clan
~~~~~~~~~~~~~~~

.. attributetable:: Clan

.. autoclass:: Clan()
    :members:
    :inherited-members:


Comment
~~~~~~~~~~~~~~~

.. attributetable:: Comment

.. autoclass:: Comment()
    :members:


Events
~~~~~~~~~~~~~~~

.. attributetable:: Event

.. autoclass:: Event
    :members:
    :inherited-members:


Game Servers
~~~~~~~~~~~~~~~

.. attributetable:: GameServer

.. autoclass:: GameServer()
    :members:
    :inherited-members:

.. attributetable:: Query

.. autoclass:: Query()
    :members:


Group
~~~~~~~~~~~~~~~

.. attributetable:: Group

.. autoclass:: Group()
    :members:
    :inherited-members:

Invite
~~~~~~~~~~~~~~~

.. attributetable:: UserInvite

.. autoclass:: UserInvite()
    :members:
    :inherited-members:

.. attributetable:: ClanInvite

.. autoclass:: ClanInvite()
    :members:
    :inherited-members:

Message
~~~~~~~~~~~~~~~

.. attributetable:: Message

.. autoclass:: Message()
    :members:

.. attributetable:: UserMessage

.. autoclass:: UserMessage()
    :members:
    :inherited-members:

.. attributetable:: GroupMessage

.. autoclass:: GroupMessage()
    :members:
    :inherited-members:

.. attributetable:: ClanMessage

.. autoclass:: ClanMessage()
    :members:
    :inherited-members:

PriceOverview
~~~~~~~~~~~~~~~

.. attributetable:: PriceOverview

.. autoclass:: PriceOverview()
    :members:

Profile
~~~~~~~~~~~~~~~

.. attributetable:: ProfileInfo

.. autoclass:: ProfileInfo()
    :members:

.. attributetable:: ProfileItem

.. autoclass:: ProfileItem()
    :members:

.. attributetable:: OwnedProfileItems

.. autoclass:: OwnedProfileItems()
    :members:

.. attributetable:: EquippedProfileItems

.. autoclass:: EquippedProfileItems()
    :members:

.. attributetable:: Profile

.. autoclass:: Profile()
    :members:
    :inherited-members:


Trading
~~~~~~~~~~~~~~~

.. attributetable:: Inventory

.. autoclass:: Inventory()
    :members:
    :inherited-members:

.. attributetable:: Item

.. autoclass:: Item()
    :members:
    :inherited-members:

.. attributetable:: Asset

.. autoclass:: Asset()
    :members:

Reviews
~~~~~~~~~~~~~~~

.. attributetable:: Review

.. autoclass:: Review()

Roles
~~~~~~~~~~~~~~~

.. attributetable:: Role

.. autoclass:: Role()


Users
~~~~~~~~~~~~~~~

.. attributetable:: ClientUser

.. autoclass:: ClientUser()
    :members:
    :inherited-members:

.. attributetable:: User

.. autoclass:: User()
    :members:
    :inherited-members:


Data-Classes
---------------

There are a few classes that can be constructed by the user, these include.

Game
~~~~~~~~~~~~~~~

.. attributetable:: Game

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
| Left for Dead 2                 | ``steam.LFD2``  |
+---------------------------------+-----------------+
| Steam                           | ``steam.STEAM`` |
+---------------------------------+-----------------+

Games can be manually constructed using there app id eg:

.. code-block:: python3

    my_rust_instance = steam.Game(id=252490, title="Rust")
    # this can then be used for trading a game title is not required for this
    # but it is for setting in game statuses if the game isn't a Steam game.

.. autofunction:: CUSTOM_GAME

.. attributetable:: steam.game.StatefulGame

.. autoclass:: steam.game.StatefulGame()
    :inherited-members:
    :members:

.. attributetable:: UserGame

.. autoclass:: UserGame()
    :inherited-members:
    :members:

.. attributetable:: WishlistGame

.. autoclass:: WishlistGame()
    :inherited-members:
    :members:

.. attributetable:: FetchedGame

.. autoclass:: FetchedGame()
    :inherited-members:
    :members:


Steam IDs
~~~~~~~~~~~~~~~

.. attributetable:: SteamID

.. autoclass:: SteamID
    :members:

TradeOffers
~~~~~~~~~~~~~~~

.. attributetable:: TradeOffer

.. autoclass:: TradeOffer
    :members:


Images
~~~~~~~~~~~~~~~

.. attributetable:: Image

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
