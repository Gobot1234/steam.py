.. currentmodule:: steam.ext.commands

API Reference
===============

The following section outlines the API of steam.py's command extension module.


Bot
----

.. autoclass:: steam.ext.commands.Bot
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment, on_user_invite, on_user_invite_accept,
                      on_clan_invite, on_clan_invite_accept, on_user_update, on_socket_receive, on_socket_raw_receive,
                      on_socket_send, on_socket_raw_send,
                      on_command, on_command_error, on_command_completion


.. autofunction:: steam.ext.commands.when_mentioned

.. autofunction:: steam.ext.commands.when_mentioned_or


Event Reference
-----------------

These events function similar to `the regular events <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_,
except they are unique to the command extension module.

.. autofunction:: steam.ext.commands.Bot.on_command_error

.. autofunction:: steam.ext.commands.Bot.on_command

.. autofunction:: steam.ext.commands.Bot.on_command_completion


Enumerations
-------------

.. autoclass:: steam.ext.commands.BucketType
    :members:
    :undoc-members:


Command
--------

.. autofunction:: steam.ext.commands.command

.. autofunction:: steam.ext.commands.group

.. autofunction:: steam.ext.commands.command.cooldown

.. autoclass:: steam.ext.commands.Command
    :members:
    :special-members: __call__

.. autoclass:: steam.ext.commands.GroupCommand
    :members:
    :inherited-members:
    :special-members: __call__


Cogs
------

.. autoclass:: steam.ext.commands.Cog
    :members:


Context
--------

.. autoclass:: steam.ext.commands.Context
    :members:
    :inherited-members:


Converters
-----------

.. autoclass:: steam.ext.commands.Converter

.. autoclass:: steam.ext.commands.UserConverter

.. autoclass:: steam.ext.commands.ChannelConverter

.. autoclass:: steam.ext.commands.ClanConverter

.. autoclass:: steam.ext.commands.GroupConverter

.. autoclass:: steam.ext.commands.GameConverter


Default Values
---------------

.. autoclass:: steam.ext.commands.Default

.. autoclass:: steam.ext.commands.DefaultAuthor

.. autoclass:: steam.ext.commands.DefaultChannel

.. autoclass:: steam.ext.commands.DefaultClan

.. autoclass:: steam.ext.commands.DefaultGroup

.. autoclass:: steam.ext.commands.DefaultGame

Greedy
-------

.. autoclass:: steam.ext.commands.Greedy


Exceptions
-----------

.. autoexception:: steam.ext.commands.CommandError
    :members:

.. autoexception:: steam.ext.commands.BadArgument
    :members:

.. autoexception:: steam.ext.commands.MissingRequiredArgument
    :members:

.. autoexception:: steam.ext.commands.CheckFailure
    :members:

.. autoexception:: steam.ext.commands.NotOwner
    :members:

.. autoexception:: steam.ext.commands.CommandNotFound
    :members:

.. autoexception:: steam.ext.commands.CommandDisabled
    :members:

.. autoexception:: steam.ext.commands.CommandOnCooldown
    :members:


Exception Hierarchy
+++++++++++++++++++++

.. exception_hierarchy::

    - :exc:`~.SteamException`
        - :exc:`~.commands.CommandError`
            - :exc:`~.commands.BadArgument`
                - :exc:`~.commands.MissingRequiredArgument`
            - :exc:`~.commands.CommandNotFound`
            - :exc:`~.commands.CheckFailure`
                - :exc:`~.commands.CommandDisabled`
                - :exc:`~.commands.NotOwner`
            - :exc:`~.commands.CommandOnCooldown`
