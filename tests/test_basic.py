# -*- coding: utf-8 -*-

import steam

from . import USERNAME, PASSWORD, SHARED_SECRET, IDENTITY_SECRET


class Client(steam.Client):
    LOGIN = False
    CONNECT = False
    READY = False
    LOGOUT = False

    async def on_login(self):
        self.LOGIN = True

    async def on_connect(self):
        self.CONNECT = True

    async def on_ready(self):
        self.READY = True
        await self.close()

    async def on_logout(self):
        self.LOGOUT = True


def test_events():
    client = Client()
    try:
        client.run(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
    except steam.LoginError as exc:
        if "captcha code" not in exc.args[0]:
            raise exc
        return
    assert client.LOGIN
    assert client.CONNECT
    assert client.READY
    assert client.LOGOUT
