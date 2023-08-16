"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic

from typing_extensions import TypeVar

from ._const import URL, impl_eq_via_id
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


@impl_eq_via_id
class Bundle(Generic[NameT]):
    """Represents a bundle of apps and packages. Read more on :works:`steamworks <store/application/bundles>`"""

    __slots__ = ("id", "name")

    def __init__(self, *, id: Intable, name: NameT = None) -> None:
        self.id = BundleID(int(id))
        """The bundle's ID."""
        self.name = name
        """The bundle's name."""

    def __repr__(self) -> str:
        return f"Bundle(id={self.id}, name={self.name!r})"

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

    async def fetch(self, *, language: Language | None = None) -> FetchedBundle:
        """Fetch this bundle.

        Shorthand for:

        .. code:: python

            bundle = await client.fetch_bundle(bundle_id)
        """
        return await self._state.fetch_bundle(self.id, language)

    async def store_item(self, *, language: Language | None = None) -> BundleStoreItem:
        """Fetch the store item for this bundle.

        Shorthand for:

        .. code:: python

            (item,) = await client.fetch_store_item(bundles=[bundle], language=language)
        """
        from .store import BundleStoreItem

        language = language or self._state.http.language
        (item,) = await self._state.fetch_store_info(bundle_ids=(self.id,), language=language)
        return BundleStoreItem(self._state, item, language)

    async def apps(self) -> list[PartialApp[None]]:
        """Fetch the bundle's apps."""
        fetched = await self.fetch()
        return fetched._apps

    async def packages(self) -> list[PartialPackage[None]]:
        """Fetch the bundle's packages."""
        fetched = await self.fetch()
        return fetched._packages

    async def redeem(self) -> None:
        """Redeem this bundle if it's a free-on-demand bundle."""
        await self._state.http.redeem_bundle(self.id)


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

    async def apps(self) -> list[PartialApp[None]]:
        return self._apps

    async def packages(self) -> list[PartialPackage[None]]:
        return self._packages
