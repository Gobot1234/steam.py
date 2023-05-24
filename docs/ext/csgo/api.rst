.. currentmodule:: steam.ext.csgo

API Reference
===============

The following section outlines the API of steam.py's CSGO extension module.


Client
------

.. attributetable:: Client

.. autoclass:: Client
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment, on_user_invite, on_user_invite_accept,
                      on_clan_invite, on_clan_invite_accept, on_user_update,
                      on_gc_connect, on_gc_disconnect, on_gc_ready, on_item_receive, on_item_remove, on_item_update

Event Reference
---------------

These events function similar to :ref:`the regular events <event-reference>`, and all of the events there are also
applicable to :class:`Client`. These are however unique to the CSGO extension module.

.. autofunction:: steam.ext.csgo.Client.on_gc_connect

.. autofunction:: steam.ext.csgo.Client.on_gc_disconnect

.. autofunction:: steam.ext.csgo.Client.on_gc_ready

.. autofunction:: steam.ext.csgo.Client.on_item_receive

.. autofunction:: steam.ext.csgo.Client.on_item_remove

.. autofunction:: steam.ext.csgo.Client.on_item_update

Bot
----

``ext.csgo`` also provides a :class:`Bot` class, which is a subclass of :class:`Client` and :class:`steam.ext.commands.Bot`.

.. attributetable:: steam.ext.csgo.Bot

.. autoclass:: steam.ext.csgo.Bot
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment, on_user_invite, on_user_invite_accept,
                      on_clan_invite, on_clan_invite_accept, on_user_update,
                      on_command, on_command_error, on_command_completion,
                      on_gc_connect, on_gc_disconnect, on_gc_ready, on_item_receive, on_item_remove, on_item_update

Utility Functions
------------------

.. autofunction:: steam.ext.csgo.utils.decode_sharecode

Enumerations
-------------
.. autoclass:: steam.ext.csgo.ItemQuality()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.ItemFlags()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.ItemOrigin()
    :members:
    :undoc-members:

Models
------
.. autoclass:: steam.ext.csgo.Backpack()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.Team()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.Round()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.Match()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.PartialUser()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.User()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.ClientUser()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.MatchPlayer()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.csgo.ProfileInfo()
    :members:
    :undoc-members:

