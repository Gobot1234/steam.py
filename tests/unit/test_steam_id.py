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

from steam import ID, InstanceFlag, InvalidID, Type, Universe


def test_hash() -> None:
    assert hash(ID(1)) == hash(ID(1))
    assert hash(ID(12345)) != hash(ID(8888))


@pytest.mark.parametrize(
    "steam_id, components",
    [
        (ID(1), [1, Type.Individual, Universe.Public, InstanceFlag.Desktop]),
        [ID("1"), [1, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID(12), [12, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID("12"), [12, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID(123), [123, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID("123"), [123, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID(12345678), [12345678, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID("12345678"), [12345678, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID(0xFFFFFFFF), [0xFFFFFFFF, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID(str(0xFFFFFFFF)), [0xFFFFFFFF, Type.Individual, Universe.Public, InstanceFlag.Desktop]],
        [ID(76580280500085312), [123456, Type.Individual, Universe.Public, 4444]],
        [ID("76580280500085312"), [123456, Type.Individual, Universe.Public, 4444]],
        [ID(103582791429521412), [4, Type.Clan, Universe.Public, InstanceFlag.All]],
        [ID("103582791429521412"), [4, Type.Clan, Universe.Public, InstanceFlag.All]],
        [ID(0), [0, Type.Invalid, Universe.Invalid, InstanceFlag.All]],
        [
            ID(id=0, type=Type.Invalid, universe=Universe.Invalid, instance=InstanceFlag.All),
            [0, Type.Invalid, Universe.Invalid, InstanceFlag.All],
        ],
        [
            ID(id=0, type=Type.Invalid, universe=Universe.Invalid, instance=InstanceFlag.All),
            [0, Type.Invalid, Universe.Invalid, InstanceFlag.All],
        ],
        [
            ID(id=0, type=Type.Invalid, universe=Type.Invalid, instance=InstanceFlag.All),
            [0, Type.Invalid, Universe.Invalid, InstanceFlag.All],
        ],
        [ID(1, Type.Multiseat), [1, Type.Multiseat, 1, 0]],
        [ID(1, Type.Multiseat, Universe.Internal), [1, Type.Multiseat, Universe.Internal, 0]],
        [
            ID(1, Type.Multiseat, Universe.Internal, InstanceFlag.Web),
            [1, Type.Multiseat, Universe.Internal, InstanceFlag.Web],
        ],
    ],
)
def test_from_id(steam_id: ID, components: list[int]) -> None:
    assert steam_id.id == components[0]
    assert steam_id.type == components[1]
    assert steam_id.universe == components[2]
    assert steam_id.instance == components[3]


@pytest.mark.parametrize(
    "id64",
    [
        "invalid_format",
        111111111111111111111111111111111111111,
        "1111111111111111111111111111111111111",
        -50,
    ],
)
def test_invalid_steam_id(id64: Union[int, str]) -> None:
    with pytest.raises(InvalidID):
        ID(id64)


def test_kwarg_type() -> None:
    assert ID(id=5, type=Type.Individual).type == Type.Individual
    assert ID(id=5, type=Type.AnonUser).type == Type.AnonUser


def test_kwarg_universe() -> None:
    with pytest.raises(InvalidID):
        ID(id=5, universe="doesn't exist")  # type: ignore
    with pytest.raises(InvalidID):
        ID(id=5, universe=99999999)  # type: ignore

    assert ID(id=5, universe=Universe.Public).universe == Universe.Public
    assert ID(id=5, universe=Universe.Dev).universe == Universe.Dev


def test_kwarg_instance() -> None:
    assert ID(id=5, instance=InstanceFlag.Console).instance == InstanceFlag.Console

    for type in Type:
        assert (
            ID(id=5, type=type).instance == InstanceFlag.Desktop
            if type in (Type.Individual, Type.GameServer)
            else ID(id=5, type=type).instance == InstanceFlag.All
        )


def test_out_of_current_bounds() -> None:
    with pytest.raises(InvalidID):
        ID(5, type=Type.try_value(1 << 4 + 1))
    with pytest.raises(InvalidID):
        ID(5, universe=Universe.try_value(1 << 8 + 1))
    with pytest.raises(InvalidID):
        ID(5, instance=InstanceFlag.try_value(1 << 20 + 1))


@pytest.mark.parametrize(
    "steam_id, valid",
    [
        [ID(0), False],
        [ID(1), True],
        [ID(2**64 - 1), False],  # everything out of current bound
        [ID(1, type=Type.Invalid), False],  # type out of bound
        [ID(1, universe=Universe.Invalid), False],
        [ID(1, universe=Universe.Max), False],  # universe out of bound
        [ID(5), True],
        # individual
        [ID(123, Type.Individual, Universe.Public, instance=InstanceFlag.All), True],
        [ID(123, Type.Individual, Universe.Public, instance=InstanceFlag.Desktop), True],
        [ID(123, Type.Individual, Universe.Public, instance=InstanceFlag.Console), True],
        [ID(123, Type.Individual, Universe.Public, instance=InstanceFlag.Web), True],
        # clan
        [ID(1, Type.Clan, Universe.Public, instance=InstanceFlag.Desktop), False],
        [ID(1, Type.Clan, Universe.Public, instance=InstanceFlag.All), True],
    ],
)
def test_is_valid(steam_id: ID, valid: bool) -> None:
    assert steam_id.is_valid() is valid


def test_dunders() -> None:
    assert ID(5) == ID(5)
    assert ID(10) != ID(5)
    assert hash(ID(5)) == hash(ID(5))
    assert str(ID(76580280500085312)) == "76580280500085312"
    assert eval(repr(ID(76561210845291072))) == ID(76561210845291072)


@pytest.mark.parametrize(
    "steam_id, id2",
    [
        [ID("STEAM_0:1:4"), "STEAM_1:1:4"],
        [ID("STEAM_1:1:4"), "STEAM_1:1:4"],
        [ID("STEAM_0:0:4"), "STEAM_1:0:4"],
        [ID("STEAM_1:0:4"), "STEAM_1:0:4"],
    ],
)
def test_as_id2(steam_id: ID, id2: str) -> None:
    assert steam_id.id2 == id2


@pytest.mark.parametrize(
    "steam_id, id2_zero",
    [
        [ID("STEAM_0:1:4"), "STEAM_0:1:4"],
        [ID("STEAM_1:1:4"), "STEAM_0:1:4"],
        [ID("STEAM_0:0:4"), "STEAM_0:0:4"],
        [ID("STEAM_1:0:4"), "STEAM_0:0:4"],
        [ID("STEAM_4:0:4"), "STEAM_4:0:4"],
        [ID("STEAM_4:1:4"), "STEAM_4:1:4"],
    ],
)
def test_as_id2_zero(steam_id: ID, id2_zero: str) -> None:
    assert steam_id.id2_zero == id2_zero


@pytest.mark.parametrize(
    "steam_id, id3",
    [
        [ID("[U:1:1234]"), "[U:1:1234:0]"],
        [ID("[U:1:1234]"), "[U:1:1234:0]"],
        [ID("[U:1:1234:56]"), "[U:1:1234:56]"],
        [ID("[g:1:4]"), "[g:1:4]"],
        [ID("[A:1:1234:567]"), "[A:1:1234:567]"],
        [ID("[G:1:1234:567]"), "[G:1:1234]"],
        [ID("[T:1:1234]"), "[T:1:1234]"],
        [ID("[c:1:1234]"), "[g:1:1234]"],
        [ID("[L:1:1234]"), "[L:1:1234]"],
    ],
)
def test_as_steam3(steam_id: ID, id3: str) -> None:
    assert steam_id.id3 == id3


@pytest.mark.parametrize(
    "steam_id, community_url",
    [
        [ID(76580280500085312), "https://steamcommunity.com/profiles/76580280500085312"],  # user url
        [ID("[g:1:4]"), "https://steamcommunity.com/gid/103582791429521412"],  # group url
        [ID("[A:1:4]"), None],  # else None
    ],
)
def test_community_url(steam_id: ID, community_url: Optional[str]) -> None:
    assert steam_id.community_url == community_url


@pytest.mark.parametrize(
    "steam_id, invite_code",
    [
        [ID(0, Type.Individual, Universe.Public, instance=InstanceFlag.Desktop), None],
        [ID(123456, Type.Individual, Universe.Public, instance=InstanceFlag.Desktop), "cv-dgb"],
        [ID(123456, Type.Individual, Universe.Beta, instance=InstanceFlag.Desktop), "cv-dgb"],
        [ID(123456, Type.Invalid, Universe.Public, instance=InstanceFlag.Desktop), None],
        [ID(123456, Type.Clan, Universe.Public, instance=InstanceFlag.Desktop), None],
    ],
)
def test_as_invite_code(steam_id: ID, invite_code: Optional[str]) -> None:
    assert steam_id.invite_code == invite_code


@pytest.mark.parametrize(
    "steam_id, invite_url",
    [
        [ID(0, Type.Individual, Universe.Public, instance=InstanceFlag.Desktop), None],
        [ID(123456, Type.Individual, Universe.Public, instance=InstanceFlag.Desktop), "https://s.team/p/cv-dgb"],
        [ID(123456, Type.Individual, Universe.Beta, instance=InstanceFlag.Desktop), "https://s.team/p/cv-dgb"],
        [ID(123456, Type.Invalid, Universe.Public, instance=InstanceFlag.Desktop), None],
        [ID(123456, Type.Clan, Universe.Public, instance=InstanceFlag.Desktop), None],
    ],
)
def test_as_invite_url(steam_id: ID, invite_url: Optional[str]) -> None:
    assert steam_id.invite_url == invite_url
