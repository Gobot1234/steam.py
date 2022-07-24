import steam


class MyClient(steam.Client):
    async def on_ready(self):
        print("------------")
        print("Logged in as")
        print("Username:", self.user)
        print("ID:", self.user.id64)
        print("Friends:", len(await self.user.friends()))
        print("------------")

    async def on_message(self, message: steam.Message):
        # we do not want the bot to reply to itself
        if message.author == self.user:
            return

        if message.content.startswith("!hello"):
            await message.channel.send(f"Hello {message.author}")


client = MyClient()
client.run("username", "password")
