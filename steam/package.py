"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from . import utils
from .enums import Language, LicenseFlag, LicenseType, PaymentMethod, Type
from .game import StatefulGame
from .utils import DateTime, Intable

if TYPE_CHECKING:
    from .clan import Clan
    from .manifest import PackageInfo
    from .message import Authors
    from .protobufs.client_server import CMsgClientLicenseListLicense
    from .protobufs.store import PurchaseReceiptInfo
    from .state import ConnectionState
    from .types import package


__all__ = (
    "Package",
    "FetchedPackage",
    "License",
)


class Package:
    """Represents information on a package which is a collection of one or more applications and depots.

    Read more on `steamworks <https://partner.steamgames.com/doc/store/application/packages>`_.
    """

    __slots__ = (
        "id",
        "name",
    )

    def __init__(self, id: Intable, name: str | None = None):
        self.id = int(id)
        """The package's ID."""
        self.name = name
        """The package's name."""

    def __eq__(self, other: object) -> bool:
        return self.id == other.id if isinstance(other, Package) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name!r})"


class StatefulPackage(Package):
    """A package with state."""

    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, **kwargs: Any):
        super().__init__(**kwargs)
        self._state = state

    async def fetch_games(self) -> list[StatefulGame]:
        """Fetches this package's games."""
        info = await self.fetch()
        return info.games

    async def fetch(self) -> FetchedPackage:
        package = await self._state.client.fetch_package(self.id)
        if package is None:
            raise ValueError("Fetched package was not valid.")
        return package

    async def info(self) -> PackageInfo:
        """Shorthand for:

        .. code-block:: python3

            (info,) = await client.fetch_product_info(packages=[package])
        """
        _, (info,) = await self._state.fetch_product_info(package_ids=(self.id,))
        return info

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id}>"


class FetchedPackage(StatefulPackage):
    name: str

    def __init__(self, state: ConnectionState, data: package.FetchedPackage):
        super().__init__(state, name=data["name"], id=data["packageid"])
        self.games = [StatefulGame(state, id=app_id) for app_id in data["appids"]]
        self.created_at = DateTime.from_timestamp(int(data["release_date"]))
        self.languages = [Language.try_value(language) for language in data["localized_langs"]]
        self._on_windows = data["available_windows"]
        self._on_mac_os = data["available_mac"]
        self._on_linux = data["available_linux"]
        self._clan_id64s = [utils.make_id64(id, type=Type.Clan) for id in data["creator_clan_ids"]]

    async def clans(self) -> list[Clan]:
        return [await self._state.fetch_clan(id64) for id64 in self._clan_id64s]  # type: ignore

    def is_on_windows(self) -> bool:
        """Whether the game is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the game is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the game is playable on Linux."""
        return self._on_linux


@dataclass
class FetchedGamePackagePriceOverview:
    percent_discount: int
    final: int


class FetchedGamePackage(StatefulPackage):
    __slots__ = (
        "_is_free",
        "price_overview",
    )

    def __init__(self, state: ConnectionState, data: game.PackageGroupSub):
        name, _, _ = data["option_text"].rpartition(" - ")
        super().__init__(state, name=name, id=data["packageid"])
        self._is_free = data["is_free_license"]
        percent_savings_text: str
        self.price_overview = FetchedGamePackagePriceOverview(
            int(re.search(r"-?(\d)", data["percent_savings_text"])[0]),
            data["price_in_cents_with_discount"],  # this isn't always in cents
        )

    def is_free(self) -> bool:
        return self._is_free


class License(StatefulPackage):
    def __init__(self, state: ConnectionState, proto: CMsgClientLicenseListLicense, owner: Authors):
        super().__init__(state, id=proto.package_id)
        self.owner: Authors = owner
        self.created_at = DateTime.from_timestamp(proto.time_created) if proto.time_created else None
        self.next_process_at = DateTime.from_timestamp(proto.time_next_process)
        self.limit = timedelta(minutes=proto.minute_limit) if proto.minute_limit else None  # the time limit in minutes
        self.used = timedelta(minutes=proto.minutes_used)  # minute precision
        self.payment_method = PaymentMethod.try_value(proto.payment_method)
        self.flags = LicenseFlag.try_value(proto.flags)
        self.purchase_country_code = proto.purchase_country_code
        self.license_type = LicenseType.try_value(proto.license_type)
        self.territory_code = proto.territory_code
        self.current_change_number = proto.change_number
        self.initial_period = proto.initial_period
        self.initial_time_unit = proto.initial_time_unit
        self.renewal_period = timedelta(minutes=proto.renewal_period)
        self.renewal_time_unit = proto.renewal_time_unit
        self.access_token = proto.access_token
        self.master_package = StatefulPackage(state, id=proto.master_package_id) if proto.master_package_id else None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} owner={self.owner!r} flags={self.flags!r}>"

    @property
    def remaining(self) -> timedelta | None:
        """The amount of time that this license can be used for."""
        if self.flags & LicenseFlag.Expired:
            return
        if self.limit is None:
            return
        return self.limit - self.used


# class Transaction:
#     def __init__(self, state: ConnectionState, proto: PurchaseReceiptInfo):
#         self.id = proto.transactionid
#         self.items = [
#             TransactionItem(
#                 Package(state, item.packageid), StatefulGame(state, id=item.appid), item.line_item_description
#             )
#             for item in proto.line_items
#         ]
#
#         self.package = Package(state, proto.packageid)
#         self.purchase_status = proto.purchase_status
#         self.created_at = DateTime.from_timestamp(proto.transaction_time)
#         self.payment_method = PaymentMethod.try_value(proto.payment_method)
#         self.base_price = proto.base_price
#         self.total_discount = proto.total_discount
#         self.tax = proto.tax
#         self.shipping = proto.shipping
#         self.currency_code = proto.currency_code
#         self.country_code = proto.country_code
#
#
# @dataclass
# class TransactionItem:
#     package_id: Package
#     game: StatefulGame
#     description: str
