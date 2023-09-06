import asyncio
import time

import pytest
from typing_extensions import Self

import steam.guard
from steam import Client

# these obviously aren't valid (anymore ;))
SHARED_SECRET = "CHBFdSqFhRY9Wdyo1dIOMsmKUFg="
IDENTITY_SECRET = "YsmBh3FQiHkrTCPKm3FhcGF40x0="
# TODO find the GoBOT ones


def test_get_authentication_code() -> None:
    assert steam.guard.get_authentication_code(SHARED_SECRET, 1655569846) == "K4X5X"
    assert steam.guard.get_authentication_code(SHARED_SECRET, 1656569918) == "3NH2G"


def test_get_confirmation_code() -> None:
    assert steam.guard.get_confirmation_code(IDENTITY_SECRET, "allow")
    assert steam.guard.get_confirmation_code(IDENTITY_SECRET, "cancel")


def test_get_device_id() -> None:
    assert steam.guard.get_device_id(76561198248053954)
    assert steam.guard.get_device_id(76561198248053954)


class Timer:
    start: float
    stop: float

    def __enter__(self) -> Self:
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop = time.perf_counter()

    @property
    def delta(self) -> float:
        return self.stop - self.start


@pytest.mark.asyncio
async def test_generate_confirmation_code_one_per_second() -> None:
    client = Client()
    client.identity_secret = IDENTITY_SECRET
    state = client._state

    with Timer() as timer:
        code_1 = await state._get_confirmation_code("allow")
        code_2 = await state._get_confirmation_code("cancel")
    assert timer.delta == pytest.approx(0, abs=3e-3)  # type: ignore
    assert code_1 != code_2

    await asyncio.sleep(1.5)

    with Timer() as timer:
        code_1 = await state._get_confirmation_code("allow")
        code_2 = await state._get_confirmation_code("allow")
        code_3 = await state._get_confirmation_code("allow")
        code_4 = await state._get_confirmation_code("allow")
    assert 2 <= timer.delta <= 3.004
    assert code_1 != code_2 != code_3 != code_4

    await asyncio.sleep(1.5)

    with Timer() as timer:
        code_1 = await state._get_confirmation_code("allow")
        code_2 = await state._get_confirmation_code("cancel")

    await asyncio.sleep(1.5)

    with Timer() as timer:
        await state._get_confirmation_code("allow")
    assert timer.delta == pytest.approx(0, abs=1e-3)  # type: ignore
