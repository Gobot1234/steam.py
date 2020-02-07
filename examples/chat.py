import steam

api_key = ''
username = ''
password = ''
shared_secret = ''
user_to_add = 76561198400794682

client = steam.Client(api_key=api_key)


@client.event
async def on_ready():
    print('Ready!')
    print(f'Currently logged in as:\n'
          f'Username: {client.user.name}\n'
          f'ID: {client.user.id64}')


@client.event
async def on_login():
    print('Logged in')
    print(f'Getting the user with the id {user_to_add}')
    user = await client.fetch_user(user_to_add)
    print(f'Attempting to add user {user.name}')


@client.event
async def on_logout():
    print('Logged out')


client.run(username=username, password=password, shared_secret=shared_secret)
