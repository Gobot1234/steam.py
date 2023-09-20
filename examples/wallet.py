import babel.numbers  # pip install babel

import steam

client = steam.Client()


def format_balance(amount: int) -> str:
    """Formats ``amount`` as a string in the user's locale"""
    currency_divisor = 10 ** babel.numbers.get_currency_precision(
        client.wallet.currency.name
    )  # this should always be 100, but this is the number of pence in a pound/cent in a dollar
    return babel.numbers.format_currency(
        amount / currency_divisor,
        client.wallet.currency.name,
    )


@client.event
async def on_ready():
    print("Logged in to", client.user)
    print("Wallet balance", format_balance(client.wallet.balance))

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
                    print("Added", format_balance(added_balance))
            case "no" | "n":
                break
            case _:
                print(choice, "is not recognised as a yes or no")

    await client.close()


client.run("username", "password")
