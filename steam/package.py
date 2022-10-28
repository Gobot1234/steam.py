"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from .app import PartialApp, PartialAppPriceOverview
from .enums import Language, LicenseFlag, LicenseType, PaymentMethod
from .types.id import Intable, PackageID
from .utils import DateTime

if TYPE_CHECKING:
    from .manifest import AppInfo, Depot, HeadlessDepot, PackageInfo
    from .message import Authors
    from .protobufs.client_server import CMsgClientLicenseListLicense
    from .protobufs.store import PurchaseReceiptInfo
    from .state import ConnectionState
    from .types import app, package


__all__ = (
    "Package",
    "FetchedPackage",
    "FetchedAppPackage",
    "License",
)


class Package:
    """Represents a package, a collection of one or more apps and depots.

    Read more on `steamworks <https://partner.steamgames.com/doc/store/application/packages>`_.
    """

    __slots__ = (
        "id",
        "name",
    )

    def __init__(self, id: Intable, name: str | None = None):
        self.id = PackageID(int(id))
        """The package's ID."""
        self.name = name
        """The package's name."""

    def __eq__(self, other: object) -> bool:
        return self.id == other.id if isinstance(other, Package) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, name={self.name!r})"


class PartialPackage(Package):
    """A package with state."""

    __slots__ = ("_state",)

    def __init__(self, state: ConnectionState, **kwargs: Any):
        super().__init__(**kwargs)
        self._state = state

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id}>"

    async def apps(self, *, language: Language | None = None) -> list[PartialApp]:
        """Fetches this package's apps."""
        fetched = await self.fetch(language=language)
        return fetched._apps

    async def fetch(self, *, language: Language | None = None) -> FetchedPackage:
        """Fetches this package's information. Shorthand for:

        .. code-block:: python3

            package = await client.fetch_package(package)
        """
        package = await self._state.client.fetch_package(self.id, language=language)
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

    async def apps_info(self) -> list[AppInfo]:
        """Shorthand for:

        .. code-block:: python3

            infos = await client.fetch_product_info(apps=await package.apps())
        """
        apps = await self.apps()
        if not apps:
            return []
        infos, _ = await self._state.fetch_product_info(app.id for app in apps)
        return infos

    async def depots(self) -> Sequence[Depot | HeadlessDepot]:
        """Fetches this package's depots."""
        try:
            depot_ids = self.depot_ids  # type: ignore
        except AttributeError:
            info = await self.info()
            depot_ids = info.depot_ids

        apps_info = await self.apps_info()

        return [
            depot
            for app_info in apps_info
            for branch in app_info._branches.values()
            for depot in branch.depots
            if depot.id in depot_ids
        ] + [depot for app_info in apps_info for depot in app_info.headless_depots if depot.id in depot_ids]

    # TODO .manifests, fetch_manifest


@dataclass(slots=True)
class PackagePriceOverview(PartialAppPriceOverview):
    individual: int


class FetchedPackage(PartialPackage):
    name: str

    def __init__(self, state: ConnectionState, data: package.FetchedPackage):
        super().__init__(state, name=data["name"], id=data["packageid"])
        self._apps = [PartialApp(state, id=app["id"], name=app["name"]) for app in data["apps"]]
        self.description = data["page_content"]
        self.created_at = DateTime.parse_steam_date(data["release_date"]["date"], full_month=False)
        self.logo_url = data["small_logo"]
        self.logo_url = data["header_image"]
        platforms = data["platforms"]
        self._on_windows = platforms["windows"]
        self._on_mac_os = platforms["mac"]
        self._on_linux = platforms["linux"]
        self.price_overview = PackagePriceOverview(**data["price"])

    def is_free(self) -> bool:
        """Whether the package is free."""
        return self.price_overview.final == 0

    def is_on_windows(self) -> bool:
        """Whether the package is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the package is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the package is playable on Linux."""
        return self._on_linux


@dataclass(slots=True)
class FetchedAppPackagePriceOverview:
    percent_discount: int
    final: int


class FetchedAppPackage(PartialPackage):
    __slots__ = (
        "_is_free",
        "price_overview",
    )

    def __init__(self, state: ConnectionState, data: app.PackageGroupSub):
        name, _, _ = data["option_text"].rpartition(" - ")
        super().__init__(state, name=name, id=data["packageid"])
        self._is_free = data["is_free_license"]
        self.price_overview = FetchedAppPackagePriceOverview(
            int(re.search(r"-?(\d)", data["percent_savings_text"])[0]),
            data["price_in_cents_with_discount"],  # this isn't always in cents
        )

    def is_free(self) -> bool:
        return self._is_free


class License(PartialPackage):
    """Represents a License to a package the client user has access to."""

    __slots__ = (
        "owner",
        "type",
        "flags",
        "created_at",
        "master_package",
        "next_process_at",
        "time_limit",
        "time_used",
        "payment_method",
        "purchase_country_code",
        "territory_code",
        "change_number",
        "initial_period",
        "initial_time_unit",
        "renewal_period",
        "renewal_time_unit",
        "access_token",
    )

    def __init__(self, state: ConnectionState, proto: CMsgClientLicenseListLicense, owner: Authors):
        super().__init__(state, id=proto.package_id)
        self.owner: Authors = owner
        """The license's owner."""
        self.type = LicenseType.try_value(proto.license_type)
        """The license's type."""
        self.flags = LicenseFlag.try_value(proto.flags)
        """The license's flags."""
        self.created_at = DateTime.from_timestamp(proto.time_created) if proto.time_created else None
        """The license's creation date."""
        self.master_package = PartialPackage(state, id=proto.master_package_id) if proto.master_package_id else None
        """The license's master package."""
        self.next_process_at = DateTime.from_timestamp(proto.time_next_process)
        """The date when the license will be processed."""
        self.time_limit = timedelta(minutes=proto.minute_limit) if proto.minute_limit else None
        """The time limit for the license."""
        self.time_used = timedelta(minutes=proto.minutes_used)
        """The time the license has been used."""
        self.payment_method = PaymentMethod.try_value(proto.payment_method)
        """The payment method used for the license."""
        self.purchase_country_code = proto.purchase_country_code
        """The country code of the license's purchase."""
        self.territory_code = proto.territory_code
        """The license's territory code."""
        self.change_number = proto.change_number
        """The license's current change number."""
        self.initial_period = proto.initial_period
        """The license's initial period."""
        self.initial_time_unit = proto.initial_time_unit
        """The license's initial time unit."""
        self.renewal_period = timedelta(minutes=proto.renewal_period)
        """The license's renewal period."""
        self.renewal_time_unit = proto.renewal_time_unit
        """The license's renewal time unit."""
        self.access_token = proto.access_token
        """The license's access token."""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id} owner={self.owner!r} flags={self.flags!r}>"

    @property
    def time_remaining(self) -> timedelta | None:
        """The amount of time that this license can be used for."""
        if self.flags & LicenseFlag.Expired:
            return
        if self.time_limit is None:
            return
        return self.time_limit - self.time_used
