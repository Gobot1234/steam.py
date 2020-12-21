from typing import TYPE_CHECKING, Optional

import discord  # pip install discord.py
from discord.ext import commands

import steam


class DiscordBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.default(),
            description="A simple bot that can get steam user info",
        )
        self.client = steam.Client()  # attach a steam.Client instance to the bot

    async def on_ready(self) -> None:
        await self.client.wait_until_ready()
        print("Ready")

    async def start(self, token: str, username: str, password: str) -> None:
        self.loop.create_task(
            self.client.start(username, password)
        )  # start the client in a task to avoid blocking the discord bot's startup
        await super().start(token)

    async def close(self) -> None:
        await self.client.close()  # make sure to close the client when we close the discord bot
        await super().close()


class UserConverter(commands.Converter):
    """Simple user converter"""

    async def convert(self, ctx: commands.Context, argument: str) -> Optional[steam.User]:
        try:
            return await ctx.bot.client.fetch_user(argument)
        except steam.InvalidSteamID:
            id64 = await steam.utils.id64_from_url(argument)
            if id64 is None:
                return
            await ctx.bot.client.fetch_user(id64)


if TYPE_CHECKING:
    UserConverter = Optional[steam.User]  # make linters play nicely with d.py's converters


bot = DiscordBot()


@bot.command()
async def user(ctx: commands.Context, user: UserConverter):
    """Show some basic info on a steam user"""
    if user is None:
        return await ctx.send("User not found")

    embed = discord.Embed(description=user.name, timestamp=user.created_at)
    embed.set_thumbnail(url=user.avatar_url)
    embed.add_field(name="64 bit ID:", value=str(user.id64))
    embed.add_field(name="Currently playing:", value=f"{user.game or 'Nothing'}")
    embed.add_field(name="Friends:", value=str(len(await user.friends())))
    embed.add_field(name="Games:", value=str(len(await user.games())))
    embed.set_footer(text="Account created on")  # set timestamp goes after this
    await ctx.send(f"Info on {user.name}", embed=embed)


bot.run("token", "username", "password")
