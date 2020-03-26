import steam

api_key = ''
username = ''
password = ''
shared_secret = ''


class MyClient(steam.Client):
    async def on_ready(self):  # this event isn't currently called but will be in the future  
        print('------------')
        print('Logged in as')
        print('Username:', self.user.name)
        print('ID:', self.user.id64)
        print('Friends:', len(self.user.friends))
        print('------------')

    async def on_login(self):
        print('Logged in with the code:', self.code)

    async def on_logout(self):
        print('Logged out from:', self.user.name)

    async def on_trade_receive(self, trade):
        print(f'Received trade: #{trade.id}')
        print('From user:', trade.partner.name, 'Is one-sided:', trade.is_one_sided())
        print('We are sending:')
        print('\n'.join([item.name if item.name is not None else item.asset_id for item in trade.items_to_give])
              if trade.items_to_give else 'Nothing')
        print('We are receiving:')
        print('\n'.join([item.name if item.name is not None else item.asset_id for item in trade.items_to_receive])
              if trade.items_to_receive else 'Nothing')

    async def on_trade_send(self, trade):
        print(f'Sent trade: #{trade.id}')
        print('To user:', trade.partner.name, 'Is one-sided:', trade.is_one_sided())
        print('We are sending:')
        print('\n'.join([item.name if item.name is not None else item.asset_id for item in trade.items_to_give])
              if trade.items_to_give else 'Nothing')
        print('We are receiving:')
        print('\n'.join([item.name if item.name is not None else item.asset_id for item in trade.items_to_receive])
              if trade.items_to_receive else 'Nothing')

    async def on_trade_accept(self, trade):
        print(f'Accepted trade: #{trade.id}')
        print('To user:', trade.partner.name, 'Is one-sided:', trade.is_one_sided())
        print('We sent:')
        print('\n'.join([item.name if item.name is not None else item.asset_id for item in trade.items_to_give])
              if trade.items_to_give else 'Nothing')
        print('We are receiving:')
        print('\n'.join([item.name if item.name is not None else item.asset_id for item in trade.items_to_receive])
              if trade.items_to_receive else 'Nothing')


client = MyClient()
client.run(username=username, api_key=api_key, password=password, shared_secret=shared_secret)
