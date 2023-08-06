import steam
from steam.ext import tf2

bot = tf2.Bot(command_prefix="!")


@bot.event
async def on_ready() -> None:
    print("Bot is ready")


@bot.event
async def on_trade_accept(trade: steam.TradeOffer) -> None:
    refined_crafted = 0
    backpack = await bot.user.inventory(steam.TF2)
    for scrap_triplet in steam.utils.as_chunks(filter(lambda i: i.name == "Scrap Metal", backpack), 3):
        if len(scrap_triplet) != 3:
            break
        await bot.craft(scrap_triplet)

    for reclaimed_triplet in steam.utils.as_chunks(filter(lambda i: i.name == "Reclaimed Metal", backpack), 3):
        if len(reclaimed_triplet) != 3:
            break
        await bot.craft(reclaimed_triplet)
        refined_crafted += 1

    print(f"Crafted {refined_crafted} Refined Metal")


bot.run("username", "password")
