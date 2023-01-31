import babel.numbers  # pip install babel

import steam

client = steam.Client()


@client.event
async def on_ready():
    print("Logged in to", client.user)
    print("Wallet balance", babel.numbers.format_currency(client.wallet.balance / 100, client.wallet.currency.name))

    while True:
        print("Want to active a wallet code? (yes/no)")

        match (choice := await steam.utils.ainput(">>> ")).lower():
            case "yes" | "y":
                print("Enter the wallet code you wish to activate")
                code = await steam.utils.ainput(">>> ")

                try:
                    added_balance = await client.wallet.add(code.strip())
                except ValueError:
                    print("Code wasn't valid")
                else:
                    print("Added", babel.numbers.format_currency(added_balance / 100, client.wallet.currency.name))
            case "no" | "n":
                break
            case _:
                print(choice, "is not recognised as a yes or no")


client.run("username", "password")
