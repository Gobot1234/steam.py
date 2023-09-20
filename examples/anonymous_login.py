import asyncio

import steam

client = steam.Client()


@client.event
async def on_login():
    print(f"Logged to anonymous client ID64: {client.user.id64}")

    info = await steam.TF2.info()
    print(f"{info.name} info:")
    print(f"id {info.id}")
    print(f"type {info.type}")
    print(f"created on {info.created_at:%A %Y/%m/%d at %H:%M:%S}")  # Formats time as "YYYY/MM/DD at HH:MM:SS"
    print(f"{len(info.branches)} branches, {', '.join(branch.name for branch in info.branches)}")

    await client.close()


async def main():
    await client.anonymous_login()


asyncio.run(main())
