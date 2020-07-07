import asyncio
import random

from steam.ext import commands

bot = commands.Bot(command_prefix="!")


@bot.event
async def on_ready():
    print("------------")
    print("Logged in as")
    print("Username:", bot.user)
    print("ID:", bot.user.id64)
    print("Friends:", len(bot.user.friends))
    print("------------")


@bot.command()
async def trade(ctx):
    await ctx.send(f"Send me a trade {ctx.author}!")

    def check(trade):
        return trade.partner == ctx.author

    try:
        offer = await bot.wait_for("trade_receive", timeout=60, check=check)
    except asyncio.TimeoutError:
        await ctx.send("You took too long to send the offer")
    else:
        await ctx.send(
            f"You were going to send {len(offer.items_to_receive)} items\n"
            f"You were going to receive {len(offer.items_to_receive)} items"
        )
        await offer.decline()


@bot.command()
async def roll(ctx, sides: int = 6, rolls: int = 1):
    """Roll a dice."""
    result = ", ".join(str(random.randint(1, sides)) for _ in range(rolls))
    await ctx.send(result)


@bot.command()
async def choose(ctx, *choices):
    """Chooses between multiple choices."""
    await ctx.send(random.choice(choices))


@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! My latency is {bot.latency * 1000:2f}")


bot.run("username", "password")
