# pyright: reportUnnecessaryTypeIgnoreComment=false
"""
Various constants/types for use around the library.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import builtins
import importlib.util
import struct
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from io import BytesIO, StringIO
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, TypeAlias, TypeVar, cast, final

from multidict import MultiDict
from yarl import URL as _URL

from .types.vdf import BinaryVDFDict, VDFDict

if TYPE_CHECKING:
    from typing_extensions import Buffer

    from .clan import Clan
    from .group import Group
    from .state import ConnectionState

DOCS_BUILDING: bool = getattr(builtins, "__sphinx__", False)

HAS_ORJSON = False
try:
    import orjson  # type: ignore
except ModuleNotFoundError:
    import json

    json_loads = json.loads

    @partial(cast, Callable[[Any], str])
    def json_dumps(
        obj: Any,
        __func: Callable[..., str] = json.dumps,
        /,
    ) -> str:
        return __func(obj, separators=(",", ":"), ensure_ascii=True)

else:
    json_loads = orjson.loads

    @partial(cast, Callable[[Any], str])
    def json_dumps(
        obj: Any,
        __func: Callable[[Any], bytes] = orjson.dumps,  # type: ignore
        __decoder: Callable[[bytes], str] = bytes.decode,
        /,
    ) -> str:
        return __decoder(__func(obj))


JSON_LOADS: Final = cast(Callable[[str | bytes], Any], json_loads)
JSON_DUMPS: Final = json_dumps


try:
    import orvdf  # type: ignore
except ModuleNotFoundError:
    import vdf

    def _multi_dict_ify(
        x: Any,
        __isinstance=isinstance,  # type: ignore
        __vdf_dict=vdf.VDFDict,
        __multi_dict: type[MultiDict[Any]] = MultiDict,
        /,
    ):
        if __isinstance(x, __vdf_dict):
            multi_dict = __multi_dict()
            adder = multi_dict.add
            for k, v in x.items():
                adder(k, _multi_dict_ify(v))
            return multi_dict
        return x

    def vdf_loads(
        s: str,
        __func: Callable[..., Any] = vdf.parse,  # type: ignore
        __mapper: type[vdf.VDFDict] = vdf.VDFDict,
        __multi_dict_ify: Callable[[vdf.VDFDict], MultiDict[Any]] = _multi_dict_ify,
        __string_io: type[StringIO] = StringIO,
        /,
    ) -> VDFDict:
        return __multi_dict_ify(__func(__string_io(s), mapper=__mapper))

    def vdf_binary_loads(
        s: bytes,
        __func: Callable[..., Any] = vdf.binary_load,  # type: ignore
        __mapper: type[vdf.VDFDict] = vdf.VDFDict,
        __multi_dict_ify: Callable[[vdf.VDFDict], MultiDict[Any]] = _multi_dict_ify,
        __bytes_io: type[BytesIO] = BytesIO,
        /,
    ) -> BinaryVDFDict:
        return __multi_dict_ify(__func(__bytes_io(s), mapper=__mapper))

else:
    vdf_loads = orvdf.loads  # type: ignore
    vdf_binary_loads = orvdf.binary_loads  # type: ignore

VDF_LOADS: Final = cast(Callable[[str], VDFDict], vdf_loads)
VDF_BINARY_LOADS: Final = cast(Callable[[bytes], BinaryVDFDict], vdf_binary_loads)

HTML_PARSER: Final = "lxml-xml" if importlib.util.find_spec("lxml") else "html.parser"

try:
    from asyncio import TaskGroup as TaskGroup, timeout as timeout  # type: ignore
except ImportError:
    from taskgroup import TaskGroup as TaskGroup, timeout as timeout  # type: ignore


UNIX_EPOCH: Final = datetime(1970, 1, 1, tzinfo=timezone.utc)
STEAM_EPOCH: Final = datetime(2003, 1, 1, tzinfo=timezone.utc)


def READ_U32(
    s: Buffer, unpacker: Callable[[Buffer], tuple[int]] = cast(Any, struct.Struct("<I").unpack_from), /
) -> int:
    (u32,) = unpacker(s)
    return u32


WRITE_U32: Final = cast(Callable[[int], bytes], struct.Struct("<I").pack)

_PROTOBUF_MASK: Final = 0x80000000
# inlined as these are some of the most called functions in the library
IS_PROTO: Final = cast(Callable[[int], bool], _PROTOBUF_MASK.__and__)  # this is boolean like for a bit of extra speed
SET_PROTO_BIT: Final = _PROTOBUF_MASK.__or__
CLEAR_PROTO_BIT: Final = (~_PROTOBUF_MASK).__and__

STATE = ContextVar["ConnectionState"]("APP_STATE")


@final
class MissingSentinel(Any if TYPE_CHECKING else object):
    __slots__ = ()

    def __eq__(self, other: object) -> Literal[False]:
        return False

    def __bool__(self) -> Literal[False]:
        return False

    def __hash__(self) -> Literal[0]:
        return 0

    def __repr__(self) -> Literal["..."]:
        return "..."


MISSING: Final = MissingSentinel()


@final
class URL:
    API: Final = _URL("https://api.steampowered.com")
    COMMUNITY: Final = _URL("https://steamcommunity.com")
    STORE: Final = _URL("https://store.steampowered.com")
    HELP: Final = _URL("https://help.steampowered.com")
    LOGIN: Final = _URL("https://login.steampowered.com")
    CDN: Final = _URL("https://cdn.cloudflare.steamstatic.com")
    PUBLISHER_API: Final = _URL("https://partner.steam-api.com")


DEFAULT_AVATAR: Final = b"\xfe\xf4\x9e\x7f\xa7\xe1\x99s\x10\xd7\x05\xb2\xa6\x15\x8f\xf8\xdc\x1c\xdf\xeb"


class _IDComparable(Protocol):
    @property
    def id(self) -> Any:
        ...


_TT_IDComp = TypeVar("_TT_IDComp", bound=type[_IDComparable])


def impl_eq_via_id(cls: _TT_IDComp) -> _TT_IDComp:
    def __eq__(self: _IDComparable, other: object, /) -> bool:
        return isinstance(other, cls) and self.id == other.id  # type: ignore

    def __hash__(self: _IDComparable) -> int:
        return hash(self.id)

    cls.__eq__ = __eq__
    cls.__hash__ = __hash__
    return cls


class _HasChatGroupMixin(Protocol):
    __slots__ = ()
    clan: Clan | None
    group: Group | None

    @property
    def _chat_group(self) -> Clan | Group:
        chat_group = self.clan or self.group
        assert chat_group is not None
        return chat_group


T_co = TypeVar("T_co", covariant=True)


class _ReadOnlyProto(Protocol[T_co]):
    def __get__(self, __instance: Any, __owner: type) -> T_co:
        ...


ReadOnly: TypeAlias = T_co | _ReadOnlyProto[T_co]
"""PEP 705 style read only, should make things a easier transition when the feature gets added to nominal classes.

Currently does not mean anything to a type checker really.
"""


@dataclass(frozen=True, slots=True)
class SteamBadge:
    name: str
    id: int
    url: str
    level: float = 1


STEAM_BADGES = (
    SteamBadge(
        "Years of Service",
        1,
        "https://community.cloudflare.steamstatic.com/public/images/badges/02_years/steamyears20_80.png",
        20,
    ),
    SteamBadge(
        "Community Ambassador",
        2,
        "https://community.cloudflare.steamstatic.com/public/images/badges/01_community/community03_80.png",
        3,
    ),
    SteamBadge(
        "The Potato Sack",
        3,
        "https://community.cloudflare.steamstatic.com/public/images/badges/03_potato/potato03_80.png",
        36,
    ),
    SteamBadge(
        "The Great Steam Treasure Hunt",
        4,
        "https://community.cloudflare.steamstatic.com/public/images/badges/04_treasurehunt/treasurehunt03_80.png",
        3,
    ),
    SteamBadge(
        "Steam Summer Camp",
        5,
        "https://community.cloudflare.steamstatic.com/public/images/badges/05_summer2011/tickets80.png",
        76,
    ),
    SteamBadge(
        "Steam Holiday Sale 2011",
        6,
        "https://community.cloudflare.steamstatic.com/public/images/badges/06_winter2011/coal03_80.png",
        78,
    ),
    SteamBadge(
        "Steam Summer Sale 2012",
        7,
        "https://community.cloudflare.steamstatic.com/public/images/badges/07_summer2012/Summer2012_stage3_80.png",
        3,
    ),
    SteamBadge(
        "Steam Holiday Sale 2012",
        8,
        "https://community.cloudflare.steamstatic.com/public/images/badges/08_winter2012/winter2012_badge80.png",
    ),
    SteamBadge(
        "Steam Community Translator",
        9,
        "https://community.cloudflare.steamstatic.com/public/images/badges/09_communitytranslator/translator_level4_80.png",
        4,
    ),
    SteamBadge(
        "Steam Community Moderator",
        10,
        "https://community.cloudflare.steamstatic.com/public/images/badges/generic/CommunityModerator_80.png",
    ),
    SteamBadge(
        "Valve Employee",
        11,
        "https://community.cloudflare.steamstatic.com/public/images/badges/generic/ValveEmployee_80.png",
    ),
    SteamBadge(
        "Steamworks Developer",
        12,
        "https://community.cloudflare.steamstatic.com/public/images/badges/generic/GameDeveloper_80.png",
    ),
    SteamBadge(
        "Owned Games",
        13,
        "https://community.cloudflare.steamstatic.com/public/images/badges/13_gamecollector/30000_80.png?v=4",
        float("inf"),
    ),
    SteamBadge(
        "Trading Card Beta Tester",
        14,
        "https://community.cloudflare.steamstatic.com/public/images/badges/generic/TradingCardBeta_80.png",
    ),
    SteamBadge(
        "Steam Hardware Beta",
        15,
        "https://community.cloudflare.steamstatic.com/public/images/badges/15_hwbeta/hwbeta03_80.png",
        3,
    ),
    SteamBadge(
        "Red Team",
        16,
        "https://community.cloudflare.steamstatic.com/public/images/badges/16_summer2014/team_red.png",
        float("inf"),
    ),
    SteamBadge(
        "Blue Team",
        17,
        "https://community.cloudflare.steamstatic.com/public/images/badges/16_summer2014/team_blue.png",
        float("inf"),
    ),
    SteamBadge(
        "Pink Team",
        18,
        "https://community.cloudflare.steamstatic.com/public/images/badges/16_summer2014/team_pink.png",
        float("inf"),
    ),
    SteamBadge(
        "Green Team",
        19,
        "https://community.cloudflare.steamstatic.com/public/images/badges/16_summer2014/team_green.png",
        float("inf"),
    ),
    SteamBadge(
        "Purple Team",
        20,
        "https://community.cloudflare.steamstatic.com/public/images/badges/16_summer2014/team_purple.png",
        float("inf"),
    ),
    SteamBadge(
        "Auction Participant/Winner",
        21,
        "https://community.cloudflare.steamstatic.com/public/images/badges/21_auction/winner_80.png?v=2",
        3,
    ),
    SteamBadge(
        "2014 Holiday Profile Recipient",
        22,
        "https://community.cloudflare.steamstatic.com/public/images/badges/22_golden/owner_80.png",
    ),
    SteamBadge(
        "Monster Summer",
        23,
        "https://community.cloudflare.steamstatic.com/public/images/badges/23_towerattack/wormhole.png",
        100_000_000,
    ),
    SteamBadge(
        "Red Herring",
        24,
        "https://community.cloudflare.steamstatic.com/public/images/badges/24_winter2015_arg_red_herring/red_herring.png",
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2016",
        25,
        "https://community.cloudflare.steamstatic.com/public/images/badges/25_steamawardnominations/level04_80.png",
        4,
    ),
    SteamBadge(
        "Sticker Completionist",
        26,
        "https://community.cloudflare.steamstatic.com/public/images/badges/26_summer2017_sticker/completionist.png",
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2017",
        27,
        "https://community.cloudflare.steamstatic.com/public/images/badges/27_steamawardnominations/level04_80.png",
        4,
    ),
    SteamBadge(
        "Spring Cleaning Event 2018",
        28,
        "https://community.cloudflare.steamstatic.com/public/images/badges/28_springcleaning2018/gold_80.png",
        3,
    ),
    SteamBadge(
        "Salien", 29, "https://community.cloudflare.steamstatic.com/public/images/badges/29_salien/6_80.png", 29
    ),
    SteamBadge(
        "Retired Community Moderator",
        30,
        "https://community.cloudflare.steamstatic.com/public/images/badges/generic/RetiredModerator_80.png",
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2018",
        31,
        "https://community.cloudflare.steamstatic.com/public/images/badges/30_steamawardnominations/level04_80.png",
        4,
    ),
    SteamBadge(
        "Winter 2018 Knick-Knack Collector",
        33,
        "https://community.cloudflare.steamstatic.com/public/images/badges/33_cozycottage2018/1000000_80.png",
        float("inf"),
    ),
    SteamBadge(
        "Lunar New Year 2019",
        34,
        "https://community.cloudflare.steamstatic.com/public/images/badges/34_lny2019/10_80.png",
        10,
    ),
    SteamBadge(
        "Spring Cleaning Event 2019",
        36,
        "https://community.cloudflare.steamstatic.com/public/images/badges/36_springcleaning2019/gold_80x80.png",
        3,
    ),
    SteamBadge(
        "Steam Grand Prix 2019",
        37,
        "https://community.cloudflare.steamstatic.com/public/images/badges/37_summer2019/level1000000_80.png",
        float("inf"),
    ),
    SteamBadge(
        "Team Hare",
        38,
        "https://community.cloudflare.steamstatic.com/public/images/badges/37_summer2019/hare_gold_80.png",
    ),
    SteamBadge(
        "Team Tortoise",
        39,
        "https://community.cloudflare.steamstatic.com/public/images/badges/37_summer2019/tortoise_gold_80.png",
    ),
    SteamBadge(
        "Team Corgi",
        40,
        "https://community.cloudflare.steamstatic.com/public/images/badges/37_summer2019/corgi_gold_80.png",
    ),
    SteamBadge(
        "Team Cockatiel",
        41,
        "https://community.cloudflare.steamstatic.com/public/images/badges/37_summer2019/cockatiel_gold_80.png",
    ),
    SteamBadge(
        "Team Pig",
        42,
        "https://community.cloudflare.steamstatic.com/public/images/badges/37_summer2019/pig_gold_80.png",
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2019",
        43,
        "https://community.cloudflare.steamstatic.com/public/images/badges/43_steamawardnominations/level04_80.png",
        4,
    ),
    SteamBadge(
        "Steam Winter Sale 2019",
        44,
        "https://community.cloudflare.steamstatic.com/public/images/badges/44_winter2019/level15_80.png",
        15,
    ),
    SteamBadge(
        "Steamville 2019 Badge",
        45,
        "https://community.cloudflare.steamstatic.com/public/images/badges/45_steamville2019/key_to_city_80.png",
    ),
    SteamBadge(
        "Lunar New Year 2020",
        46,
        "https://community.cloudflare.steamstatic.com/public/images/badges/46_lny2020/10_80.png",
        10,
    ),
    SteamBadge(
        "Spring Cleaning Event 2020",
        47,
        "https://community.cloudflare.steamstatic.com/public/images/badges/47_springcleaning2020/dewey_badge_3.0_80x80.png",
        3,
    ),
    SteamBadge(
        "Community Contributor",
        48,
        "https://community.cloudflare.steamstatic.com/public/images/badges/48_communitycontributor/1_80.png",
        float("inf"),
    ),
    SteamBadge(
        "Community Patron",
        49,
        "https://community.cloudflare.steamstatic.com/public/images/badges/49_communitypatron/1_80.png",
        float("inf"),
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2020",
        50,
        "https://community.cloudflare.steamstatic.com/public/images/badges/50_steamawardnominations/level04_184.png",
        4,
    ),
    SteamBadge(
        "The Masked Avenger",
        51,
        "https://community.cloudflare.steamstatic.com/public/images/badges/51_summer2021/51.png",
    ),
    SteamBadge(
        "The Trailblazing Explorer",
        52,
        "https://community.cloudflare.steamstatic.com/public/images/badges/51_summer2021/52.png",
    ),
    SteamBadge(
        "The Gorilla Scientist",
        53,
        "https://community.cloudflare.steamstatic.com/public/images/badges/51_summer2021/53.png",
    ),
    SteamBadge(
        "The Paranormal Professor",
        54,
        "https://community.cloudflare.steamstatic.com/public/images/badges/51_summer2021/54.png",
    ),
    SteamBadge(
        "The Ghost Detective",
        55,
        "https://community.cloudflare.steamstatic.com/public/images/badges/51_summer2021/55.png",
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2021",
        56,
        "https://community.cloudflare.steamstatic.com/public/images/badges/56_steamawardnominations/level04_80.png",
        4,
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2021 Classic Edition",
        57,
        "https://community.cloudflare.steamstatic.com/public/images/badges/57_steamawardnominationsclassic/2021_nomination_classic_level04.png",
        4,
    ),
    SteamBadge(
        "2022 Steam Cup",
        59,
        "https://community.cloudflare.steamstatic.com/public/images/badges/generic/RacingSale2022_80.png",
    ),
    SteamBadge(
        "2022 Steam Next Fest June Edition",
        60,
        "https://community.cloudflare.steamstatic.com/public/images/badges/60_nextfestsummer2022/160/badge_3.png",
        1056,
    ),
    SteamBadge(
        "Clorthax's Paradox Party Badge",
        61,
        "https://community.cloudflare.steamstatic.com/public/images/badges/61_summersale_minigame2022/80/badge_clorthax_3.png?t=7337941",
        10,
    ),
    SteamBadge(
        "2022 Steam Next Fest October Edition",
        62,
        "https://community.cloudflare.steamstatic.com/public/images/badges/62_nextfestautumn2022/160/badge_3.png",
        6,
    ),
    SteamBadge(
        "Steam Awards Nomination Committee 2022",
        63,
        "https://community.cloudflare.steamstatic.com/public/images/badges/63_steamawardnominations/level04_80.png",
        4,
    ),
    SteamBadge(
        "Steam Replay 2022",
        64,
        "https://community.akamai.steamstatic.com/public/images/badges/generic/Replay2022_80.png",
    ),
)


# default CMs if Steam API is down
DEFAULT_CMS: Final = (
    "ext1-ams1.steamserver.net:27019",
    "ext1-ams1.steamserver.net:27022",
    "ext1-ams1.steamserver.net:27023",
    "ext1-ams1.steamserver.net:27024",
    "ext1-ams1.steamserver.net:27025",
    "ext1-ams1.steamserver.net:27029",
    "ext1-ams1.steamserver.net:27033",
    "ext1-ams1.steamserver.net:27035",
    "ext1-ams1.steamserver.net:27038",
    "ext1-ams1.steamserver.net:443",
    "ext1-fra1.steamserver.net:27020",
    "ext1-fra1.steamserver.net:27022",
    "ext1-fra1.steamserver.net:27023",
    "ext1-fra1.steamserver.net:27024",
    "ext1-fra1.steamserver.net:27025",
    "ext1-fra1.steamserver.net:27030",
    "ext1-fra1.steamserver.net:27031",
    "ext1-fra1.steamserver.net:27032",
    "ext1-fra1.steamserver.net:27034",
    "ext1-fra1.steamserver.net:27037",
    "ext1-fra1.steamserver.net:27038",
    "ext1-fra1.steamserver.net:443",
    "ext1-lhr1.steamserver.net:27020",
    "ext1-lhr1.steamserver.net:27021",
    "ext1-lhr1.steamserver.net:27025",
    "ext1-lhr1.steamserver.net:27029",
    "ext1-lhr1.steamserver.net:27030",
    "ext1-lhr1.steamserver.net:27032",
    "ext1-lhr1.steamserver.net:27034",
    "ext1-lhr1.steamserver.net:27036",
    "ext1-lhr1.steamserver.net:27038",
    "ext1-lhr1.steamserver.net:443",
    "ext1-par1.steamserver.net:27019",
    "ext1-par1.steamserver.net:27020",
    "ext1-par1.steamserver.net:27021",
    "ext1-par1.steamserver.net:27022",
    "ext1-par1.steamserver.net:27023",
    "ext1-par1.steamserver.net:27024",
    "ext1-par1.steamserver.net:27025",
    "ext1-par1.steamserver.net:27029",
    "ext1-par1.steamserver.net:27031",
    "ext1-par1.steamserver.net:27033",
    "ext1-par1.steamserver.net:27035",
    "ext1-par1.steamserver.net:27036",
    "ext1-par1.steamserver.net:443",
    "ext2-ams1.steamserver.net:27020",
    "ext2-ams1.steamserver.net:27022",
    "ext2-ams1.steamserver.net:27023",
    "ext2-ams1.steamserver.net:27025",
    "ext2-ams1.steamserver.net:27028",
    "ext2-ams1.steamserver.net:27029",
    "ext2-ams1.steamserver.net:27030",
    "ext2-ams1.steamserver.net:27032",
    "ext2-ams1.steamserver.net:27033",
    "ext2-ams1.steamserver.net:27038",
    "ext2-ams1.steamserver.net:443",
    "ext2-fra1.steamserver.net:27032",
    "ext2-fra1.steamserver.net:27036",
    "ext2-lhr1.steamserver.net:27030",
    "ext2-lhr1.steamserver.net:27033",
    "ext2-lhr1.steamserver.net:443",
    "ext2-par1.steamserver.net:27019",
    "ext2-par1.steamserver.net:27021",
    "ext2-par1.steamserver.net:27023",
    "ext2-par1.steamserver.net:27029",
    "ext2-par1.steamserver.net:27030",
    "ext2-par1.steamserver.net:27031",
    "ext2-par1.steamserver.net:27033",
    "ext2-par1.steamserver.net:27038",
    "ext2-par1.steamserver.net:443",
    "ext3-lhr1.steamserver.net:27020",
    "ext3-lhr1.steamserver.net:27025",
    "ext3-lhr1.steamserver.net:27030",
    "ext3-lhr1.steamserver.net:27038",
    "ext3-lhr1.steamserver.net:443",
    "ext4-lhr1.steamserver.net:27022",
    "ext4-lhr1.steamserver.net:27029",
    "ext4-lhr1.steamserver.net:27031",
    "ext4-lhr1.steamserver.net:27036",
    "ext4-lhr1.steamserver.net:443",
)
