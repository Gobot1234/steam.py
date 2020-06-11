import steam


class MyClient(steam.Client):

    async def on_ready(self):  # on_events in a subclassed client don't need the @client.event decorator
        print('------------')
        print('Logged in as')
        print('Username:', self.user.name)
        print('ID:', self.user.id64)
        print('Friends:', len(self.user.friends))
        print('------------')

    async def on_logout(self):
        print('Logged out from:', self.user.name)

    async def on_trade_receive(self, trade):  # we have received a trade (yay)
        print(f'Received trade: #{trade.id}')
        print('Trade partner is:', trade.partner.name)
        print('We would send:')
        print('\n'.join(item.name if item.name else str(item.asset_id) for item in trade.items_to_send)
              if trade.items_to_send else 'Nothing')  # list the items the ClientUser would send
        print('We would receive:')
        print('\n'.join(item.name if item.name else str(item.asset_id) for item in trade.items_to_receive)
              if trade.items_to_receive else 'Nothing')  # list the items the ClientUser would receive

        if trade.is_gift():  # check if the trade is a gift
            print('Accepting the trade as it is a gift')
            await trade.accept()  # auto-accept the trade

    async def on_trade_accept(self, trade):  # we accepted a trade
        print(f'Accepted trade: #{trade.id}')
        print('Trade partner is:', trade.partner.name)
        print('We sent:')
        print('\n'.join(item.name if item.name else str(item.asset_id) for item in trade.items_to_send)
              if trade.items_to_send else 'Nothing')  # list the items the ClientUser has sent
        print('We received:')
        print('\n'.join(item.name if item.name else str(item.asset_id) for item in trade.items_to_receive)
              if trade.items_to_receive else 'Nothing')  # list the items the ClientUser has received


client = MyClient()
client.run('username', 'password', shared_secret='shared_secret')
