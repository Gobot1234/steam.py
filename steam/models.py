"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
import asyncio
import logging
import re
import traceback
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta
from io import BytesIO
from typing import TYPE_CHECKING, Any, TypeVar

from typing_extensions import Literal, ParamSpec, Self, TypedDict
from yarl import URL as _URL

from . import utils
from ._const import TASK_HAS_NAME, URL
from .enums import IntEnum
from .image import Image
from .protobufs import EMsg

if TYPE_CHECKING:
    from _typeshed import StrOrBytesPath

    from .gateway import Msgs
    from .state import ConnectionState


__all__ = (
    "PriceOverview",
    "Ban",
)

F = TypeVar("F", bound="Callable[..., Any]")
P = ParamSpec("P")


def api_route(path: str, version: int = 1) -> _URL:
    return URL.API / f"{path}/v{version}"


class _ReturnTrue:
    __slots__ = ()

    def __call__(self, *_: Any, **__: Any) -> Literal[True]:
        return True

    def __repr__(self) -> str:
        return "<return_true>"


return_true = _ReturnTrue()


class Registerable:
    __slots__ = ("loop", "parsers_name")
    loop: asyncio.AbstractEventLoop

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        self = super().__new__(cls)
        self.loop = asyncio.get_event_loop()
        cls.parsers_name = tuple(cls.__annotations__)[0]
        bases = tuple(reversed(cls.__mro__[:-2]))  # skip Registerable and object
        for idx, base in enumerate(bases):
            parsers_name = tuple(base.__annotations__)[0]
            for name, attr in base.__dict__.items():
                if not hasattr(attr, "msg"):
                    continue
                try:
                    parsers = getattr(self, parsers_name)
                except AttributeError:
                    parsers = {}
                    setattr(self, parsers_name, parsers)
                msg_parser = getattr(self, name)
                if idx != 0 and isinstance(attr.msg, EMsg):
                    parsers = getattr(self, tuple(bases[0].__annotations__)[0])
                parsers[attr.msg] = msg_parser

        return self

    @staticmethod
    def _run_parser_callback(task: asyncio.Task[object]) -> None:
        try:
            exception = task.exception()
        except asyncio.CancelledError:
            return
        if exception:
            traceback.print_exception(exception.__class__, exception, exception.__traceback__)

    def run_parser(self, emsg: IntEnum, msg: Msgs) -> None:
        try:
            event_parser = getattr(self, self.parsers_name)[emsg]
        except KeyError:
            log = logging.getLogger(self.__class__.__module__)
            try:
                log.debug("Ignoring event %r", msg)
            except Exception:
                log.debug("Ignoring event %s", msg.msg)
        else:
            coro = utils.maybe_coroutine(event_parser, msg)

            (
                self.loop.create_task(coro, name=f"task_{event_parser.__name__}")
                if TASK_HAS_NAME
                else self.loop.create_task(coro)
            ).add_done_callback(self._run_parser_callback)


EventParser = None


def register(msg: IntEnum) -> Callable[[F], F]:  # this afaict is not type able currently without HKT
    def wrapper(callback: F) -> F:
        callback.msg = msg
        return callback

    return wrapper


PRICE_RE = re.compile(r"(^\D*(?P<price>[\d,.]*)\D*$)")


class PriceOverviewDict(TypedDict):
    success: bool
    lowest_price: str
    median_price: str
    volume: str


class PriceOverview:
    """Represents the data received from https://steamcommunity.com/market/priceoverview.

    Attributes
    -------------
    currency
        The currency identifier for the item e.g. "$" or "£".
    volume
        The amount of items that sold in the last 24 hours.
    lowest_price
        The lowest price observed by the market.
    median_price
        The median price observed by the market.
    """

    __slots__ = ("currency", "volume", "lowest_price", "median_price")

    lowest_price: float | str
    median_price: float | str

    def __init__(self, data: PriceOverviewDict):
        lowest_price = PRICE_RE.search(data["lowest_price"])["price"]
        median_price = PRICE_RE.search(data["median_price"])["price"]

        try:
            self.lowest_price = float(lowest_price.replace(",", "."))
            self.median_price = float(median_price.replace(",", "."))
        except ValueError:
            self.lowest_price = lowest_price
            self.median_price = median_price

        self.volume: int = int(data["volume"].replace(",", ""))
        self.currency: str = data["lowest_price"].replace(lowest_price, "").strip()

    def __repr__(self) -> str:
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in self.__slots__]
        return f"<PriceOverview {' '.join(resolved)}>"


class Ban:
    """Represents a Steam ban.

    Attributes
    ----------
    since_last_ban
        How many days since the user was last banned
    number_of_game_bans
        The number of game bans the user has.
    """

    __slots__ = (
        "since_last_ban",
        "number_of_game_bans",
        "_vac_banned",
        "_community_banned",
        "_market_banned",
    )

    def __init__(self, data: dict[str, Any]):
        self._vac_banned: bool = data["VACBanned"]
        self._community_banned: bool = data["CommunityBanned"]
        self._market_banned: bool = data["EconomyBan"]
        self.since_last_ban = timedelta(days=data["DaysSinceLastBan"])
        self.number_of_game_bans: int = data["NumberOfGameBans"]

    def __repr__(self) -> str:
        attrs = [
            ("number_of_game_bans", self.number_of_game_bans),
            ("is_vac_banned()", self.is_vac_banned()),
            ("is_community_banned()", self.is_community_banned()),
            ("is_market_banned()", self.is_market_banned()),
        ]
        resolved = [f"{method}={value!r}" for method, value in attrs]
        return f"<Ban {' '.join(resolved)}>"

    def is_banned(self) -> bool:
        """Species if the user is banned from any part of Steam."""
        return any((self.is_vac_banned(), self.is_community_banned(), self.is_market_banned()))

    def is_vac_banned(self) -> bool:
        """Whether or not the user is VAC banned."""
        return self._vac_banned

    def is_community_banned(self) -> bool:
        """Whether or not the user is community banned."""
        return self._community_banned

    def is_market_banned(self) -> bool:
        """Whether or not the user is market banned."""
        return self._market_banned


class _IOMixin(metaclass=abc.ABCMeta):
    __slots__ = ()

    @asynccontextmanager
    async def open(self, **kwargs: Any) -> AsyncGenerator[BytesIO, None]:
        """Open this file as and returns its contents as an in memory buffer."""
        try:
            url: str = self.url  # type: ignore
            state: ConnectionState = self._state  # type: ignore
        except AttributeError:
            raise NotImplementedError() from None

        async with state.http._session.get(url) as r:
            yield BytesIO(await r.read())

    async def read(self, **kwargs: Any) -> bytes:
        """Read the whole contents of this file."""
        async with self.open(**kwargs) as io:
            return io.getvalue()

    async def save(self, filename: StrOrBytesPath, **kwargs: Any) -> int:
        """Save the file to a path.

        Parameters
        ----------
        filename
            The filename of the file to be created and have this saved to.

        Returns
        -------
        The number of bytes written.
        """
        async with self.open(**kwargs) as file:
            with file, open(filename, "wb") as actual_fp:
                return actual_fp.write(file.getvalue())

    async def image(self, *, spoiler: bool = False, **kwargs: Any) -> Image:
        """Return this file as an image for uploading."""
        async with self.open(**kwargs) as file:
            return Image(file, spoiler=spoiler)
