"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._const import URL

if TYPE_CHECKING:
    from .models import CDNAsset
    from .protobufs.store import EStoreCategoryType
    from .state import ConnectionState


@dataclass(slots=True)
class PartialCategory:
    _state: ConnectionState
    id: int

    async def fetch(self) -> StoreCategory:
        ...


@dataclass(slots=True)
class FetchedAppCategory(PartialCategory):
    name: str


@dataclass(slots=True)
class StoreCategory(PartialCategory):
    name: str
    type: EStoreCategoryType
    display_name: str
    image: CDNAsset


@dataclass(slots=True)
class PartialGenre:
    _state: ConnectionState
    id: int

    # TODO
    async def fetch(self) -> StoreGenre:
        ...


@dataclass(slots=True)
class StoreGenre(PartialGenre):
    name: str


@dataclass(slots=True)
class PartialTag:
    _state: ConnectionState
    id: int

    async def fetch(self) -> StoreTag:
        (item,) = await self._state.fetch_app_tag(self.id)
        return StoreTag(self._state, item.id, item.visible, item.name, str(URL.STORE / item.store_url_path))


@dataclass(slots=True)
class StoreTag(PartialTag):
    visible: bool
    name: str
    url: str


class PopularTag(PartialTag):
    ...
