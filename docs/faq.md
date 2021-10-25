```{eval-rst}
.. currentmodule:: steam
```

% faq:

# F.A.Q

Find answers to some common questions relating to steam.py and help in the [discord server](https://discord.gg/MQ68WUS).

```{contents} Questions
:local: true
```

## General

These are some general questions relating to steam.py

### How much Python do I need to know?

This is not obviously required but it should make working with the library significantly simpler. Properly learning
Python will both prevent confusion and frustration when receiving help from others but will make it easier when reading
documentation and when debugging any issues in your code.

**A list of useful knowledge courtesy of Scragly:**

> % I like https://realpython.com for reading up on things as you can see

- Installing packages
- Primitive data types: `str`, `int`, `bool`, `dict`, `float`
- Basic operators: `+`, `-`, `/`, `*`, etc.
- Data structures `list`, `tuple`, `dict`, `set`
- Importing
- Variables, namespace and scope
- [Control flow](https://realpython.com/python-conditional-statements):
    - `while`
    - `if`
    - `elif`
    - `else`
    - `for`
- [Exception handling](https://realpython.com/python-exceptions):
    - `try`
    - `except`
    - `else`
    - `finally`
- [Function definitions](https://realpython.com/defining-your-own-python-function)
- [Argument definitions](https://realpython.com/python-kwargs-and-args):
    - Argument ordering
    - Default arguments
    - Variable length arguments
- [Classes, objects, attributes and methods](https://realpython.com/python3-object-oriented-programming)
- [Console usage, interpreters and environments](https://realpython.com/python-virtual-environments-a-primer)
- [Asyncio basics](https://realpython.com/async-io-python):
    - `await`
    - `async def`
    - `async with`
    - `async for`
    - [What is blocking?](https://discordpy.rtfs.io/en/latest/faq.html#what-does-blocking-mean)
- String formatting:
    - [str.format()](https://pyformat.info)
    - [f-strings](https://realpython.com/python-f-strings) A.K.A. formatted string literals
    - Implicit/explicit string concatenation
- [Logging](https://realpython.com/courses/logging-python)
- [Decorators](https://realpython.com/primer-on-python-decorators)
- [Basic type hints](https://realpython.com/python-type-checking)

**Places to learn more python**

- https://docs.python.org/3/tutorial/index.html (official tutorial)
- https://greenteapress.com/wp/think-python-2e (for beginners to programming or python)
- https://www.codeabbey.com (exercises for beginners)
- https://www.real-python.com (good for individual quick topics)
- https://gto76.github.io/python-cheatsheet (cheat sheet)

### How can I get help with my code?

**Bad practices:**

- Truncate the traceback as you might remove important parts from it. If it isn't sommething that should be kept private
  like your username, password etc. include it.
- Send screenshots/text files of code/errors unless relevant as they can be difficult to read.
- Uploading a text file. Instead, you could use any of:
    - https://mystb.in
    - https://gist.github.com
    - https://hastebin.com
- Ask if you can ask a question about the library as the answer will always be yes.
- Saying "This code doesn't work" or "What's wrong with this code?"
    - This is not helpful for yourself or others. Describe what you expected to happen and/or tried (with your code),
      and what isn't going right. Along with a traceback (if applicable).
  
### How can I wait for an event?

```python3
import asyncio

import steam
from steam.ext import commands


bot = commands.Bot(command_prefix="!")

@bot.command
async def trade(ctx: commands.Context):
    def check(trade: steam.TradeOffer) -> bool:
        return trade.partner == ctx.author

    await ctx.send("Send me a trade!")
    try:
        offer = await bot.wait_for("trade_receive", timeout=60, check=check)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to send the offer")
    else:
        await ctx.send(
            f"You were going to send {len(offer.items_to_receive)} items\n"
            f"You were going to receive {len(offer.items_to_send)} items"
        )
        await offer.decline()
```

The final interaction will end up looking something like this:

- ?trade
- Send me a trade!
- User sent a new trade offer
- You were going to send 3 items. You were going to receive 5 items

### How do I send a trade?

Sending a trade should be pretty simple.

- You need to first get the inventories of the User's involved.
- Then you need to find the items to trade for.
- Construct the TradeOffer from its items.
- Finally use the {meth}`~steam.User.send` method on the User that you want to send the offer to.

```python3
# we need to chose a game to fetch the inventory for
game = steam.TF2
# we need to get the inventories to get items
my_inventory = await client.user.inventory(game)
their_inventory = await user.inventory(game)

# we need to get the items to be included in the trade
keys = my_inventory.filter_items("Mann Co. Supply Crate Key", limit=3)
earbuds = their_inventory.get_item("Earbuds")

# finally construct the trade
trade = TradeOffer(items_to_send=keys, item_to_receive=earbuds, message="This trade was made using steam.py")
await user.send(trade=trade)
# you don't need to confirm the trade manually, the client will handle that for you
```

### What is the difference between fetch and get?

- **GET**
  : This retrieves an object from the client's cache. If it happened recently, it will be cached. So this method is best
    in this case. This is also the faster of the two methods as it is a dictionary lookup.
- **FETCH**
  : This retrieves an object from the API, it is also a [coroutine_link] because of this. This is good in case
    something needs to be updated, due to the cache being stale or the object not being in cache at all. These, however,
    should be used less frequently as they are a request to the API and are generally slower to return values. Fetched
    values aren't added to cache.
