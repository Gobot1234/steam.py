import steam

api_key = ''
username = ''
password = ''
shared_secret = ''


class MyClient(steam.Client):
    async def on_ready(self):
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
        print('From user:', trade.partner.name)
        print('We are sending:\n' + '\n'.join([item.name for item in trade.items_to_give]))
        print('We are receiving:\n' + '\n'.join([item.name for item in trade.items_to_receive]))


client = MyClient()
client.run(username, api_key, password, shared_secret)
