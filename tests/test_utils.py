# Some sections of this are from
# https://github.com/Gorialis/discord.py/blob/64d629c39fe92ad9e5fe383fd2954391237c134c/tests/test_utils.py

from __future__ import annotations

import random
from typing import NamedTuple, Optional

import pytest
from yarl import URL

from steam import utils


class FakeModel(NamedTuple):
    data: bytes


def test_find() -> None:
    # Generate a random collection of instances
    instances = [FakeModel(data=bytes(random.randrange(256) for _ in range(128))) for _ in range(256)]

    # Select a model to be found
    model_to_find = instances[0]

    # Shuffle instances
    random.shuffle(instances)

    # Ensure the model is found
    assert utils.find(lambda m: m.data == model_to_find.data, instances) == model_to_find


def test_get() -> None:
    # Generate a random collection of instances
    instances = [FakeModel(data=bytes(random.randrange(256) for _ in range(128))) for _ in range(256)]

    # Select a model to be found
    model_to_find = instances[0]

    # Shuffle instances
    random.shuffle(instances)

    # Ensure the model is found
    assert utils.get(instances, data=model_to_find.data) == model_to_find


@pytest.mark.asyncio
async def test_maybe_coroutine() -> None:
    def function_1() -> int:
        return 1

    assert await utils.maybe_coroutine(function_1) == 1

    async def function_2() -> int:
        return 2

    assert await utils.maybe_coroutine(function_2) == 2


user_1 = {
    "user_id": "440528954",
    "token": "MpmarfFH",
}
user_2 = {
    "user_id": "287788226",
    "token": "NBewyDB2",
}


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH", user_1),
        ("steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH", user_1),
        ("www.steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH", user_1),
        ("https://steamcommunity.com/tradeoffer/new/?partner=440528954&amp;token=MpmarfFH", user_1),
        (URL("https://steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH"), user_1),
        ("https://steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", user_2),
        ("steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", user_2),
        ("www.steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", user_2),
        ("https://steamcommunity.com/tradeoffer/new/?partner=287788226&amp;token=NBewyDB2", user_2),
        (URL("https://steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2"), user_2),
        ("https://stemcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", None),
        ("https://steamcommunity.com/tradeoffer/new", None),
    ],
)
def test_parse_trade_url(url: str, expected: Optional[dict[str, str]]) -> None:
    match = utils.parse_trade_url(url)

    assert match.groupdict() == expected if match is not None else expected is None
