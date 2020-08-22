# -*- coding: utf-8 -*-

import pytest

import steam

from . import IDENTITY_SECRET, PASSWORD, SHARED_SECRET, USERNAME


class Client(steam.Client):
    LOGIN = False
    CONNECT = False
    READY = False
    LOGOUT = False

    async def start(self) -> None:
        try:
            await super().start(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
        except steam.LoginError as exc:
            if "captcha code" not in exc.args[0]:
                raise exc
            return

    async def on_login(self) -> None:
        self.LOGIN = True

    async def on_connect(self) -> None:
        self.CONNECT = True

    async def on_ready(self) -> None:
        self.READY = True
        await self.close()

    async def on_logout(self) -> None:
        self.LOGOUT = True


@pytest.mark.asyncio
async def test_basic_events():
    client = Client()
    try:
        await client.start()
    finally:
        await client.close()
    assert client.LOGIN
    assert client.CONNECT
    assert client.READY
    assert client.LOGOUT
