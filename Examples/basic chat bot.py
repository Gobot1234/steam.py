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


@client.event
async def on_ready():
    print('Ready!')


@client.event
async def on_logout():
    print('Logged out')


client.run(username=username, password=password, shared_secret=shared_secret)
