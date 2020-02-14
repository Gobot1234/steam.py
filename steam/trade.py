from .enums import Game, URL


class TradeOffer:
    """Represents a Trade offer from a User"""

    def __init__(self, state, data):
        self._state = state
        self._update(data)

    def _update(self, data):
        self.comment = data['comment']


class Inventory:
    """Represents a Users inventory"""

    __slots__ = ('items', 'owner', 'game', '_inventory', '_state')

    def __init__(self, state, data):
        self._state = state
        self._update(data)

    def __repr__(self):
        return "<Inventory owner='{0.owner}' game={0.game!r} len={0.__len__}>".format(self)

    def __len__(self):
        return self._inventory['total_inventory_count']

    def _update(self, data):
        self._inventory = data
        self.game = Game(app_id=data[0]['app_id'])
        self.owner = self._state.client.fetch_user(user_id=data['steam_id64'])
        self.items = [Item(item) for item in self._inventory['descriptions']]

    def filter_items(self, item_name: str):
        """Filters items by name into a list of one type of item

        Parameters
        ----------
        item_name: `str`
            The item to filter

        Returns
        -------
        Items: :class:`list`
            List of `~steam.Item`s
        """
        return [item for item in self.items if item.name == item_name]

    def get_item(self, item_name: str):
        """Get an item by name from a :class:`~steam.Inventory`

        Parameters
        ----------
        item_name: `str`
            The item to get from the

        Returns
        -------
        Item: :class:`~steam.Item`
            Returns the first found item with a matching name
        """
        return [item for item in self.items if item.name == item_name][0]

    async def update_inventory(self):
        """Update an :class:`~steam.User`'s :class:`~steam.Inventory`
        Returns
        -------
        Inventory: :class:`~steam.Inventory`
        """
        resp = await self._state.http._request('GET', f'{URL.COMMUNITY}/inventory/{self.owner.id64}/'
                                                      f'{self.game.app_id}/{self.game.context_id}')
        return Inventory(state=self._state, data=await resp.json())


class Item:
    """Represents an item in an User's inventory"""

    __slots__ = ('name', 'asset_id', 'colour', 'sterilised_name', 'descriptions',
                 'type', 'tags', 'game', 'icon_url', 'icon_url_large')

    def __init__(self, data):
        self._update(data)

    def __repr__(self):
        return "<Item name='{0.name}' asset_id={0.asset_id} game={0.game!r} tradable={0.tradable} " \
               "marketable={0.marketable}>".format(self)

    def _update(self, data):
        self.name = data['name']
        self.asset_id = data['asset_id']
        self.colour = int(data['name_color'], 16)
        self.sterilised_name = data['market_name']
        self.descriptions = data['descriptions']
        self.type = data['type']
        self.tags = data['tags']
        self.game = Game(app_id=data['app_id'])
        self._marketable = data['marketable']
        self._tradeable = data['tradable']
        self.icon_url = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url"]}'
        self.icon_url_large = f'https://steamcommunity-a.akamaihd.net/economy/image/{data["icon_url"]}'

    @property
    def tradable(self):
        return bool(self._tradeable)

    @property
    def marketable(self):
        return bool(self._marketable)
