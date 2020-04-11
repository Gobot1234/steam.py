.. currentmodule:: steam
.. _faq:

F.A.Q
======

Find answers to some common questions relating to steam.py and help in the discord server

.. contents:: Questions
    :local:


How much Python should I need to know?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**A list of required knowledge courtesy of Scragly:**

    .. I like https://realpython.com for reading up on things as you can see

    - pip installing packages
    - Primitive data types: ``str``, ``int``, ``float``, ``bool``
    - Operators: ``+``, ``-``, ``/``, ``*``, etc.
    - Data structures ``list``, ``tuple``, ``dict``, ``set``
    - Importing
    - Variables, namespace and scope
    - `Control flow <https://realpython.com/python-conditional-statements/>`_
        - ``while``
        - ``if``
        - ``elif``
        - ``else``
        - ``for``
    - `Exception handling <https://realpython.com/python-exceptions/>`_
        - ``try``
        - ``except``
        - ``else``
        - ``finally``
    - `Function definitions <https://realpython.com/defining-your-own-python-function/>`_
    - `Argument definitions <https://realpython.com/python-kwargs-and-args/>`_
        - Argument ordering
        - Default arguments
        - Variable length arguments
    - `Classes, objects, attributes and methods <https://realpython.com/python3-object-oriented-programming/>`_
    - `Console usage, interpreters and environments <https://realpython.com/python-virtual-environments-a-primer/>`_
    - `Asyncio basics <https://realpython.com/async-io-python/>`_
        - ``await``
        - ``async def``
        - ``async with``
        - ``async for``
        - `What is blocking? <https://discordpy.rtfs.io/en/latest/faq.html#what-does-blocking-mean>`_
    - String formatting
        - `str.format() <https://pyformat.info/>`_
        - `f-strings <https://realpython.com/python-f-strings/>`_ A.K.A. formatted string literals
        - Implicit/explicit string concatenation
    - `Logging <https://realpython.com/courses/logging-python/>`_
    - `Decorators <https://realpython.com/primer-on-python-decorators/>`_

You should have knowledge over all of the above this is due to the to the semi-complex nature of the library along
with asynchronous programming, it can be rather overwhelming for a beginner. Properly learning python will both
prevent confusion and frustration when receiving help from others but will make it easier when reading documentation
and when debugging any issues in your code.

**Places to learn more python**

- https://docs.python.org/3/tutorial/index.html (official tutorial)
- https://greenteapress.com/wp/think-python-2e/ for beginners to programming or to python
- https://www.codeabbey.com/ (exercises for beginners)
- https://www.real-python.com/ (good for individual quick tutorials)
- https://gto76.github.io/python-cheatsheet/ (cheat sheet)


How can I get help with my code?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**What not to do:**

- Truncate the traceback.
    - As you might remove important parts from it.
- Send screenshots/text files of code/errors unless relevant.
    - As they are difficult to read.
- Use https://pastebin.com,
    - As it is very bloated and ad heavy.
    - Instead you could use of:
        - https://hastebin.com/
        - https://mystb.in/
        - https://gist.github.com/
        - https://starb.in/
- Ask if you can ask a question about the library.
    - The answer will always be yes.
- Saying This code doesn't work or What's wrong with this code? Without any traceback.
    - This not helpful for yourself or others. Describe what you expected to happen and/or tried (with your code),
      and what isn't going right. Along with a traceback.

**Encouraged practices:**

- Try searching for something using the documentation or ``=rtfm`` in an appropriate channel.
- Trying something for yourself.

    .. raw:: html

        <video width="320" height="240" controls>
            <source src="https://tryitands.ee/tias.mp4" type="video/mp4">
        Your browser does not support the video :(
        </video>


How can I wait for an event?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python3

    @client.event
    async def on_message(message):
        if message.content.startswith('?trade'):
            await message.send('Send me a trade')

            def check(trade):
                return trade.partner == message.author

            try:
                trade = await client.wait_for('trade_receive', timeout=60, check=check)
            except asyncio.TimeoutError:
                await channel.send('You took too long')
            else:
                to_send = ', '.join([item.name if item.name else str(item.asset_id) for item in trade.items_to_send]) \
                    if trade.items_to_send else 'Nothing'
                to_receive = ', '.join([item.name if item.name else str(item.asset_id) for item in trade.items_to_receive]) \
                    if trade.items_to_receive else 'Nothing'
                await message.send(f'You were going to send:\n{to_receive}\nYou were going to receive:\n{to_send}')
                await trade.decline()
