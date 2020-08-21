# -*- coding: utf-8 -*-

import steam

from . import USERNAME, PASSWORD, SHARED_SECRET, IDENTITY_SECRET


class Client(steam.Client):
    async def start(self) -> None:
        try:
            await super().start(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
        except steam.LoginError as exc:
            if "captcha code" not in exc.args[0]:
                raise exc
            return
        await self.wait_for("login", timeout=120)
        await self.wait_for("connect", timeout=120)
        await self.wait_for("ready", timeout=120)
        await self.close()
        await self.wait_for("logout", timeout=120)


def test_events():
    client = Client()
    client.run()
