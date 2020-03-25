steam.py
=========

A modern, easy to use, and async ready package to interact with the Steam API. Heavily inspired by [discord.py](https://github.com/Rapptz/discord.py).

[
![Codacy](https://img.shields.io/codacy/grade/a0405599d4ab4a8c82655873d7443532)](https://app.codacy.com/manual/Gobot1234/steam.py) [![GitHub issues](https://img.shields.io/github/issues-raw/Gobot1234/steam.py)](https://github.com/Gobot1234/steam.py/issues) [![GitHub stars](https://img.shields.io/github/stars/Gobot1234/steam.py)](https://github.com/Gobot1234/steam.py/stargazers) [![Discord](https://img.shields.io/discord/678629505094647819?color=7289da&label=Discord&logo=discord)](https://discord.gg/MQ68WUS)

Key Features
--------------

  - Modern Pythonic API using `async`/`await` syntax
  - Proper rate limit handling.
  - Easy to use with an object oriented design

Installation
--------------

**Python 3.6 or higher is required**

To install the library just run either of the following commands:

```sh
# Linux/macOS
python3 -m pip install -U git+https://github.com/Gobot1234/steam.py
# Windows
py -m pip install -U git+https://github.com/Gobot1234/steam.py
```

Quick Example
--------------

```py
import steam

class MyClient(steam.Client):
	async def on_login(self):
		print('Logged on as', self.user)

	async def on_trade_receive(self, trade):
        	print(f'Received trade: #{trade.id}')
     		print('To user:', trade.partner.name, 'Is one-sided:', trade.is_one_sided())
        	print('We are sending:')
        	print('\n'.join([item.name if item.name else item.asset_id for item in trade.items_to_give])
        	      if trade.items_to_give else 'Nothing')
        	print('We are receiving:')
        	print('\n'.join([item.name if item.name else item.asset_id for item in trade.items_to_receive])
        	      if trade.items_to_receive else 'Nothing')

client = MyClient()
client.run(username='username', api_key='api_key', password='password', shared_secret='shared_secret')
```

Links
------

  - [Documentation](https://steampy.readthedocs.io/en/latest/index.html)
  - [Official Discord Server](https://discord.gg/MQ68WUS)

#### Please note this repo is still in alpha if you find any bugs please make a [new issue](https://github.com/Gobot1234/steam.py/issues/new).
