.. currentmodule:: steam.ext.commands

API Reference
===============

The following section outlines the API of steam.py's command extension module.


Bot
----

.. attributetable:: Bot

.. autoclass:: Bot
    :members:
    :inherited-members:
    :exclude-members: on_connect, on_disconnect, on_ready, on_login, on_logout, on_error, on_message, on_typing,
                      on_trade_receive, on_trade_send, on_trade_accept, on_trade_decline, on_trade_cancel,
                      on_trade_expire, on_trade_counter, on_comment, on_user_invite, on_user_invite_accept,
                      on_clan_invite, on_clan_invite_accept, on_user_update,
                      on_command, on_command_error, on_command_completion,

.. autofunction:: when_mentioned

.. autofunction:: when_mentioned_or


Event Reference
-----------------

These events function similar to :ref:`the regular events <event-reference>`, and all of the events there are also
applicable to :class:`Bot`. These are however unique to the commands extension module.

.. autofunction:: steam.ext.commands.Bot.on_command_error

.. autofunction:: steam.ext.commands.Bot.on_command

.. autofunction:: steam.ext.commands.Bot.on_command_completion


Enumerations
-------------

.. autoclass:: BucketType
    :members:
    :undoc-members:


Commands
--------

.. autodecorator:: command(name=None, cls=None, **attrs)

.. autodecorator:: group(name=None, cls=None, **attrs)

.. autodecorator:: check

.. autodecorator:: cooldown

.. autodecorator:: is_owner()

.. attributetable:: Command

.. autoclass:: Command
    :members:
    :special-members: __call__

.. attributetable:: Group

.. autoclass:: Group
    :members:
    :inherited-members:
    :special-members: __call__


Command Parsing
~~~~~~~~~~~~~~~

steam.py offers multiple ways to parse commands.

.. TODO type hinting section.

Positional or Keyword
+++++++++++++++++++++

- Values are passed to matching parameter based on their position.

Example:

.. code-block:: python


    @bot.command()
    async def command(ctx, argument_1, argument_2):
        ...

An invocation of ``!command some string`` would pass ``"some"`` to ``argument_1`` and ``"string"`` to ``argument_2``.

Variadic Positional
+++++++++++++++++++

- Values are passed as a :class:`tuple` of positional arguments that can be indefinitely long. This corresponds to an
  ``*args`` parameter in a function definition.

Example:

.. code-block:: python

    @bot.command()
    async def command(ctx, argument_1, *arguments):
        ...

An invocation of ``!command some longer string`` would pass ``"some"`` to ``argument_1`` and ``("longer", "string")``
to ``arguments``.

.. note::

    This has to be the last parameter in a function definition.


Keyword only
++++++++++++

- Any value is passed from the rest of the command to the first keyword only argument.

Example:

.. code-block:: python

    @bot.command()
    async def command(ctx, argument_1, *, argument_2):
        ...

An invocation of ``!command some longer string`` would pass ``"some"`` to ``argument_1`` and ``"longer string"`` to
``argument_2``.

.. note::

    This has to be the last parameter in a function definition.


Variadic Keyword
++++++++++++++++

- Values are passed as a :class:`dict` of keyword arguments that can be indefinitely long. This corresponds to a
  `**kwargs` parameter in a function definition.

Example:

.. code-block:: python

    @bot.command()
    async def command(ctx, argument_1, **arguments):
        ...

An invocation of ``!command some string=long`` would pass ``"some"`` to ``argument_1`` and ``{"string": "long"}`` to
``**arguments``.

.. note::

    This has to be the last parameter in a function definition.

.. warning::

    Type-hinting this function does not work like it strictly should, it should be done using ``**kwargs: value_type``
    whereas with steam.py it is ``**kwargs: dict[key_type, value_type]`` the rational behind this decision was to allow
    for non-string keys e.g. ``!ban user="reason to ban"``.


Help Commands
-------------

.. attributetable:: HelpCommand

.. autoclass:: HelpCommand
    :members:
    :inherited-members:
    :special-members: __call__

.. attributetable:: DefaultHelpCommand

.. autoclass:: DefaultHelpCommand
    :members:
    :inherited-members:
    :special-members: __call__


Cogs
------

.. attributetable:: Cog

.. autoclass:: Cog
    :members:


Context
--------

.. attributetable:: Context

.. autoclass:: Context
    :members:
    :inherited-members:


Cooldowns
----------

.. attributetable:: Cooldown

.. autoclass:: Cooldown
    :members:

Converters
-----------

.. autodecorator:: converter_for()

.. attributetable:: Converter

.. autoclass:: Converter()
    :members:
    :special-members: __class_getitem__

.. autoclass:: UserConverter()

.. autoclass:: ChannelConverter()

.. autoclass:: ClanConverter()

.. autoclass:: GroupConverter()

.. autoclass:: AppConverter()


Default Values
---------------

.. attributetable:: Default

.. autoclass:: Default()

.. autoclass:: DefaultAuthor()

.. autoclass:: DefaultChannel()

.. autoclass:: DefaultClan()

.. autoclass:: DefaultGroup()

.. autoclass:: DefaultApp()

Greedy
-------

.. attributetable:: Greedy

.. autoclass:: Greedy()
    :members:
    :special-members: __class_getitem__


Exceptions
-----------

.. autoexception:: CommandError
    :members:

.. autoexception:: BadArgument
    :members:

.. autoexception:: MissingRequiredArgument
    :members:

.. autoexception:: DuplicateKeywordArgument
    :members:

.. autoexception:: UnmatchedKeyValuePair
    :members:

.. autoexception:: CheckFailure
    :members:

.. autoexception:: NotOwner
    :members:

.. autoexception:: CommandNotFound
    :members:

.. autoexception:: CommandDisabled
    :members:

.. autoexception:: CommandOnCooldown
    :members:


Exception Hierarchy
~~~~~~~~~~~~~~~~~~~~~

.. exception_hierarchy::

    - :exc:`steam.SteamException`
        - :exc:`CommandError`
            - :exc:`BadArgument`
                - :exc:`MissingRequiredArgument`
                - :exc:`DuplicateKeywordArgument`
                - :exc:`UnmatchedKeyValuePair`
            - :exc:`CommandNotFound`
            - :exc:`CheckFailure`
                - :exc:`CommandDisabled`
                - :exc:`NotOwner`
            - :exc:`CommandOnCooldown`
