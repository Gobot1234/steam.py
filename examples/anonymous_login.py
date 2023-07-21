import asyncio

import steam

client = steam.Client()


@client.event
async def on_login():
    print(f"Logged in as {client.user!r}")

    info = await steam.TF2.info()
    print(f"TF2 info: {info!r}")
    print(f"TF2 was created on {info.created_at:%A %Y/%m/%d at %H:%M:%S}")
    print(f"TF2 has {len(info.branches)} branches")

    await client.close()


async def main():
    await client.anonymous_login()


asyncio.run(main())
