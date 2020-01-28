import logging

import steam

api_key = ''
username = ''
password = ''
shared_secret = ''

logging.basicConfig(level=logging.INFO)
client = steam.Client(api_key=api_key)


@client.event
async def on_login():
    print('Logged in')
    user = await client.get_user(76561198248053954)
    print(f'Attempting to add user {user.name}')
    print(f'Result: {await user.add()}')


@client.event
async def on_ready():
    print('Ready!')
    print(f'Currently logged in as:\nUsername: {client.user.name}\nID: {client.user.id64}')


@client.event
async def on_logout():
    print('Logged out')


client.run(username=username, password=password, shared_secret=shared_secret)
