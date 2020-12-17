# -*- coding: utf-8 -*-

"""A basic integration test"""

import sys
from typing import Any

import pytest

import steam

from . import IDENTITY_SECRET, PASSWORD, SHARED_SECRET, USERNAME


class Client(steam.Client):
    LOGIN: bool = False
    CONNECT: bool = False
    READY: bool = False
    LOGOUT: bool = False
    failed_to_login: bool = False

    async def start(self, *args: Any, **kwargs: Any) -> None:
        try:
            await super().start(*args, **kwargs)
        except steam.LoginError as exc:
            if "429 Too Many Requests" not in exc.args[0]:
                raise exc
            self.failed_to_login = True

    def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        if event.upper() in self.__annotations__:
            setattr(self, event.upper(), True)

        super().dispatch(event, *args, **kwargs)

    async def on_ready(self) -> None:
        await self.close()


@pytest.mark.skipif(
    sys.version_info[:2] == (3, 8) or not USERNAME,
    reason="If there are issues they are normally present in one of the 2 versions, "
    "as well, it will ask for a CAPTCHA code if you login twice simultaneously on the third computer",
)
def test_basic_events() -> None:
    client = Client()
    client.run(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
    if not client.failed_to_login:
        assert client.LOGIN
        assert client.CONNECT
        assert client.READY
        assert client.LOGOUT
