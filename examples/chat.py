import steam

api_key = ''
username = ''
password = ''
shared_secret = ''
user_to_add = 1234567890

client = steam.Client(api_key=api_key)


@client.event
async def on_ready():
    print('Ready!')
    print(f'Currently logged and ready as:\n'
          f'Username: {client.user.name}\n'
          f'ID: {client.user.id64}')


@client.event
async def on_login():
    print('Logged in')


@client.event
async def on_logout():
    print('Logged out')


client.run(username=username, password=password, shared_secret=shared_secret)
