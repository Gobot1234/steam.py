.. currentmodule:: steam.ext.commands

API Reference
===============

The following section outlines the API of steam.py's command extension module.


Bot
----

.. autoclass:: steam.ext.commands.Bot
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_error,
                      on_message, on_typing, on_trade_receive, on_trade_send,
                      on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment, on_user_invite,
                      on_clan_invite, on_user_update, on_socket_receive,
                      on_socket_raw_receive, on_socket_send, on_socket_raw_send,
                      on_command, on_command_error, on_command_completion


Event Reference
-----------------

These events function similar to `the regular events <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_,
except they are unique to the command extension module.

.. autofunction:: steam.ext.commands.Bot.on_command_error

.. autofunction:: steam.ext.commands.Bot.on_command

.. autofunction:: steam.ext.commands.Bot.on_command_completion


Enums
--------

.. autoclass:: steam.ext.commands.BucketType


Command
--------

.. autofunction:: steam.ext.commands.command

.. autofunction:: steam.ext.commands.cooldown

.. autoclass:: steam.ext.commands.Command
    :members:
    :special-members: __call__


Cogs
------

.. autoclass:: steam.ext.commands.Cog
    :members:



Context
--------

.. autoclass:: steam.ext.commands.Context()
    :members:
    :inherited-members:


Exceptions
-----------

.. autoexception:: steam.ext.commands.CommandError
    :members:

.. autoexception:: steam.ext.commands.MissingRequiredArgument
    :members:

.. autoexception:: steam.ext.commands.BadArgument
    :members:

.. autoexception:: steam.ext.commands.CheckFailure
    :members:

.. autoexception:: steam.ext.commands.CommandNotFound
    :members:

.. autoexception:: steam.ext.commands.CommandOnCooldown
    :members:


Exception Hierarchy
+++++++++++++++++++++

.. exception_hierarchy::

    - :exc:`~.SteamException`
        - :exc:`~.commands.CommandError`
            - :exc:`~.commands.MissingRequiredArgument`
            - :exc:`~.commands.BadArgument`
            - :exc:`~.commands.CommandNotFound`
            - :exc:`~.commands.CheckFailure`
            - :exc:`~.commands.CommandOnCooldown`
