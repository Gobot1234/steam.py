import pytest

from steam.id import id64_from_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url, id64",
    [
        ("https://steamcommunity.com/id/Gobot1234", 76561198248053954),
        ("https://steamcommunity.com/profiles/76561198400794682", 76561198400794682),
        ("https://steamcommunity.com/groups/Valve", 103582791429521412),
        ("https://steamcommunity.com/gid/103582791429521412", 103582791429521412),
        ("https://steamcommunity.com/app/570", 103582791433224455),
        ("https://steamcommunity.com/games/DOTA2", 103582791433224455),
        ("https://steamcommunity.com/profiles/0", None),
        ("https://steamcommunity.com/gid/0", None),
        ("https://steamcommunity.com/app/0", None),
    ],
)
async def test_from_url(url: str, id64: int | None) -> None:
    assert await id64_from_url(url) == id64
