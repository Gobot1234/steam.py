# Some sections of this are from
# https://github.com/Gorialis/discord.py/blob/64d629c39fe92ad9e5fe383fd2954391237c134c/tests/test_utils.py

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from yarl import URL

from steam import ID, utils

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class FakeModel(NamedTuple):
    data: bytes


@pytest.mark.asyncio
async def test_find() -> None:
    # Generate a random collection of instances
    instances = [FakeModel(data=bytes(random.randrange(256) for _ in range(128))) for _ in range(256)]

    # Select a model to be found
    model_to_find = instances[0]

    # Shuffle instances
    random.shuffle(instances)

    # Ensure the model is found
    assert utils.find(lambda m: m.data == model_to_find.data, instances) == model_to_find

    async def async_iter() -> AsyncGenerator[FakeModel, None]:
        for model in instances:
            yield model

    assert await utils.find(lambda m: m.data == model_to_find.data, async_iter()) == model_to_find


@pytest.mark.asyncio
async def test_get() -> None:
    # Generate a random collection of instances
    instances = [FakeModel(data=bytes(random.randrange(256) for _ in range(128))) for _ in range(256)]

    # Select a model to be found
    model_to_find = instances[0]

    # Shuffle instances
    random.shuffle(instances)

    # Ensure the model is found
    assert utils.get(instances, data=model_to_find.data) == model_to_find

    async def async_iter() -> AsyncGenerator[FakeModel, None]:
        for model in instances:
            yield model

    assert await utils.get(async_iter(), data=model_to_find.data) == model_to_find


@pytest.mark.asyncio
async def test_as_chunks() -> None:
    assert not list(utils.as_chunks([], 1))

    first, *rest, last = list(utils.as_chunks(range(100), 5))
    assert len(first) == 5
    assert len(last) == 5
    assert all(len(chunk) == 5 for chunk in rest)

    first, *rest, last = list(utils.as_chunks(range(100), 3))
    assert len(first) == 3
    assert len(last) == 1
    assert all(len(chunk) == 3 for chunk in rest)

    async def arange(*args: Any, **kwargs: Any) -> AsyncGenerator[int, None]:
        for i in range(*args, **kwargs):
            yield i

    first, *rest, last = [elem async for elem in utils.as_chunks(arange(100), 5)]
    assert len(first) == 5
    assert len(last) == 5
    assert all(len(chunk) == 5 for chunk in rest)

    first, *rest, last = [elem async for elem in utils.as_chunks(arange(100), 3)]
    assert len(first) == 3
    assert len(last) == 1
    assert all(len(chunk) == 3 for chunk in rest)


@pytest.mark.asyncio
async def test_maybe_coroutine() -> None:
    def function_1() -> int:
        return 1

    assert await utils.maybe_coroutine(function_1) == 1

    async def function_2() -> int:
        return 2

    assert await utils.maybe_coroutine(function_2) == 2


user_1 = utils.TradeURLInfo(
    id=ID(440528954),
    token="MpmarfFH",
)
user_2 = utils.TradeURLInfo(
    id=ID(287788226),
    token="NBewyDB2",
)

user_2_no_token = utils.TradeURLInfo(
    id=ID(287788226),
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://steamcommunity.com/tradeoffer/new?partner=440528954&token=MpmarfFH", user_1),
        ("steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH", user_1),
        ("www.steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH", user_1),
        ("https://steamcommunity.com/tradeoffer/new/?partner=440528954&amp;token=MpmarfFH", user_1),
        (URL("https://steamcommunity.com/tradeoffer/new/?partner=440528954&token=MpmarfFH"), user_1),
        ("https://steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", user_2),
        ("steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", user_2),
        ("www.steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", user_2),
        ("https://steamcommunity.com/tradeoffer/new/?partner=287788226&amp;token=NBewyDB2", user_2),
        (URL("https://steamcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2"), user_2),
        ("https://steamcommunity.com/tradeoffer/new/?partner=287788226", user_2_no_token),
        ("https://stemcommunity.com/tradeoffer/new/?partner=287788226&token=NBewyDB2", None),
        ("https://steamcommunity.com/tradeoffer/new", None),
    ],
)
def test_parse_trade_url(url: str, expected: utils.TradeURLInfo | None) -> None:
    match = utils.parse_trade_url(url)

    assert match == expected if match is not None else expected is None


def test_update_class(): ...


def test_steam_time_parse() -> None:
    april_16th_2020 = datetime(2020, 4, 16, tzinfo=timezone.utc)
    assert april_16th_2020 == utils.DateTime.parse_steam_date("16 April, 2020")
    assert april_16th_2020 == utils.DateTime.parse_steam_date("April 16, 2020")

    assert april_16th_2020 == utils.DateTime.parse_steam_date("16 Apr, 2020", full_month=False)
    assert april_16th_2020 == utils.DateTime.parse_steam_date("Apr 16, 2020", full_month=False)

    assert utils.DateTime.parse_steam_date("Garbage Date") is None
    assert utils.DateTime.parse_steam_date("Garbage Date", full_month=False) is None


@pytest.mark.parametrize(
    "input, tags",
    [
        (
            '[random min="1" max="23" result="15"][/random]',
            [utils.BBCodeTag("random", (0, 46), {"min": "1", "max": "23", "result": "15"}, "")],
        ),
        (
            "[code]<UserMessage author=<ClientUser name='Vulcan Steve' state=[url=http://PersonaState.Online]PersonaState.Online[/url] id=1019733507 universe=Universe.Public instance=Instance.Desktop> id=2707242814382538752 channel=<DMChannel participant=<User name='Gobot1234' state=[url=http://PersonaState.Online]PersonaState.Online[/url] id=287788226 universe=Universe.Public instance=Instance.Desktop>>>[/code]",
            [
                utils.BBCodeTag(
                    "code",
                    (0, 402),
                    {},
                    "<UserMessage author=<ClientUser name='Vulcan Steve' state=[url=http://PersonaState.Online]PersonaState.Online[/url] id=1019733507 universe=Universe.Public instance=Instance.Desktop> id=2707242814382538752 channel=<DMChannel participant=<User name='Gobot1234' state=[url=http://PersonaState.Online]PersonaState.Online[/url] id=287788226 universe=Universe.Public instance=Instance.Desktop>>>",
                ),
                utils.BBCodeTag(
                    "url",
                    (64, 121),
                    {"": "http://PersonaState.Online"},
                    "PersonaState.Online",
                ),
                utils.BBCodeTag(
                    "url",
                    (271, 328),
                    {"": "http://PersonaState.Online"},
                    "PersonaState.Online",
                ),
            ],
        ),
        (
            "[tradeoffer sender=287788226 id=5554545][/tradeoffer]",
            [utils.BBCodeTag("tradeoffer", (0, 53), {"sender": "287788226", "id": "5554545"}, "")],
        ),
        (
            '[tradeofferlink url="https://steamcommunity.com/tradeoffer/new?partner=287788226&token=NBewyDB2" partner="287788226"]https://steamcommunity.com/tradeoffer/new?partner=287788226&token=NBewyDB2[/tradeofferlink]',
            [
                utils.BBCodeTag(
                    name="tradeofferlink",
                    position=(0, 208),
                    attributes={
                        "url": "https://steamcommunity.com/tradeoffer/new?partner=287788226&token=NBewyDB2",
                        "partner": "287788226",
                    },
                    inner="https://steamcommunity.com/tradeoffer/new?partner=287788226&token=NBewyDB2",
                )
            ],
        ),
    ],
)
def test_parse_bb_code(input: str, tags: list[utils.BBCodeTag]) -> None:
    assert utils.parse_bb_code(input).tags == tags
