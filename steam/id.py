"""
Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE

Contains large portions of:
https://github.com/ValvePython/steam/blob/master/steam/steamid.py
The appropriate licenses are in LICENSE
"""

from __future__ import annotations

import abc
import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, Literal

import aiohttp

from ._const import MISSING
from .enums import InstanceFlag, Type, TypeChar, Universe
from .errors import InvalidID
from .types.id import ID32, ID64, Intable

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from .types.http import StrOrURL


__all__ = ("ID",)


def parse_id64(
    id: Intable,
    *,
    type: Type = MISSING,
    universe: Universe = MISSING,
    instance: InstanceFlag = MISSING,
) -> ID64:
    """Convert various representations of Steam IDs to its Steam 64-bit ID.

    Parameters
    ----------
    id
        The ID to convert.
    type
        The type of the ID.
    universe
        The universe of the ID.
    instance
        The instance of the ID.

    Examples
    --------
    .. code-block:: python3

        parse_id64(12345)
        parse_id64("12345")  # account ids
        parse_id64(12345, type=steam.Type.Clan)  # makes the clan id into a clan id64
        parse_id64(103582791429521412)
        parse_id64("103582791429521412")  # id64s
        parse_id64("STEAM_1:0:2")  # id2
        parse_id64("[g:1:4]")  # id3

    Raises
    ------
    :exc:`.InvalidID`
        The created 64-bit Steam ID would be invalid.

    Returns
    -------
    The 64-bit Steam ID.
    """

    if not id and type is MISSING and universe is MISSING and instance is MISSING:
        return ID64(0)

    try:
        id = int(id)
    except ValueError:
        # textual input e.g. [g:1:4]
        assert isinstance(id, str)
        result = parse_id2(id) or parse_id3(id)  # or parse_invite_code(id)  # TODO
        if result is None:
            raise InvalidID(id, "it cannot be parsed") from None
        id, type, universe, instance = result
    else:
        # numeric input
        if 0 <= id < 2**32:  # 32 bit
            try:
                type = Type.try_value(type) if type is not MISSING else Type.Individual
                universe = Universe.try_value(universe) if universe is not MISSING else Universe.Public
            except ValueError as e:
                raise InvalidID(id, e.args[0]) from None

            if instance is MISSING:
                instance = InstanceFlag.Desktop if type in (Type.Individual, Type.GameServer) else InstanceFlag.All

            if not (0 <= universe < 1 << 8):
                raise InvalidID(id, "universe is bigger than 8 bits")
            if not (0 <= type < 1 << 4):
                raise InvalidID(id, "type is bigger than 4 bits")
            if not (0 <= instance < 1 << 20):
                raise InvalidID(id, "instance is bigger than 20 bits")
        elif 0 <= id < 2**64:  # 64 bit
            universe = Universe.try_value((id >> 56) & 0xFF)
            type = Type.try_value((id >> 52) & 0xF)
            instance = InstanceFlag.try_value((id >> 32) & 0xFFFFF)
            id = id & 0xFFFFFFFF
        else:
            raise InvalidID(id, f"it is too {'large' if id >= 2**64 else 'small'}")

    return ID64(universe << 56 | type << 52 | instance << 32 | id)


ID2_REGEX = re.compile(r"STEAM_(?P<universe>\d+):(?P<remainder>[0-1]):(?P<id>\d{1,10})")


def parse_id2(value: str) -> tuple[ID32, Literal[Type.Individual], Universe, Literal[InstanceFlag.Desktop]] | None:
    """Convert an ID2 into its component parts.

    Parameters
    ----------
    value
        The ID2 e.g. ``STEAM_1:0:1234``.

    Note
    ----
    The universe will be always set to ``1``. See :attr:`ID.id2_zero`.

    Returns
    -------
    A tuple of 32 bit ID, type, universe and instance or ``None``

    e.g. (100000, Type.Individual, Universe.Public, InstanceFlag.Desktop).
    """
    if (match := ID2_REGEX.search(value)) is None:
        return None

    id = ID32((int(match["id"]) << 1) | int(match["remainder"]))
    universe = (
        int(match["universe"])
        or 1  # games before orange box used to incorrectly display universe as 0, we support that
    )

    return id, Type.Individual, Universe.try_value(universe), InstanceFlag.Desktop


ID3_REGEX = re.compile(
    (
        rf"\[(?P<type>[i{''.join(TypeChar._member_map_)}]):"
        r"(?P<universe>[0-4]):"
        r"(?P<id>[0-9]{1,10})"
        r"(:(?P<instance>\d+))?]"
    )
)


def parse_id3(value: str) -> tuple[ID32, Type, Universe, InstanceFlag] | None:
    """Convert a Steam ID3 into its component parts.

    Parameters
    ----------
    value
        The ID3 e.g. ``[U:1:1234]``.

    Returns
    -------
    A tuple of 32 bit ID, type, universe and instance or ``None``

    e.g. (100000, Type.Individual, Universe.Public, InstanceFlag.Desktop)
    """
    if (match := ID3_REGEX.search(value)) is None:
        return None

    id = ID32(int(match["id"]))
    universe = Universe.try_value(int(match["universe"]))
    type_char = match["type"].replace("i", "I")
    type = Type.try_value(TypeChar[type_char])
    instance = InstanceFlag.try_value(int(instance_)) if (instance_ := match["instance"]) else InstanceFlag.All

    match type_char:
        case "g" | "T":
            instance = InstanceFlag.All
        case "L":
            instance |= InstanceFlag.ChatLobby
        case "c":
            instance |= InstanceFlag.ChatClan
        case "G" | "I":
            instance = InstanceFlag.Desktop

    return id, type, universe, instance


_INVITE_HEX = "0123456789abcdef"
_INVITE_CUSTOM = "bcdfghjkmnpqrtvw"
_INVITE_VALID = f"{_INVITE_HEX}{_INVITE_CUSTOM}"
_URL_START = r"(?:https?://)?(?:www\.)?"
INVITE_REGEX = re.compile(rf"({_URL_START}s\.team/p/(?P<code_1>[\-{_INVITE_VALID}]+))|(?P<code_2>[\-{_INVITE_VALID}]+)")
_INVITE_CUSTOM_RE = re.compile(f"[{_INVITE_CUSTOM}]")
_INVITE_HEX_RE = re.compile(f"[{_INVITE_HEX}]")


def _invite_custom_sub(s: str, map: Mapping[str, str] = dict(zip(_INVITE_CUSTOM, _INVITE_HEX)), /) -> str:
    def sub(m: re.Match[str]) -> str:
        return map[m.group()]

    return _INVITE_CUSTOM_RE.sub(sub, s)


def _invite_hex_sub(s: str, map: Mapping[str, str] = dict(zip(_INVITE_HEX, _INVITE_CUSTOM)), /) -> str:
    def sub(m: re.Match[str]) -> str:
        return map[m.group()]

    return _INVITE_HEX_RE.sub(sub, s)


def parse_invite_code(
    code: str,
) -> tuple[ID32, Literal[Type.Individual], Literal[Universe.Public], Literal[InstanceFlag.Desktop]] | None:
    """Convert an invitation code into its component parts.

    Parameters
    ----------
    code
        The invite code e.g. ``cv-dgb``

    Returns
    -------
    A tuple of 32 bit ID, type, universe and instance or ``None``

    e.g. (100000, Type.Individual, Universe.Public, InstanceFlag.Desktop).
    """
    search = INVITE_REGEX.search(code)

    if not search:
        return None

    code = (search["code_1"] or search["code_2"]).replace("-", "")

    id = ID32(int(_invite_custom_sub(code), 16))

    if 0 < id < 2**32:
        return id, Type.Individual, Universe.Public, InstanceFlag.Desktop


URL_REGEX = re.compile(
    rf"(?P<clean_url>{_URL_START}steamcommunity\.com/(?P<type>profiles|id|user|gid|groups|app|games)/(?P<value>.+))"
)
USER_ID64_FROM_URL_REGEX = re.compile(r"g_rgProfileData\s*=\s*(?P<json>{.*?});\s*")
CLAN_ID64_FROM_URL_REGEX = re.compile(r"OpenGroupChat\(\s*'(?P<steamid>\d+)'\s*\)")


async def id64_from_url(url: StrOrURL, session: aiohttp.ClientSession = MISSING) -> ID64 | None:
    """Takes a Steam Community url and returns 64-bit Steam ID or ``None``.

    Notes
    -----
    - Each call makes a http request to https://steamcommunity.com.

    - Example URLs:

        https://steamcommunity.com/gid/[g:1:4]

        https://steamcommunity.com/gid/103582791429521412

        https://steamcommunity.com/groups/Valve

        https://steamcommunity.com/profiles/[U:1:12]

        https://steamcommunity.com/profiles/76561197960265740

        https://steamcommunity.com/id/johnc

        https://steamcommunity.com/user/r

        https://steamcommunity.com/app/570

    Parameters
    ----------
    url
        The Steam community url.
    session
        The session to make the request with. If this parameter is omitted a new one is generated.

    Returns
    -------
    The found 64-bit ID or ``None`` if ``https://steamcommunity.com`` is down or no matching account is found.
    """

    if not (search := URL_REGEX.search(str(url))):
        return None

    gave_session = session is not MISSING
    session = session if gave_session else aiohttp.ClientSession()

    try:
        if search["type"] in {"id", "profiles", "user"}:  # user profile
            r = await session.get(search["clean_url"])
            text = await r.text()
            if not (match := USER_ID64_FROM_URL_REGEX.search(text)):
                return None
            data = json.loads(match["json"])
        else:  # clan profile
            r = await session.get(search["clean_url"])
            text = await r.text()
            data = CLAN_ID64_FROM_URL_REGEX.search(text)
        return ID64(int(data["steamid"])) if data else None
    finally:
        if not gave_session:
            await session.close()


# TODO when defaults are implemented, make this Generic over Literal[Type] maybe
# TypeT = typing.TypeVar("TypeT", bound=Type)
#
#
# class ID(typing.Generic[TypeT]):
#     type TypeT
class ID(metaclass=abc.ABCMeta):
    """Convert a Steam ID between its various representations.

    .. container:: operations

        .. describe:: x == y

            Checks if two IDs are equal.

        .. describe:: hash(x)

            Returns the hash of the ID.

        .. describe:: str(x)

            Returns the string representation of :attr:`id64`.

        .. describe:: int(x)

            Returns the :attr:`id64` of the ID.

        .. describe:: format(x, format_spec)

            Formats the ID using the given format spec.

            Prefixes of ``32``, ``64`` can be used to specify which of :attr:`id` or :attr:`id64` to use.
            Anything after the prefix is passed to :func:`format`.

            E.g.

            .. code-block:: pycon

                >>> format(steam_id, "64x")  # formats the `id64` as a hex string
                "11000010264339c"
                >>> format(steam_id, "32b")  # formats the `id` as binary
                "10011001000011001110011100"


    Parameters
    ----------
    id
        The ID to convert.
    type
        The type of the ID.
    universe
        The universe of the ID.
    instance
        The instance of the ID.
    """

    # format of a 64-bit steam ID:
    # 0b0000000100010000000000000000000100010001001001110100110011000010
    #   └───┰──┘└─┰┘└─────────┰────────┘└──────────────┰───────────────┘
    #       │     │           │                        │
    #   universe  └ type      └ instance               └ account id
    #   (8 bits)    (4 bits)    (20 bits)                (32 bits)
    #   Universe    Type        InstanceFlag             ID32
    #   Public      Individual  All                      287788226

    __slots__ = ("id64", "__weakref__")

    def __init__(
        self,
        id: Intable,
        *,
        type: Type = MISSING,
        universe: Universe = MISSING,
        instance: InstanceFlag = MISSING,
    ):
        self.id64: Final = parse_id64(id, type=type, universe=universe, instance=instance)
        """The Steam ID's 64-bit ID."""

    def __int__(self) -> ID64:
        return self.id64

    def __eq__(self, other: Any) -> bool:
        return self.id64 == other.id64 if isinstance(other, ID) else NotImplemented

    def __str__(self) -> str:
        return str(self.id64)

    def __hash__(self) -> int:
        return hash(self.id64)

    def __repr__(self) -> str:
        return f"ID(id={self.id}, type={self.type!r}, universe={self.universe!r}, instance={self.instance!r})"

    def __format__(self, format_spec: str, /) -> str:
        match format_spec[:2]:
            case "64" | "":
                return format(self.id64, format_spec[2:])
            case "32":
                return format(self.id, format_spec[2:])
            case _:
                raise ValueError(f"Unknown format specifier {format_spec!r}")

    @property
    def universe(self) -> Universe:
        """The Steam universe of the ID."""
        return Universe.try_value((self.id64 >> 56) & 0xFF)

    @property
    def type(self) -> Type:
        """The Steam type of the ID."""
        return Type.try_value((self.id64 >> 52) & 0xF)

    @property
    def instance(self) -> InstanceFlag:
        """The instance of the ID."""
        return InstanceFlag.try_value((self.id64 >> 32) & 0xFFFFF)

    @property
    def id(self) -> ID32:
        """The Steam ID's 32-bit ID."""
        return ID32(self.id64 & 0xFFFFFFFF)

    @property
    def id2(self) -> str:
        """The Steam ID's ID 2.

        e.g ``STEAM_1:0:1234``.
        """
        return f"STEAM_{self.universe.value}:{self.id % 2}:{self.id >> 1}"

    @property
    def id2_zero(self) -> str:
        """The Steam ID's ID 2 accounted for bugged GoldSrc and Orange Box games.

        Note
        ----
        In these games the accounts :attr:`universe`, ``1`` for :class:`.Type.Public`, should be the ``X`` component of
        ``STEAM_X:0:1234`` however, this was bugged and the value of ``X`` was ``0``.

        e.g ``STEAM_0:0:1234``.
        """
        return self.id2.replace("_1", "_0")

    @property
    def id3(self) -> str:
        """The Steam ID's ID 3.

        e.g ``[U:1:1234]``.
        """
        type_char = TypeChar(self.type).name
        instance = None

        if self.type in (Type.AnonGameServer, Type.Multiseat):
            instance = self.instance
        elif self.type == Type.Individual:
            if self.instance != InstanceFlag.Desktop:
                instance = self.instance
        elif self.type == Type.Chat:
            if self.instance & InstanceFlag.ChatClan > 0:
                type_char = "c"
            elif self.instance & InstanceFlag.ChatLobby > 0:
                type_char = "L"
            else:
                type_char = "T"

        return f"[{type_char}:{self.universe.value}:{self.id}{f':{instance.value}' if instance is not None else ''}]"

    @property
    def invite_code(self) -> str | None:
        """The Steam ID's invite code in the s.team invite code format.

        e.g. ``cv-dgb``.
        """
        if self.type == Type.Individual and self.is_valid():
            invite_code = _invite_hex_sub(f"{self:32x}")
            split_idx = len(invite_code) // 2
            return invite_code if split_idx == 0 else f"{invite_code[:split_idx]}-{invite_code[split_idx:]}"

    @property
    def invite_url(self) -> str | None:
        """The Steam ID's full invite code URL.

        e.g ``https://s.team/p/cv-dgb``.
        """
        code = self.invite_code
        return f"https://s.team/p/{code}" if code else None

    @property
    def community_url(self) -> str | None:
        """The Steam ID's community url.

        e.g https://steamcommunity.com/profiles/123456789.
        """
        suffix = {
            Type.Individual: "profiles",
            Type.Clan: "gid",
        }
        try:
            return f"https://steamcommunity.com/{suffix[self.type]}/{self.id64}"
        except KeyError:
            return None

    def is_valid(self) -> bool:
        """Whether this Steam ID is valid.

        A Steam ID is currently considered valid if:

            - It is in ``(0, 2 ** 64)``
            - :attr:`universe` is in ``(Invalid, Dev]``
            - :attr:`type` is in ``(Invalid, AnonUser]``
            - If :attr:`type` is :class:`.Type.Individual`:
                - :attr:`id` is non-zero
                - :attr:`instance` is in ``[All, Web]``
            - If :attr:`type` is :class:`.Type.Clan`:
                - :attr:`id` is non-zero
                - :attr:`instance` is ``All``.
            - If :attr:`type` is :class:`.Type.GameServer`:
                - :attr:`id` is non-zero
        """
        if not (Universe.Invalid < self.universe <= Universe.Dev):
            return False
        if not (Type.Invalid < self.type <= Type.AnonUser):
            return False

        match self.type:
            case Type.Individual:
                return self.id != 0 and 0 <= self.instance <= InstanceFlag.Web
            case Type.Clan:
                return self.id != 0 and self.instance == InstanceFlag.All
            case Type.GameServer:
                return self.id != 0
        return True

    @staticmethod
    async def from_url(url: StrOrURL, session: ClientSession = MISSING) -> ID | None:
        """A helper function creates a Steam ID instance from a Steam community url.

        Note
        ----
        See :func:`id64_from_url` for the full parameter list.
        """
        id64 = await id64_from_url(url, session)
        return ID(id64) if id64 else None
