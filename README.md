# steam.py

A modern, easy to use, and async ready package to interact with the Steam API. Heavily inspired by
[discord.py](https://github.com/Rapptz/discord.py) and borrowing functionality from
[ValvePython/steam](https://github.com/ValvePython/steam).

![Supports](https://img.shields.io/pypi/pyversions/steamio)
![Version](https://img.shields.io/pypi/v/steamio?color=%2366c0f4)
![License](https://img.shields.io/github/license/Gobot1234/steam.py)
[![GitHub issues](https://img.shields.io/github/issues-raw/Gobot1234/steam.py)](https://github.com/Gobot1234/steam.py/issues)
[![GitHub stars](https://img.shields.io/github/stars/Gobot1234/steam.py)](https://github.com/Gobot1234/steam.py/stargazers)
[![Discord](https://img.shields.io/discord/678629505094647819?color=7289da&label=Discord&logo=discord)](https://discord.gg/MQ68WUS)
[![Documentation Status](https://github.com/Gobot1234/steam.py/actions/workflows/docs.yml/badge.svg)](https://github.com/Gobot1234/steam.py/actions/workflows/docs.yml)


## Key Features

- Modern Pythonic API using `async`/`await` syntax
- Command extension to aid with bot creation
- Easy to use with an object-oriented design
- Fully typed hinted for faster development

## Installation

**Python 3.7 or higher is required**

To install the library just run either of the following commands:

```sh
# Linux/macOS
python3 -m pip install -U steamio
# Windows
py -m pip install -U steamio
```

Or for the development version.

```sh
# Linux/macOS
python3 -m pip install -U "steamio @ git+https://github.com/Gobot1234/steam.py@main"
# Windows
py -m pip install -U "steamio @ git+https://github.com/Gobot1234/steam.py@main"
```

## Quick Example

```py
import steam


class MyClient(steam.Client):
    async def on_ready(self) -> None:
        print("Logged in as", self.user)

    async def on_trade_receive(self, trade: steam.TradeOffer) -> None:
        await trade.partner.send("Thank you for your trade")
        print(f"Received trade: #{trade.id}")
        print("Trade partner is:", trade.partner)
        print("We would send:", len(trade.items_to_send), "items")
        print("We would receive:", len(trade.items_to_receive), "items")

        if trade.is_gift():
            print("Accepting the trade as it is a gift")
            await trade.accept()


client = MyClient()
client.run("username", "password")
```

## Bot Example

```py
from steam.ext import commands

bot = commands.Bot(command_prefix="!")


@bot.command
async def ping(ctx: commands.Context) -> None:
    await ctx.send("Pong!")


bot.run("username", "password")
```

## Links

- [Documentation](https://steam-py.github.io/docs/latest/)
- [Official Discord Server](https://discord.gg/MQ68WUS)
