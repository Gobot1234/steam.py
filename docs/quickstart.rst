Quickstart
==========

A quick start guide for steam.py

.. _installing:

Installation
------------

Installation should be as simple as:

.. code-block:: sh

    # Linux/macOS
    python3 -m pip install -U steamio
    # Windows
    py -m pip install -U steamio

The Basics
----------

steam.py being heavily inspired by and based on discord.py revolves around :ref:`events <event-reference>`. An event is
something you listen for and then respond to.

For example, when a trade happens, you will receive an event about it that you can respond to.

A quick example to showcase how events work:

.. code-block:: py

    import steam

    class MyClient(steam.Client):
        async def on_ready(self) -> None:
            print("Logged in as", self.user)

        async def on_trade_receive(self, trade: steam.TradeOffer) -> None:
            print(f"Received trade: #{trade.id} from", trade.partner)

    client = MyClient()
    client.run("username", "password")

A Minimal Bot
-------------
Let’s make a bot that replies to a specific message and walk you through it.

It looks something like this:

.. code-block:: py

    import steam

    class MyClient(steam.Client):
        async def on_ready() -> None:
            print(f"We have logged in as {self.user}")

        async def on_message(self, message: steam.Message) -> None:
            if message.author == self.user:
                return

            if message.content.startswith("$hello"):
                await message.channel.send("Hello!")

    client = MyClient()
    client.run("username", "password")


Lets walk through what this does:

    1. We import the steam module, if this raises a :exc:`ModuleNotFoundError` see :ref:`installing` again.
    2. We then subclass :class:`steam.Client` to create our own client ``MyClient``.
    3. We register an event :meth:`steam.Client.on_ready` in ``MyClient``, which will be called after the client is
       ready. This event will print once we log in to inform us as such.
    4. We then register another event :meth:`steam.Client.on_message`, when doing so we need to be careful to check the
       :class:`steam.Message.author` as steam.py fires an event for every message sent. After this we can check the
       :class:`steam.Message.content` to see if the message startswith the correct phrase of "$hello" to send back our
       reply of "Hello!".
    5. Finally we instantiate ``MyClient`` and use :meth:`steam.Client.run` it with our steam username and password.

After saving this as ``example_bot.py`` not called ``steam.py`` as it will interfere with the library we can run the bot
and watch it come online using:

.. code-block:: sh

    # Linux/macOS
    python3 example_bot.py
    # Windows
    py -3 example_bot.py


A Minimal Bot with ext.commands
-------------------------------

Since code like this is so common steam.py comes with a powerful commands extension to aid with creating commands.

.. code-block:: py

    from steam.ext import commands


    class MyBot(commands.Bot):
        async def on_ready() -> None:
            print(f"We have logged in as {self.user}")

        @commands.command
        async def hello(self, ctx: commands.Context) -> None:
            await ctx.send("Hello!")

    bot = MyBot(command_prefix="$")
    bot.run("username", "password")

This will perform the same as the example using :meth:`steam.Client.on_message`.

Except with some key differences:

    1. We import steam.ext.commands to handle commands.
    2. We subclass :class:`steam.ext.commands.Bot` to inherit command parsing functionality.
    3. We swap out the ``if message.content.startswith("$hello"):`` line for a command that is registered with the
       command's name using the :func:`steam.ext.commands.command`.
    4. Inside the ``hello`` command we are able to access the context of the invocation using the ``ctx`` parameter.
       This allows us to use the :meth:`steam.ext.commands.Context.send` to send the same response.
    5. When instantiating the bot we pass the ``command_prefix`` key-word argument to make the bot only respond when the
       message's content starts with the prefix "$".
