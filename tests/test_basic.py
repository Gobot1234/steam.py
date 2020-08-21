# -*- coding: utf-8 -*-

import pytest
import steam

from . import USERNAME, PASSWORD, SHARED_SECRET, IDENTITY_SECRET


@pytest.mark.asyncio
async def test_events():
    client = steam.Client()
    try:
        await client.start(USERNAME, PASSWORD, shared_secret=SHARED_SECRET, identity_secret=IDENTITY_SECRET)
    except steam.LoginError as exc:
        if "captcha code" not in exc.args[0]:
            raise exc
        return
    await client.wait_for("login", timeout=120)
    await client.wait_for("connect", timeout=120)
    await client.wait_for("ready", timeout=120)
    await client.close()
    await client.wait_for("logout", timeout=120)
