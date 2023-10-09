"""A basic integration test"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
from io import StringIO
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

    async def login(self, *args: Any, **kwargs: Any) -> None:
        asyncio.get_running_loop().set_debug(True)
        stdout = StringIO()
        try:
            with contextlib.redirect_stdout(stdout):
                await super().login(*args, **kwargs)
        except steam.LoginError as exc:
            if not exc.__cause__ or not isinstance(exc.__cause__, steam.HTTPException) or exc.__cause__.code != 429:
                raise
            self.failed_to_login = True
        finally:
            if stdout.getvalue():
                self.failed_to_login = True

    def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None:
        if event.upper() in self.__annotations__:
            setattr(self, event.upper(), True)

        super().dispatch(event, *args, **kwargs)

    async def on_ready(self) -> None:
        await self.close()


@pytest.mark.skipif(
    True,
    # not USERNAME if not RUNNING_AS_ACTION else False,
    reason=(
        "If there are issues they are normally present in one of the 2 versions, as well, it will ask for a CAPTCHA "
        "code if you login twice simultaneously on the third computer"
    ),
)
@pytest.mark.asyncio
async def test_basic_events() -> None:
    client = Client()
    await client.login(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
    if not client.failed_to_login:
        assert client.LOGIN
        assert client.CONNECT
        assert client.READY
        # assert client.LOGOUT  # TODO: check what's happening here
    else:
        atexit.register(print, "Failed to login")  # make sure we can tell if we failed to login
