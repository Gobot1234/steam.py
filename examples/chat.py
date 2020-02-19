import steam

api_key = ''
username = ''
password = ''
shared_secret = ''

client = steam.Client(api_key=api_key)


@client.event
async def on_ready():
    print('Currently logged and ready!')
    print('Username:', client.user.name)
    print('ID:', client.user.id64)
    print('Friends:', len(client.user.friends))


@client.event
async def on_login():
    print(f'Logged in with the code: {client.code}')


@client.event
async def on_logout():
    print('Logged out')


client.run(username=username, password=password, shared_secret=shared_secret)
