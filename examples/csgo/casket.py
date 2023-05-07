# A small example demonstrating how to interact with caskets.

from __future__ import annotations

import steam
from steam.ext import commands, csgo


class BackpackItemConverter(
    commands.Converter[csgo.BackpackItem[csgo.ClientUser]]
):  # custom converter to get `BackpackItem`s from the bot's inventory
    async def convert(self, ctx: commands.Context[MyBot], argument: str) -> csgo.BackpackItem[csgo.ClientUser]:
        backpack = await ctx.bot.user.inventory(steam.CSGO)
        try:
            asset_id = int(argument)
        except ValueError:
            item = steam.utils.get(backpack, name=argument)
        else:
            item = steam.utils.get(backpack, id=asset_id)

        if item is None:
            raise commands.BadArgument(f"{argument!r} is not present in the backpack")
        return item


class MyBot(csgo.Bot):
    @commands.group
    async def casket(self, ctx: commands.Context, *, casket: csgo.BackpackItem):
        """Get info about a casket/storage container."""
        if not isinstance(casket, csgo.Casket):
            return await ctx.send(f"{casket.name!r} is not a casket.")

        contents = await casket.contents()
        await ctx.send(
            f"""Info on {casket.custom_name!r}:
            - contains {casket.contained_item_count} items
            - first item in it is {contents[0].id}
            """
        )

    @casket.command
    async def add(self, ctx: commands.Context, item: csgo.BackpackItem, casket: csgo.BackpackItem):
        """Add an item to a casket."""
        if not isinstance(casket, csgo.Casket):
            return await ctx.send(f"{casket.name} is not a casket.")

        await casket.add(item)
        await ctx.send("👌")

    @casket.command
    async def remove(self, ctx: commands.Context, item_id: int, casket: csgo.BackpackItem):
        """Remove an item from a casket."""
        if not isinstance(casket, csgo.Casket):
            return await ctx.send(f"{casket.name} is not a casket.")

        contents = await casket.contents()
        casket_item = steam.utils.get(contents, asset_id=item_id)
        if casket_item is None:
            return await ctx.send(f"{item_id} is not in the casket.")
        await casket.remove(casket_item)
        await ctx.send("👌")


bot = MyBot(command_prefix="!")
bot.run("username", "password")
