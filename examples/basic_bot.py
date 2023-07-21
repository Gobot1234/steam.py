import asyncio
import random

import steam
from steam.ext import commands

bot = commands.Bot(command_prefix="!")


@bot.event
async def on_ready():
    print("------------")
    print("Logged in as")
    print("Username:", bot.user)
    print("ID:", bot.user.id64)
    print("Friends:", len(await bot.user.friends()))
    print("------------")


@bot.command
async def trade(ctx: commands.Context):
    """Read items from a trade offer."""
    await ctx.send(f"Send me a trade {ctx.author}!")

    def check(trade: steam.TradeOffer) -> bool:
        return trade.user == ctx.author and not trade.is_our_offer()

    try:
        offer = await bot.wait_for("trade", timeout=60, check=check)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to send the offer")
    else:
        await ctx.send(
            (
                f"You were going to send {len(offer.receiving)} items\n"
                f"You were going to receive {len(offer.receiving)} items"
            )
        )
        await offer.decline()


@bot.command
async def roll(ctx: commands.Context, sides: int = 6, rolls: int = 1):
    """Roll a dice."""
    result = ", ".join(str(random.randint(1, sides)) for _ in range(rolls))
    await ctx.send(result)


@bot.command
async def choose(ctx: commands.Context, *choices: str):
    """Chooses between multiple choices."""
    await ctx.send(random.choice(choices))


@bot.command(aliases=["pong"])
async def ping(ctx: commands.Context):
    """Ping command to display latency."""
    await ctx.send(f"Pong! My latency is {bot.latency * 1000:2f}")


bot.run("username", "password")
