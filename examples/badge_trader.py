"""This example aims to demonstrate more advanced ext.commands usage with a small badge trading bot."""

import asyncio
import math
from collections.abc import Iterable
from operator import attrgetter
from typing import TypeVar

import steam
from steam.ext import commands

bot = commands.Bot(command_prefix="!")
TRADING_CARDS = steam.STEAM


@bot.command
async def badges(ctx: commands.Context, user: steam.PartialUser = commands.DefaultAuthor):
    """Give some info about a user's current badges."""
    badges = await user.badges()
    favourite_badge = await user.favourite_badge()
    scarcest_badge = min(
        badges,
        key=attrgetter("scarcity"),  # attrgetter("name") ≈ lambda x: x.name
        default=None,
    )

    fragments = [f"You have {len(badges)} badge{'s' * (len(badges) != 1)}"]
    if favourite_badge is not None:
        fragments.append(f"your favourite badge is {await favourite_badge.name()}")
    if scarcest_badge is not None:
        fragments.append(
            f"your scarcest badge is {await scarcest_badge.name()} with a scarcity of {scarcest_badge.scarcity}"
        )

    # join the fragments using proper grammar because manners make'th man
    await ctx.send(fragments[0] if len(fragments) == 1 else f"{', '.join(fragments[:-1])} and {fragments[-1]}")


@bot.group
async def level(ctx: commands.Context, to: float | None = None):
    """An example root command which could implement a calculation to work out how much this will cost."""
    if to is None:
        await ctx.send("Currently badge sets cost £1234 and can are being bought for £99")
    else:
        await ctx.send(f"To level up to {to} will cost you £200")


def required_xp(desired_level: float, current_level: float) -> float:
    """Returns the amount of XP required to get between `desired_level` and `current_level`.

    Unless you have a decent understanding of calculus I'd just ignore how this works and just accept that it does.

    For those of you who understand how calculus works and know a bit of number theory:

        - Steam levels work so that the amount of XP required to level up is the ceiling of the non-unit values times by 100.
        e.g.:

            - Level 8 -> 9 requires 100 XP
            - Level 12 -> 13 requires 200 XP
            - Level 12 -> 14 requires 400 XP

        - We can determine the gradient of the function that describes the amount of XP required in an interval of 10 levels

          The formula for which looks like:

          df         ⌈ l + 10 ⌉
          -- = 100 · | ------ | - 100
          dl         |   10   |

        - Using integration that I don't have any kind of proof for other than a very old looking wolfram alpha page
          (https://functions.wolfram.com/IntegerFunctions/Ceiling/21/02/01)

                     ⌈x⌉
          ∫ ⌈x⌉ dx = --- · (2x - ⌈x⌉ + 1) + C
                      2

          Therefore it follows (using a substitution (z := l/10 + 1) that the integral of our `f` function is:

                     ⌈z⌉
          f = 1000 · --- · (2z - ⌈z⌉ + 1) - 1000z
                      2

        - This is what the inner function `f` here is doing

        - Also this doesn't use the first formula because fractional inputs are fun
    """

    def f(level: float) -> float:
        z = level / 10 + 1
        return 500 * math.ceil(z) * (2 * z - math.ceil(z) + 1) - 1_000 * z

    return math.ceil(f(desired_level) - f(current_level))


OwnerT = TypeVar("OwnerT", bound=steam.abc.PartialUser)  # preserve the type of item.owner


def get_trading_cards(items: Iterable[steam.Item[OwnerT]]) -> list[steam.Item[OwnerT]]:
    return [
        card
        for card in items
        if any(
            tag.category == "item_class" and tag.internal_name == f"item_class_{steam.CommunityItemClass.Badge.value}"
            for tag in card.tags
        )
    ]


@level.command
async def up(ctx: commands.Context, level: float, ignore_owned_cards: bool = False):
    """Level up to level by purchasing cards to craft into booster packs."""
    badges = await ctx.author.badges()
    current_xp = badges.xp
    if not ignore_owned_cards:
        trading_cards = get_trading_cards(await ctx.author.inventory(TRADING_CARDS))
        craftable_badges = {  # TODO this is a lie
            app: {
                item_def
                for item_def in await app.community_item_definitions()
                if item_def.class_ == steam.CommunityItemClass.GameCard
            }
            for app in {card.market_fee_app for card in trading_cards}
        }

        # check how many cards the user already has that can be crafted
        # each badge crafted gives 100 xp
        current_xp += len(craftable_badges) * 100
    required_xp_ = required_xp(level, badges.level) - current_xp
    math.ceil(required_xp_ / 100)

    amount = 100
    try:
        async with asyncio.timeout(600):
            await for_payment(ctx, amount)
    except asyncio.TimeoutError:
        return await ctx.send("Timed out waiting for payment")

    get_trading_cards(await bot.user.inventory(TRADING_CARDS))
    sending_cards = ...
    await ctx.author.send(trade=steam.TradeOffer(sending=sending_cards))


async def for_payment(ctx: commands.Context, amount: float):
    """This function is left unimplemented to allow for whatever method you want to take payments."""
    await ctx.send("Send a payment to ...")
    ...


@bot.event
async def on_trade(trade: steam.TradeOffer):
    if not trade.is_our_offer():
        if (
            all(item.app == steam.STEAM for item in trade.sending)  # we are only sending items for steam
            and len(get_trading_cards(trade.sending)) == len(trade.sending)  # we are sending cards not gifts etc
        ):  # fmt: skip
            if len(trade.sending) * 2 == len(get_trading_cards(trade.receiving)):
                # accept 1:2 trades for any cards
                await trade.accept()
            else:
                # try and counter the trade to fix the ratio
                their_cards = get_trading_cards(await trade.user.inventory(steam.STEAM))
                if len(their_cards) <= len(trade.sending) * 2:
                    receiving = their_cards[len(trade.sending) * 2 :]
                return await trade.counter(
                    steam.TradeOffer(
                        sending=trade.sending, receiving=receiving, message="The ratio of accepted cards is 1:2"
                    )
                )
        await trade.decline()
