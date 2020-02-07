import steam

user_to_add = 1234567890

client = steam.Client(api_key=api_key)


"""Missing 
invites
system comments
"""

{
    "notifications": {
        "1": 0,  # trade notifcation
        "2": 0,
        "3": 0,
        "4": 0,  # comments
        "5": 1,  # items
        "6": 0,
        "8": 0,
        "9": 9,  # chat messages
        "10": 0,
        "11": 0
    }
}


@client.event
async def on_login():
    print('Logged in')
    user = await client.fetch_user(user_to_add)
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
