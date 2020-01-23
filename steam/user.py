from .abc import BaseUser

from .utils.id import *
from .utils.steamid import SteamID


class ClientUser(BaseUser):
    #__slots__ = ('id64', 'id2', 'id3', 'avatar_url', 'activity', 'state', 'profile_url')

    def __init__(self, state):
        self.state = state
        print(self.state.http.steam_id)
        self.state.loop.run_until_complete(self._update())

    def __repr__(self):
        return '<name {0.name}, id64{0.id64}, level {0.level}>'.format(self)

    async def _update(self):
        self.steam_id = SteamID(self.state.http.steam_id)
        print(self.steam_id.as_steam3[5:-1])
        async with self.state.http.session as session:
            async with session.get(
                    f'https://steamcommunity.com/miniprofile/{self.steam_id.as_steam3[5:-1]}/json') as r:
                data = await r.json()
        self.username = data['persona_name']
        self.avatar_url = data['avatar_url']
        self.level = data['level']

    @property
    async def id64(self):
        return self.steam_id.as_64

    @property
    async def id2(self):
        return self.steam_id.as_steam2

    @property
    async def id3(self):
        return self.steam_id.as_steam3

    @property
    def username(self):
        return self.username

    @property
    def level(self):
        return self.level

    @property
    def avatar_url(self):
        return self.avatar_url


class User(BaseUser):
    #__slots__ = ('name', 'id64', 'avatar_url', 'activity', 'state', 'profile_url')

    def __init__(self, state, user):
        self.state = state
        self._update(user)  # from https://steamcommunity.com/miniprofile/ID3/json

    def __repr__(self):
        return '<name {0.name}, id64{0.id64}, level {0.level}>'.format(self)

    def _update(self, data):
        self.name = data['persona_name']
        self.id64 = name_to_ID64(self.state.http, data['persona_name'])
        self.avatar_url = data['avatar_url']
        self.level = data['level']

    @property
    async def id64(self):
        return self.id64

    @property
    def name(self):
        return self.name

    @property
    def level(self):
        return self.level

    @property
    def avatar_url(self):
        return self.avatar_url

    async def block(self):
        return await self.state.http.block()

    async def add(self):
        return await self.state.http.add_friend()
