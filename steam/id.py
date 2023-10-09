"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
import re
from collections.abc import Callable
from contextlib import nullcontext
from types import GenericAlias
from typing import TYPE_CHECKING, Final, Generic, Literal, cast

import aiohttp
from typing_extensions import TypeVar

from ._const import JSON_LOADS, URL
from .enums import Instance, Type, TypeChar, Universe
from .errors import InvalidID
from .types.id import ID32, ID64, Intable

if TYPE_CHECKING:
    from aiohttp import ClientSession

    from .types.http import StrOrURL
    from .types.user import IndividualID


__all__ = ("ID",)


def parse_id64(
    id: Intable,
    /,
    *,
    type: Type | None = None,
    universe: Universe | None = None,
    instance: Instance | None = None,
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
    .. code:: python

        parse_id64(12345)
        parse_id64("12345")  # account ids
        parse_id64(12345, type=steam.Type.Clan)  # makes what would be interpreted as a user id into a clan id64
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

    if not id and type is None and universe is None and instance is None:
        return ID64(0)

    try:
        id = int(id)
    except ValueError:
        # textual input e.g. [g:1:4]
        if not isinstance(id, str):
            raise InvalidID(id, type, universe, instance, "it cannot be parsed as an int or str") from None
        result = ID.from_id2(id) or ID.from_id3(id)
        if result is None:
            raise InvalidID(id, type, universe, instance, "it cannot be parsed") from None
        return result.id64
    else:
        # numeric input
        if id < 0:
            raise InvalidID(id, type, universe, instance, "it is too small")
        elif 0 <= id < 2**32:  # 32 bit
            type = type or Type.Individual
            universe = universe or Universe.Public

            if instance is None:
                instance = Instance.Desktop if type in (Type.Individual, Type.GameServer) else Instance.All

            if not (0 <= universe < 1 << 8):
                raise InvalidID(id, type, universe, instance, "universe is bigger than 8 bits")
            if not (0 <= type < 1 << 4):
                raise InvalidID(id, type, universe, instance, "type is bigger than 4 bits")
            if not (0 <= instance < 1 << 20):
                raise InvalidID(id, type, universe, instance, "instance is bigger than 20 bits")
        elif id < 2**64:  # 64 bit
            universe = Universe.try_value((id >> 56) & 0xFF)
            type = Type.try_value((id >> 52) & 0xF)
            instance = Instance.try_value((id >> 32) & 0xFFFFF)
            id &= 0xFFFFFFFF
        else:
            raise InvalidID(id, type, universe, instance, "it is too large")

    return ID64(universe << 56 | type << 52 | instance << 32 | id)


ID2_REGEX = re.compile(r"STEAM_(?P<universe>\d+):(?P<remainder>[0-1]):(?P<id>\d{1,10})")
ID3_REGEX = re.compile(
    (
        rf"\[(?P<type>[i{''.join(TypeChar._member_map_)}]):"
        rf"(?P<universe>[{min(Universe).value}-{max(Universe).value}]):"
        r"(?P<id>[0-9]{1,10})"
        r"(:(?P<instance>\d+))?]"
    )
)


_INVITE_HEX = "0123456789abcdef"
_INVITE_CUSTOM = "bcdfghjkmnpqrtvw"
_INVITE_VALID = f"{_INVITE_HEX}{_INVITE_CUSTOM}"
_URL_START = r"(?:https?://)?(?:www\.)?"
INVITE_REGEX = re.compile(rf"(?:{_URL_START}(?:s\.team/p/))?(?P<code>[\-{_INVITE_VALID}]{{1,8}})")


def _invite_custom_sub(
    s: str,
    repl: Callable[[re.Match[str]], str] = lambda m, map=dict(zip(_INVITE_CUSTOM, _INVITE_HEX)): map[m.group()],
    pattern: re.Pattern[str] = re.compile(f"[{_INVITE_CUSTOM}]"),
    /,
) -> str:
    return pattern.sub(repl, s)


def _invite_hex_sub(
    s: str,
    repl: Callable[[re.Match[str]], str] = lambda m, map=dict(zip(_INVITE_HEX, _INVITE_CUSTOM)): map[m.group()],
    pattern: re.Pattern[str] = re.compile(f"[{_INVITE_HEX}]"),
    /,
) -> str:
    return pattern.sub(repl, s)


USER_URL_PATHS = frozenset({"id", "profiles", "user"})
CLAN_URL_PATHS = frozenset({"gid", "groups", "app", "games"})
URL_REGEX = re.compile(
    rf"{_URL_START}(?P<clean_url>steamcommunity\.com/(?P<type>{'|'.join(USER_URL_PATHS | CLAN_URL_PATHS)})/[^/]*)"
)
USER_ID64_FROM_URL_REGEX = re.compile(r"g_rgProfileData\s*=\s*(?P<json>{.*?});\s*")
CLAN_ID64_FROM_URL_REGEX = re.compile(r"OpenGroupChat\(\s*'(?P<steamid>\d+)'\s*\)")


async def id64_from_url(url: StrOrURL, /, session: aiohttp.ClientSession | None = None) -> ID64 | None:
    """Fetches the 64-bit Steam ID from a Steam Community URL or ``None``.

    See Also
    --------
    :meth:`ID.from_url` for more information.
    """
    id = await ID.from_url(url, session=session)
    return id.id64 if id is not None else None


_ID64_TO_ID32: Final = cast(Callable[[int], ID32], 0xFFFFFFFF.__and__)


TypeT = TypeVar("TypeT", bound=Type, default=Type, covariant=True)


class ID(Generic[TypeT], metaclass=abc.ABCMeta):
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
                >>> f"{steam_id:32b}"  # same as above


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
    __class_getitem__ = classmethod(
        GenericAlias
    )  # want the different behaviour between typing._GenericAlias to do with attribute forwarding

    def __init__(
        self,
        id: Intable,
        *,
        type: TypeT | None = None,
        universe: Universe | None = None,
        instance: Instance | None = None,
    ):
        self.id64: Final = parse_id64(id, type=type, universe=universe, instance=instance)
        """The Steam ID's 64-bit ID."""

    def __int__(self) -> ID64:
        return self.id64

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ID) and self.id64 == other.id64

    def __str__(self) -> str:
        return str(self.id64)

    def __hash__(self) -> int:
        return hash(self.id64)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, type={self.type!r}, universe={self.universe!r}, instance={self.instance!r})"

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
    def type(self) -> TypeT:
        """The Steam type of the ID."""
        return cast(TypeT, Type.try_value((self.id64 >> 52) & 0xF))

    @property
    def instance(self) -> Instance:
        """The instance of the ID."""
        return Instance.try_value((self.id64 >> 32) & 0xFFFFF)

    @property
    def id(self, _ID64_TO_ID32: Callable[[ID64], ID32] = _ID64_TO_ID32, /) -> ID32:
        """The Steam ID's 32-bit ID."""
        return _ID64_TO_ID32(self.id64)

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

        match self.type:
            case Type.AnonGameServer | Type.Multiseat:
                instance = self.instance
            case Type.Individual:
                if self.instance != Instance.Desktop:
                    instance = self.instance
            case Type.Chat:
                if self.instance & Instance.ChatClan > 0:
                    type_char = "c"
                elif self.instance & Instance.ChatLobby > 0:
                    type_char = "L"
                else:
                    type_char = "T"

        return f"[{type_char}:{self.universe.value}:{self.id}{f':{instance.value}' if instance is not None else ''}]"

    # @property
    # @overload
    # def invite_code(self: ID[Type.Individual]) -> str:
    #     ...
    #
    # @property
    # @overload
    # def invite_code(self: ID[~Type.Individual]) -> None:
    #     ...

    @property
    def invite_code(self) -> str | None:
        """The Steam ID's invite code in the s.team invite code format.

        e.g. ``cv-dgb``.
        """
        if self.type == Type.Individual and self.is_valid():
            invite_code = _invite_hex_sub(f"{self:32x}")
            split_idx = len(invite_code) // 2
            return invite_code if split_idx == 0 else f"{invite_code[:split_idx]}-{invite_code[split_idx:]}"

    # @property
    # @overload
    # def invite_url(self: ID[Type.Individual]) -> str:
    #     ...
    #
    # @property
    # @overload
    # def invite_url(self: ID[~Type.Individual]) -> None:
    #     ...
    #

    @property
    def invite_url(self) -> str | None:
        """The Steam ID's full invite code URL.

        e.g ``https://s.team/p/cv-dgb``.
        """
        code = self.invite_code
        return f"https://s.team/p/{code}" if code else None

    # @property
    # @overload
    # def community_url(self: ID[Type.Individual | Type.Clan]) -> str:
    #     ...
    #
    # @property
    # @overload
    # def community_url(self: ID[~(Type.Individual | Type.Clan)]) -> None:
    #     ...

    @property
    def community_url(self) -> str | None:
        """The Steam ID's community url if it is a :attr:`.Type.Individual` or :attr:`.Type.Clan`.

        e.g ``https://steamcommunity.com/profiles/123456789`` or ``https://steamcommunity.com/gid/123456789``.
        """
        match self.type:
            case Type.Individual:
                return str(URL.COMMUNITY / f"profiles/{self.id64}")
            case Type.Clan:
                return str(URL.COMMUNITY / f"gid/{self.id64}")
            case _:
                return None

    def is_valid(self) -> bool:
        """Whether this Steam ID is valid.

        A Steam ID is currently considered valid if:

            - It is in ``(0, 2**64)``
            - :attr:`universe` is in ``(Invalid, Dev]``
            - :attr:`type` is in ``(Invalid, AnonUser]``
            - If :attr:`type` is :attr:`.Type.Individual`:
                - :attr:`id` is non-zero
                - :attr:`instance` is in ``[All, Web]``
            - If :attr:`type` is :attr:`.Type.Clan`:
                - :attr:`id` is non-zero
                - :attr:`instance` is ``All``.
            - If :attr:`type` is :attr:`.Type.GameServer`:
                - :attr:`id` is non-zero
        """
        if not (0 < self.id64 < 2**64):
            return False  # this shouldn't ever happen unless someone messes around with id64 but w/e
        if not (Universe.Invalid < self.universe <= Universe.Dev):
            return False
        if not (Type.Invalid < self.type <= Type.AnonUser):
            return False

        match self.type:
            case Type.Individual:
                return self.id != 0 and Instance.All <= self.instance <= Instance.Web
            case Type.Clan:
                return self.id != 0 and self.instance == Instance.All
            case Type.GameServer:
                return self.id != 0
        return True

    @staticmethod
    def from_id2(value: str, /) -> IndividualID | None:
        """Create an ID from a user's :attr:`id2`.

        Parameters
        ----------
        value
            The ID2 e.g. ``STEAM_1:0:1234``.

        Note
        ----
        The universe will be set to :attr:`Universe.Public` if it's ``0``. See :attr:`ID.id2_zero`.
        """
        if (match := ID2_REGEX.fullmatch(value)) is None:
            return None

        id = (int(match["id"]) << 1) | int(match["remainder"])
        universe = (
            int(match["universe"])
            or 1  # games before orange box used to incorrectly display universe as 0, we support that
        )

        return ID(id, type=Type.Individual, universe=Universe.try_value(universe), instance=Instance.Desktop)

    @staticmethod
    def from_id3(value: str, /) -> ID | None:
        """Create an ID from an SteamID's :attr:`id3`.

        Parameters
        ----------
        value
            The ID3 e.g. ``[U:1:1234]``.
        """
        if (match := ID3_REGEX.fullmatch(value)) is None:
            return None

        id = ID32(match["id"])
        universe = Universe.try_value(int(match["universe"]))
        type_char = TypeChar[match["type"].replace("i", "I")]
        if instance_ := match["instance"]:
            instance = Instance.try_value(int(instance_))
        else:
            instance = Instance.All
            # we can't use simple match because that uses the int.__eq__ which won't work for L, c and T
            match type_char.name:
                case TypeChar.g.name | TypeChar.T.name:
                    instance = Instance.All
                case TypeChar.L.name:
                    instance = Instance.ChatLobby
                case TypeChar.c.name:
                    instance = Instance.ChatClan
                case TypeChar.G.name | TypeChar.U.name:
                    instance = Instance.Desktop

        return ID(id, type=type_char.value, universe=universe, instance=instance)

    @staticmethod
    def from_invite_code(value: str, /) -> ID[Literal[Type.Individual]] | None:
        """Create an ID from a user's :attr:`invite_code`.

        Parameters
        ----------
        value
            The invite code e.g. ``cv-dgb``
        """
        if (search := INVITE_REGEX.fullmatch(value)) is None:
            return None

        code = search["code"].replace("-", "")

        id = ID32(_invite_custom_sub(code), 16)

        if 0 < id < 2**32:
            return ID(id, type=Type.Individual, universe=Universe.Public, instance=Instance.Desktop)

    @staticmethod
    async def from_url(
        url: StrOrURL, /, session: ClientSession | None = None
    ) -> ID[Literal[Type.Individual, Type.Clan]] | None:
        """Fetches the ID associated with a Steam Community URL or ``None``.

        Note
        -----
        Each call makes an HTTP request to https://steamcommunity.com.

        Examples
        --------
        The following are valid calls:

        .. code:: pycon

            >>> await ID.from_url("https://steamcommunity.com/groups/Valve")
            >>> await ID.from_url("https://steamcommunity.com/gid/103582791429521412")
            >>> await ID.from_url("https://steamcommunity.com/gid/[g:1:4]")
            ID(id=4, type=Type.Clan, universe=Universe.Public, instance=Instance.All)

            >>> await ID.from_url("https://steamcommunity.com/id/johnc")
            >>> await ID.from_url("https://steamcommunity.com/profiles/76561197960265740")
            >>> await ID.from_url("https://steamcommunity.com/profiles/[U:1:12]")
            >>> await ID.from_url("https://steamcommunity.com/user/r")
            ID(id=12, type=Type.Individual, universe=Universe.Public, instance=Instance.Desktop)

            >>> await ID.from_url("https://steamcommunity.com/app/570")
            ID(id=3703047, type=Type.Clan, universe=Universe.Public, instance=Instance.All)

        Parameters
        ----------
        url
            The Steam Community URL.
        session
            The session to make the request with. If ``None``, one is generated.
        """

        if not (search := URL_REGEX.match(str(url))):
            return None

        async with (
            aiohttp.ClientSession() if session is None else nullcontext(session) as session,
            session.get(f"https://{search['clean_url']}") as r,
        ):
            text = await r.text()

        if search["type"] in USER_URL_PATHS:
            data = JSON_LOADS(match["json"]) if (match := USER_ID64_FROM_URL_REGEX.search(text)) else None
        else:
            data = CLAN_ID64_FROM_URL_REGEX.search(text)
        return ID[Literal[Type.Individual, Type.Clan]](int(data["steamid"])) if data else None


ID_ZERO: Final = ID[Literal[Type.Individual]](0, type=Type.Individual)
