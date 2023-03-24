"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import TypeVar

from ._const import URL
from .app import PartialApp
from .clan import PartialClan
from .enums import Language
from .package import PartialPackage
from .types.id import BundleID, Intable

if TYPE_CHECKING:
    from .state import ConnectionState
    from .store import BundleStoreItem
    from .types import bundle

__all__ = (
    "Bundle",
    "PartialBundle",
    "FetchedBundle",
)

NameT = TypeVar("NameT", bound=str | None, default=str | None, covariant=True)


class Bundle(Generic[NameT]):
    """Represents a bundle of apps and packages."""

    __slots__ = ("id", "name")

    def __init__(self, *, id: Intable, name: NameT = None) -> None:
        self.id = BundleID(int(id))
        """The bundle's ID."""
        self.name = name
        """The bundle's name."""

    def __repr__(self) -> str:
        return f"Bundle(id={self.id}, name={self.name!r})"

    def __eq__(self, other: object) -> bool:
        return other.id == self.id if isinstance(other, Bundle) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.id)

    @property
    def url(self) -> str:
        """The bundle's store page URL."""
        return f"{URL.STORE}/bundle/{self.id}"


class PartialBundle(Bundle[NameT]):
    def __init__(self, state: ConnectionState, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._state = state

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id}>"

    async def fetch(self) -> FetchedBundle:
        """Fetch this bundle.

        Shorthand for:

        .. code:: python

            bundle = await client.fetch_bundle(bundle)
        """
        return await self._state.client.fetch_bundle(self.id)

    async def store_item(self) -> BundleStoreItem:
        """Fetch the store item for this bundle.

        Shorthand for:

        .. code:: python

            (item,) = await client.fetch_store_item(bundles=[bundle])
        """
        (item,) = await self._state.client.fetch_store_item(bundles=(self,))
        return item

    async def apps(self) -> list[PartialApp]:
        """Fetch the bundle's apps."""
        fetched = await self.fetch()
        return fetched._apps

    async def packages(self) -> list[PartialPackage]:
        """Fetch the bundle's packages."""
        fetched = await self.fetch()
        return fetched._packages


class FetchedBundle(PartialBundle[str]):
    """Represents a bundle of games and packages."""

    def __init__(self, state: ConnectionState, data: bundle.Bundle) -> None:
        super().__init__(state, id=data["bundleid"], name=data["name"])
        self._apps = [PartialApp(state, id=app_id) for app_id in data["appids"]]
        self._packages = [PartialPackage(state, id=package_id) for package_id in data["packageids"]]

        self._on_windows = data["available_windows"]
        self._on_mac_os = data["available_mac"]
        self._on_linux = data["available_linux"]
        self._vrhmod = data.get("support_vrhmod", False)
        self._vrhmod_only = data.get("support_vrhmod_only", False)
        self.creator_clans = [PartialClan(state, id) for id in data["creator_clan_ids"]]
        """The clans of the creators that created this bundle."""
        self.supported_languages = [Language.try_value(lang) for lang in data["localized_langs"]]
        """The languages that this bundle is supported in."""

    def is_on_windows(self) -> bool:
        """Whether the app is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the app is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the app is playable on Linux."""
        return self._on_linux

    async def apps(self) -> list[PartialApp]:
        return self._apps

    async def packages(self) -> list[PartialPackage]:
        return self._packages
