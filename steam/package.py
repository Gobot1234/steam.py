from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .enums import LicenseFlag, LicenseType, PaymentMethod
from .game import StatefulGame

if TYPE_CHECKING:
    from .manifest import PackageInfo
    from .message import Authors
    from .protobufs.client_server import CMsgClientLicenseListLicense
    from .state import ConnectionState


@dataclass(repr=False)
class Package:
    """Represents information on a package which is a collection of one or more applications and depots.

    Read more on `steamworks <https://partner.steamgames.com/doc/store/application/packages>`_.
    """

    __slots__ = ("id", "games", "_state")
    _state: ConnectionState
    id: int
    """The package's ID."""

    async def fetch_games(self) -> list[StatefulGame]:
        """Fetches this package's games."""
        info = await self.info()
        return info.games

    async def info(self) -> PackageInfo:
        """Shorthand for:

        .. code-block:: python3

            (info,) = await client.fetch_product_info(packages=[package])
        """
        _, (info,) = await self._state.fetch_product_info(package_ids=(self.id,))
        return info

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.id}>"


class License(Package):
    def __init__(self, state: ConnectionState, proto: CMsgClientLicenseListLicense, owner: Authors):
        super().__init__(state, proto.package_id)
        self.owner: Authors = owner
        self.created_at = datetime.utcfromtimestamp(proto.time_created) if proto.time_created else None
        self.next_process_at = datetime.utcfromtimestamp(proto.time_next_process)
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
        self.master_package = Package(state, proto.master_package_id) if proto.master_package_id else None

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
#         self.created_at = datetime.utcfromtimestamp(proto.transaction_time)
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
