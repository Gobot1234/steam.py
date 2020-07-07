import steam


class MyClient(steam.Client):
    async def on_ready(
        self,
    ):  # on_events in a subclassed client don't need the @client.event decorator
        print("------------")
        print("Logged in as")
        print("Username:", self.user)
        print("ID:", self.user.id64)
        print("Friends:", len(self.user.friends))
        print("------------")

    async def on_trade_receive(self, trade):  # we have received a trade (yay)
        await trade.partner.send("Thank you for your trade")
        print(f"Received trade: #{trade.id}")
        print("Trade partner is:", trade.partner)
        print("We would send:", len(trade.items_to_send), "items")
        print("We would receive:", len(trade.items_to_receive), "items")

        if trade.is_gift():  # check if the trade is a gift
            print("Accepting the trade as it is a gift")
            await trade.accept()  # auto-accept the trade

    async def on_trade_accept(self, trade):  # we accepted a trade
        await trade.partner.send(f"Successfully accepted trade #{trade.id}")
        print(f"Accepted trade: #{trade.id}")
        print("Trade partner was:", trade.partner)
        print("We sent:", len(trade.items_to_send), "items")
        print("We received:", len(trade.items_to_receive), "items")


client = MyClient()
client.run("username", "password")
