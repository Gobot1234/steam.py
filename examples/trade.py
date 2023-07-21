import steam


class MyClient(steam.Client):
    async def on_ready(self):  # on_events in a subclassed client don't need the @client.event decorator
        print("------------")
        print("Logged in as")
        print("Username:", self.user)
        print("ID:", self.user.id64)
        print("Friends:", len(await self.user.friends()))
        print("------------")

    async def on_trade(self, trade: steam.TradeOffer):
        if not trade.is_our_offer():  # we have received a trade (yay)
            await trade.user.send("Thank you for your trade")
            print(f"Received trade: #{trade.id}")
            print("Trade partner is:", trade.user)
            print("We would send:", len(trade.sending), "items")
            print("We would receive:", len(trade.receiving), "items")

            if trade.is_gift():  # check if the trade is a gift
                print("Accepting the trade as it is a gift")
                await trade.accept()  # auto-accept the trade

    async def on_trade_update(self, _, trade: steam.TradeOffer):  # we accepted a trade
        if trade.state == steam.TradeOfferState.Accepted:
            await trade.user.send(f"Successfully accepted trade #{trade.id}")
            print(f"Accepted trade: #{trade.id}")
            print("Trade partner was:", trade.user)
            print("We sent:", len(trade.sending), "items")
            print("We received:", len(trade.receiving), "items")


client = MyClient()
client.run("username", "password")
