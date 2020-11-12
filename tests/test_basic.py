# -*- coding: utf-8 -*-

"""A basic integration test"""

import sys
from typing import Any

import pytest

import steam

from . import IDENTITY_SECRET, PASSWORD, SHARED_SECRET, USERNAME


class Client(steam.Client):
    LOGIN = False
    CONNECT = False
    READY = False
    LOGOUT = False
    failed_to_login = False

    async def start(self, *args: Any, **kwargs: Any) -> None:
        try:
            await super().start(*args, **kwargs)
        except steam.LoginError as exc:
            if "too many login failures" not in exc.args[0]:
                raise exc
            self.failed_to_login = True

    async def on_login(self) -> None:
        self.LOGIN = True

    async def on_connect(self) -> None:
        self.CONNECT = True

    async def on_ready(self) -> None:
        self.READY = True
        await self.close()

    async def on_logout(self) -> None:
        self.LOGOUT = True


@pytest.mark.skipif(
    sys.version_info[:2] == (3, 8),
    reason="If there are issues they are normally present in one of the 2 versions, "
           "aswell, it will ask for a CAPTCHA code if you login twice simultaneously on the third computer"
)
def test_basic_events() -> None:
    client = Client()
    client.run(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
    if not client.failed_to_login:
        assert client.LOGIN
        assert client.CONNECT
        assert client.READY
        assert client.LOGOUT
