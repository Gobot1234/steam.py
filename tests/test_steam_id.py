# -*- coding: utf-8 -*-

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

from typing import List

import pytest
from steam import SteamID, EType, EUniverse


def create_id64(id: int, type: int, universe: int, instance: int) -> int:
    return (universe << 56) | (type << 52) | (instance << 32) | id


def compare(steam_id: SteamID, test_list: List[int]) -> None:
    assert steam_id.id == test_list[0]
    assert steam_id.type == test_list[1]
    assert steam_id.universe == test_list[2]
    assert steam_id.instance == test_list[3]


def test_hash():
    assert hash(SteamID(1)) == hash(SteamID(1))
    assert SteamID(12345) != hash(SteamID(8888))


def test_arg_too_many_invalid():
    with pytest.raises(TypeError):
        SteamID(1, 2, 3, 4, 5)
    with pytest.raises(TypeError):
        SteamID(1, 2, 3, 4, 5, 6)


def test_args_only():
    compare(SteamID(1, 2), [1, 2, 1, 0])
    compare(SteamID(1, 2, 3), [1, 2, 3, 0])
    compare(SteamID(1, 2, 3, 4), [1, 2, 3, 4])


def test_from_id():
    compare(SteamID(1), [1, EType.Individual, EUniverse.Public, 1])
    compare(SteamID("1"), [1, EType.Individual, EUniverse.Public, 1])
    compare(SteamID(12), [12, EType.Individual, EUniverse.Public, 1])
    compare(SteamID("12"), [12, EType.Individual, EUniverse.Public, 1])
    compare(SteamID(123), [123, EType.Individual, EUniverse.Public, 1])
    compare(SteamID("123"), [123, EType.Individual, EUniverse.Public, 1])
    compare(SteamID(12345678), [12345678, EType.Individual, EUniverse.Public, 1])
    compare(SteamID("12345678"), [12345678, EType.Individual, EUniverse.Public, 1])
    compare(SteamID(0xFFFFFFFF), [0xFFFFFFFF, EType.Individual, EUniverse.Public, 1])
    compare(SteamID(str(0xFFFFFFFF)), [0xFFFFFFFF, EType.Individual, EUniverse.Public, 1])


def test_arg_steam64():
    compare(SteamID(76580280500085312), [123456, EType.Individual, EUniverse.Public, 4444])
    compare(SteamID("76580280500085312"), [123456, EType.Individual, EUniverse.Public, 4444])
    compare(SteamID(103582791429521412), [4, EType.Clan, EUniverse.Public, 0])
    compare(SteamID("103582791429521412"), [4, EType.Clan, EUniverse.Public, 0])


def test_arg_steam64_invalid_universe():
    with pytest.raises(ValueError):
        SteamID(create_id64(1, 1, 255, 1))


def test_arg_steam64_invalid_type():
    with pytest.raises(ValueError):
        SteamID(create_id64(1, 15, 1, 1))


def test_arg_text_invalid():
    with pytest.raises(ValueError):
        SteamID("invalid_format")


def test_arg_too_large_invalid():
    with pytest.raises(ValueError):
        SteamID(111111111111111111111111111111111111111)
        SteamID("1111111111111111111111111111111111111")


def test_too_small():
    with pytest.raises(ValueError):
        SteamID(-50)
        SteamID(id=-50)


def test_kwarg_id():
    assert SteamID(id=555).id == 555
    assert SteamID(id="555").id == 555


def test_kwarg_type():
    with pytest.raises(KeyError):
        SteamID(id=5, type="doesn't exist")
    with pytest.raises(KeyError):
        SteamID(id=5, type=99999999)

    assert SteamID(id=5, type=1).type == EType.Individual
    assert SteamID(id=5, type="Individual").type == EType.Individual
    assert SteamID(id=5, type="AnonUser").type == EType.AnonUser


def test_kwarg_universe():
    with pytest.raises(KeyError):
        SteamID(id=5, universe="doesn't exist")
    with pytest.raises(KeyError):
        SteamID(id=5, universe=99999999)

    assert SteamID(id=5, universe=1).universe == EUniverse.Public
    assert SteamID(id=5, universe="Public").universe == EUniverse.Public
    assert SteamID(id=5, universe="Dev").universe == EUniverse.Dev


def test_kwarg_instance():
    assert SteamID(id=5, instance=1234).instance == 1234

    for type in EType:
        assert (
            SteamID(id=5, type=type).instance == 1
            if type in (EType.Individual, EType.GameServer)
            else SteamID(id=5, type=type).instance == 0
        )


def test_kwargs_invalid():
    invalid = [0, EType.Invalid, EUniverse.Invalid, 0]

    compare(SteamID(), invalid)
    compare(SteamID(id=0, type=0, universe=0, instance=0), invalid)
    compare(SteamID(id=0, type=EType.Invalid, universe=EUniverse.Invalid, instance=0,), invalid)
    compare(SteamID(id=0, type="Invalid", universe="Invalid", instance=0,), invalid)


def test_is_valid():
    assert SteamID(1).is_valid()
    assert SteamID(id=5).is_valid()

    assert not SteamID(0).is_valid()

    assert not SteamID(id=1, type=EType.Invalid).is_valid()
    assert not SteamID(id=1, universe=EUniverse.Invalid).is_valid()
    # default
    assert not SteamID().is_valid()
    # id = 0
    assert not SteamID(0).is_valid()
    assert not SteamID(id=0).is_valid()
    # id > 0
    assert SteamID(5).is_valid()
    # type out of bound
    assert not SteamID(1, EType.Max).is_valid()
    # universe out of bound
    assert not SteamID(1, universe=EUniverse.Max).is_valid()
    # individual
    assert SteamID(123, EType.Individual, EUniverse.Public, instance=0).is_valid()
    assert SteamID(123, EType.Individual, EUniverse.Public, instance=1).is_valid()
    assert SteamID(123, EType.Individual, EUniverse.Public, instance=2).is_valid()
    assert SteamID(123, EType.Individual, EUniverse.Public, instance=3).is_valid()
    assert SteamID(123, EType.Individual, EUniverse.Public, instance=4).is_valid()
    assert not SteamID(123, EType.Individual, EUniverse.Public, instance=5).is_valid()
    assert not SteamID(123, EType.Individual, EUniverse.Public, instance=333).is_valid()
    # clan
    assert SteamID(1, EType.Clan, EUniverse.Public, instance=0).is_valid()
    assert not SteamID(1, EType.Clan, EUniverse.Public, instance=1).is_valid()
    assert not SteamID(1, EType.Clan, EUniverse.Public, instance=1234).is_valid()

    s = SteamID(123, type=EType.Clan, universe=EUniverse.Public, instance=333)
    assert not s.is_valid()


def test_dunders():
    assert not SteamID(10) == SteamID(5)
    assert SteamID(10) != SteamID(5)
    assert hash(SteamID(5)) == hash(SteamID(5))
    assert str(SteamID(76580280500085312)) == "76580280500085312"
    assert eval(repr(SteamID(76580280500085312))) == SteamID(76580280500085312)


def test_as_steam2():
    assert SteamID("STEAM_0:1:4").id2 == "STEAM_1:1:4"
    assert SteamID("STEAM_1:1:4").id2 == "STEAM_1:1:4"
    assert SteamID("STEAM_0:0:4").id2 == "STEAM_1:0:4"
    assert SteamID("STEAM_1:0:4").id2 == "STEAM_1:0:4"

    assert SteamID("STEAM_4:0:4").id2 == "STEAM_4:0:4"
    assert SteamID("STEAM_4:1:4").id2 == "STEAM_4:1:4"


def test_as_steam2_zero():
    assert SteamID("STEAM_0:1:4").id2_zero == "STEAM_0:1:4"
    assert SteamID("STEAM_1:1:4").id2_zero == "STEAM_0:1:4"
    assert SteamID("STEAM_0:0:4").id2_zero == "STEAM_0:0:4"
    assert SteamID("STEAM_1:0:4").id2_zero == "STEAM_0:0:4"

    assert SteamID("STEAM_4:0:4").id2_zero == "STEAM_4:0:4"
    assert SteamID("STEAM_4:1:4").id2_zero == "STEAM_4:1:4"


def test_as_steam3():
    assert SteamID("[U:1:1234]").id3, "[U:1:1234]"
    assert SteamID("[U:1:1234:56]").id3, "[U:1:1234:56]"
    assert SteamID("[g:1:4]").id3, "[g:1:4]"
    assert SteamID("[A:1:1234:567]").id3 == "[A:1:1234:567]"
    assert SteamID("[G:1:1234:567]").id3 == "[G:1:1234]"
    assert SteamID("[T:1:1234]").id3 == "[T:1:1234]"
    assert SteamID("[c:1:1234]").id3 == "[g:1:1234]"
    assert SteamID("[L:1:1234]").id3 == "[L:1:1234]"


def test_as_32():
    assert SteamID(76580280500085312).id == 123456


def test_as_64():
    assert SteamID(76580280500085312).id64 == 76580280500085312


def test_community_url():
    # user url
    assert SteamID(76580280500085312).community_url == "https://steamcommunity.com/profiles/76580280500085312"
    # group url
    assert SteamID("[g:1:4]").community_url == "https://steamcommunity.com/gid/103582791429521412"
    # else None
    assert SteamID("[A:1:4]").community_url is None


def test_as_invite_code():
    assert SteamID(0, EType.Individual, EUniverse.Public, instance=1).invite_code is None
    assert SteamID(123456, EType.Individual, EUniverse.Public, instance=1).invite_code == "cv-dgb"
    assert SteamID(123456, EType.Individual, EUniverse.Beta, instance=1).invite_code == "cv-dgb"
    assert SteamID(123456, EType.Invalid, EUniverse.Public, instance=1).invite_code is None
    assert SteamID(123456, EType.Clan, EUniverse.Public, instance=1).invite_code is None


def test_as_invite_url():
    assert SteamID(0, EType.Individual, EUniverse.Public, instance=1).invite_url is None
    assert SteamID(123456, EType.Individual, EUniverse.Public, instance=1).invite_url == "https://s.team/p/cv-dgb"
    assert SteamID(123456, EType.Individual, EUniverse.Beta, instance=1).invite_url == "https://s.team/p/cv-dgb"
    assert SteamID(123456, EType.Invalid, EUniverse.Public, instance=1).invite_url is None
    assert SteamID(123456, EType.Clan, EUniverse.Public, instance=1).invite_url is None
