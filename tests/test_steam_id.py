"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Mostly from https://github.com/ValvePython/steam/blob/master/tests/test_steamid.py
"""

from __future__ import annotations

from typing import Optional, Union

import pytest

from steam import InvalidSteamID, SteamID, Type, Universe


def test_hash() -> None:
    assert hash(SteamID(1)) == hash(SteamID(1))
    assert SteamID(12345) != hash(SteamID(8888))


@pytest.mark.parametrize(
    "steam_id, components",
    [
        (SteamID(1), [1, Type.Individual, Universe.Public, 1]),
        [SteamID("1"), [1, Type.Individual, Universe.Public, 1]],
        [SteamID(12), [12, Type.Individual, Universe.Public, 1]],
        [SteamID("12"), [12, Type.Individual, Universe.Public, 1]],
        [SteamID(123), [123, Type.Individual, Universe.Public, 1]],
        [SteamID("123"), [123, Type.Individual, Universe.Public, 1]],
        [SteamID(12345678), [12345678, Type.Individual, Universe.Public, 1]],
        [SteamID("12345678"), [12345678, Type.Individual, Universe.Public, 1]],
        [SteamID(0xFFFFFFFF), [0xFFFFFFFF, Type.Individual, Universe.Public, 1]],
        [SteamID(str(0xFFFFFFFF)), [0xFFFFFFFF, Type.Individual, Universe.Public, 1]],
        [SteamID(76580280500085312), [123456, Type.Individual, Universe.Public, 4444]],
        [SteamID("76580280500085312"), [123456, Type.Individual, Universe.Public, 4444]],
        [SteamID(103582791429521412), [4, Type.Clan, Universe.Public, 0]],
        [SteamID("103582791429521412"), [4, Type.Clan, Universe.Public, 0]],
        [SteamID(), [0, Type.Invalid, Universe.Invalid, 0]],
        [SteamID(id=0, type=0, universe=0, instance=0), [0, Type.Invalid, Universe.Invalid, 0]],
        [
            SteamID(id=0, type=Type.Invalid, universe=Universe.Invalid, instance=0),
            [0, Type.Invalid, Universe.Invalid, 0],
        ],
        [SteamID(id=0, type="Invalid", universe="Invalid", instance=0), [0, Type.Invalid, Universe.Invalid, 0]],
        [SteamID(1, 2), [1, 2, 1, 0]],
        [SteamID(1, 2, 3), [1, 2, 3, 0]],
        [SteamID(1, 2, 3, 4), [1, 2, 3, 4]],
    ],
)
def test_from_id(steam_id: SteamID, components: list[int]) -> None:
    assert steam_id.id == components[0]
    assert steam_id.type == components[1]
    assert steam_id.universe == components[2]
    assert steam_id.instance == components[3]


@pytest.mark.parametrize(
    "id64",
    [
        18379190083593961473,
        139611592743452673,
        "invalid_format",
        111111111111111111111111111111111111111,
        "1111111111111111111111111111111111111",
        -50,
    ],
)
def test_invalid_steam_id(id64: Union[int, str]) -> None:
    with pytest.raises(InvalidSteamID):
        SteamID(id64)


def test_kwarg_type() -> None:
    assert SteamID(id=5, type=1).type == Type.Individual
    assert SteamID(id=5, type="Individual").type == Type.Individual
    assert SteamID(id=5, type="AnonUser").type == Type.AnonUser


def test_kwarg_universe() -> None:
    with pytest.raises(InvalidSteamID):
        SteamID(id=5, universe="doesn't exist")
    with pytest.raises(InvalidSteamID):
        SteamID(id=5, universe=99999999)

    assert SteamID(id=5, universe=1).universe == Universe.Public
    assert SteamID(id=5, universe="Public").universe == Universe.Public
    assert SteamID(id=5, universe="Dev").universe == Universe.Dev


def test_kwarg_instance() -> None:
    assert SteamID(id=5, instance=1234).instance == 1234

    for type in Type:
        assert (
            SteamID(id=5, type=type).instance == 1
            if type in (Type.Individual, Type.GameServer)
            else SteamID(id=5, type=type).instance == 0
        )


@pytest.mark.parametrize(
    "steam_id, valid",
    [
        [SteamID(), False],
        [SteamID(0), False],
        [SteamID(1), True],
        [SteamID(1, type=Type.Invalid), False],  # type out of bound
        [SteamID(1, universe=Universe.Invalid), False],
        [SteamID(1, universe=Universe.Max), False],  # universe out of bound
        [SteamID(5), True],
        # individual
        [SteamID(123, Type.Individual, Universe.Public, instance=0), True],
        [SteamID(123, Type.Individual, Universe.Public, instance=1), True],
        [SteamID(123, Type.Individual, Universe.Public, instance=2), True],
        [SteamID(123, Type.Individual, Universe.Public, instance=3), True],
        [SteamID(123, Type.Individual, Universe.Public, instance=4), True],
        [SteamID(123, Type.Individual, Universe.Public, instance=5), False],
        [SteamID(123, Type.Individual, Universe.Public, instance=333), False],
        # clan
        [SteamID(123, type=Type.Clan, universe=Universe.Public, instance=333), False],
        [SteamID(1, Type.Clan, Universe.Public, instance=1), False],
        [SteamID(1, Type.Clan, Universe.Public, instance=1234), False],
        [SteamID(123, type=Type.Clan, universe=Universe.Public, instance=333), False],
        [SteamID(1, Type.Clan, Universe.Public, instance=0), True],
    ],
)
def test_is_valid(steam_id: SteamID, valid: bool) -> None:
    assert steam_id.is_valid() is valid


def test_dunders() -> None:
    assert not SteamID(10) == SteamID(5)
    assert SteamID(10) != SteamID(5)
    assert hash(SteamID(5)) == hash(SteamID(5))
    assert str(SteamID(76580280500085312)) == "76580280500085312"
    assert eval(repr(SteamID(76580280500085312))) == SteamID(76580280500085312)


@pytest.mark.parametrize(
    "steam_id, id2",
    [
        [SteamID("STEAM_0:1:4"), "STEAM_1:1:4"],
        [SteamID("STEAM_1:1:4"), "STEAM_1:1:4"],
        [SteamID("STEAM_0:0:4"), "STEAM_1:0:4"],
        [SteamID("STEAM_1:0:4"), "STEAM_1:0:4"],
    ],
)
def test_as_id2(steam_id: SteamID, id2: str) -> None:
    assert steam_id.id2 == id2


@pytest.mark.parametrize(
    "steam_id, id2_zero",
    [
        [SteamID("STEAM_0:1:4"), "STEAM_0:1:4"],
        [SteamID("STEAM_1:1:4"), "STEAM_0:1:4"],
        [SteamID("STEAM_0:0:4"), "STEAM_0:0:4"],
        [SteamID("STEAM_1:0:4"), "STEAM_0:0:4"],
        [SteamID("STEAM_4:0:4"), "STEAM_4:0:4"],
        [SteamID("STEAM_4:1:4"), "STEAM_4:1:4"],
    ],
)
def test_as_id2_zero(steam_id: SteamID, id2_zero: str) -> None:
    assert steam_id.id2_zero == id2_zero


@pytest.mark.parametrize(
    "steam_id, id3",
    [
        [SteamID("[U:1:1234]"), "[U:1:1234:0]"],
        [SteamID("[U:1:1234]"), "[U:1:1234:0]"],
        [SteamID("[U:1:1234:56]"), "[U:1:1234:56]"],
        [SteamID("[g:1:4]"), "[g:1:4]"],
        [SteamID("[A:1:1234:567]"), "[A:1:1234:567]"],
        [SteamID("[G:1:1234:567]"), "[G:1:1234]"],
        [SteamID("[T:1:1234]"), "[T:1:1234]"],
        [SteamID("[c:1:1234]"), "[g:1:1234]"],
        [SteamID("[L:1:1234]"), "[L:1:1234]"],
    ],
)
def test_as_steam3(steam_id: SteamID, id3: str) -> None:
    assert steam_id.id3 == id3


@pytest.mark.parametrize(
    "steam_id, community_url",
    [
        [SteamID(76580280500085312), "https://steamcommunity.com/profiles/76580280500085312"],  # user url
        [SteamID("[g:1:4]"), "https://steamcommunity.com/gid/103582791429521412"],  # group url
        [SteamID("[A:1:4]"), None],  # else None
    ],
)
def test_community_url(steam_id: SteamID, community_url: Optional[str]) -> None:
    assert steam_id.community_url == community_url


@pytest.mark.parametrize(
    "steam_id, invite_code",
    [
        [SteamID(0, Type.Individual, Universe.Public, instance=1), None],
        [SteamID(123456, Type.Individual, Universe.Public, instance=1), "cv-dgb"],
        [SteamID(123456, Type.Individual, Universe.Beta, instance=1), "cv-dgb"],
        [SteamID(123456, Type.Invalid, Universe.Public, instance=1), None],
        [SteamID(123456, Type.Clan, Universe.Public, instance=1), None],
    ],
)
def test_as_invite_code(steam_id: SteamID, invite_code: Optional[str]) -> None:
    assert steam_id.invite_code == invite_code


@pytest.mark.parametrize(
    "steam_id, invite_url",
    [
        [SteamID(0, Type.Individual, Universe.Public, instance=1), None],
        [SteamID(123456, Type.Individual, Universe.Public, instance=1), "https://s.team/p/cv-dgb"],
        [SteamID(123456, Type.Individual, Universe.Beta, instance=1), "https://s.team/p/cv-dgb"],
        [SteamID(123456, Type.Invalid, Universe.Public, instance=1), None],
        [SteamID(123456, Type.Clan, Universe.Public, instance=1), None],
    ],
)
def test_as_invite_url(steam_id: SteamID, invite_url: Optional[str]) -> None:
    assert steam_id.invite_url == invite_url
