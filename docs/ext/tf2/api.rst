.. currentmodule:: steam.ext.tf2

API Reference
===============

The following section outlines the API of steam.py's TF2 extension module.


Client
------


.. autoclass:: Client
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade, on_trade_update, on_comment, on_invite, on_invite_accept, on_invite_decline,
                      on_user_update,
                      on_gc_connect, on_gc_disconnect, on_gc_ready, on_item_receive, on_item_remove, on_item_update,
                      on_account_update

Event Reference
---------------

These events function similar to :ref:`the regular events <event-reference>`, and all of the events there are also
applicable to :class:`Client`. These are however unique to the TF2 extension module.

.. autofunction:: steam.ext.tf2.Client.on_gc_connect

.. autofunction:: steam.ext.tf2.Client.on_gc_disconnect

.. autofunction:: steam.ext.tf2.Client.on_gc_ready

.. autofunction:: steam.ext.tf2.Client.on_account_update

.. autofunction:: steam.ext.tf2.Client.on_item_receive

.. autofunction:: steam.ext.tf2.Client.on_item_remove

.. autofunction:: steam.ext.tf2.Client.on_item_update

Bot
----

``ext.tf2`` also provides a :class:`Bot` class, which is a subclass of :class:`Client` and :class:`steam.ext.commands.Bot`.


.. autoclass:: steam.ext.tf2.Bot
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade, on_trade_update, on_comment, on_invite, on_invite_accept, on_invite_decline,
                      on_user_update,
                      on_command, on_command_error, on_command_completion,
                      on_gc_connect, on_gc_disconnect, on_gc_ready, on_item_receive, on_item_remove, on_item_update
                      on_account_update

Enumerations
-------------
.. autoclass:: steam.ext.tf2.ItemQuality()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.ItemFlags()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.ItemOrigin()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.Mercenary()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.ItemSlot()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.WearLevel()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.BackpackSortType()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.Part()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.Spell()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.Sheen()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.Killstreak()
    :members:
    :undoc-members:

.. autoclass:: steam.ext.tf2.Attribute()
    :members:
    :undoc-members:


Models
------
.. autoclass:: steam.ext.tf2.Backpack()
    :members:
    :undoc-members:


Currency
--------
As working with refined is so common in TF2, ``ext.tf2`` provides a :class:`Metal` class to make working with it easier.

.. autoclass:: steam.ext.tf2.Metal()
    :members:
    :undoc-members: