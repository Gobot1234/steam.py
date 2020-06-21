.. currentmodule:: steam.ext.commands

API Reference
===============

The following section outlines the API of steam.py's command extension module.


Bot
----

.. autoclass:: steam.ext.commands.Bot
    :members:
    :inherited-members:


Event Reference
-----------------

These events function similar to `the regular events <https://steampy.rtfd.io/en/latest/api.html#event-reference>`_,
except they are custom to the command extension module.

.. autofunction:: Bot.on_command_error

.. autofunction:: Bot.on_command

.. autofunction:: Bot.on_command_completion


Command
--------

.. autofunction:: steam.ext.commands.command

.. autoclass:: steam.ext.commands.Command
    :members:
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


Exception Hierarchy
+++++++++++++++++++++

.. exception_hierarchy::

    - :exc:`~.SteamException`
        - :exc:`~.commands.CommandError`
            - :exc:`~.commands.MissingRequiredArgument`
            - :exc:`~.commands.BadArgument`
            - :exc:`~.commands.CommandNotFound`
            - :exc:`~.commands.CheckFailure`
