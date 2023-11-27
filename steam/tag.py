"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic

from typing_extensions import TypeVar

from . import utils
from ._const import URL, impl_eq_via_id

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from .enums import Language
    from .state import ConnectionState
    from .store import AppStoreItem

__all__ = (
    "Category",
    "StoreCategory",
    "Genre",
    "Tag",
    "StoreTag",
)

NameT = TypeVar("NameT", bound=str | None, default=str | None, covariant=True)


@impl_eq_via_id
class Category(Generic[NameT]):
    __slots__ = ("_state", "id", "name")

    def __init__(self, _state: ConnectionState, id: int, name: NameT = None):
        self._state = _state
        self.id = id
        self.name = name

    async def fetch(self, *, language: Language | None = None) -> StoreCategory:
        """Fetches the category."""
        (item,) = await self._state.fetch_app_categories(self.id, language=language)  # TODO asset handling?
        return StoreCategory(self._state, item.id, item.name, item.visible)

    @property
    def url(self: Category[str]) -> str:
        """The URL of the category on the Steam Store."""
        return str(URL.STORE / f"category/{self.name.lower()}")

    # not sure if worth implementing if it only returns some https://github.com/Revadike/InternalSteamWebAPI/wiki/Get-Apps-In-Category
    # async def apps(self) -> list[Store]:
    #     raise NotImplementedError


# GetStoreCategoriesRequest
class AllCategoriesCategory(Category[str]):
    __slots__ = ()
    # f type: EStoreCategoryType
    internal_name: str
    display_name: str
    # image: Asset
    visible: bool


class StoreCategory(Category[str]):
    __slots__ = ("visible",)

    def __init__(self, state: ConnectionState, id: int, name: str, visible: bool):
        super().__init__(state, id, name)
        self.visible = visible


@impl_eq_via_id
class Genre(Generic[NameT]):
    __slots__ = ("_state", "id", "name")

    def __init__(self, _state: ConnectionState, id: int, name: NameT = None):
        self._state = _state
        self.id = id
        self.name = name

    @utils.todo
    async def fetch(self) -> StoreGenre:  # not sure how to even fetch one
        raise NotImplementedError

    # not sure if worth implementing if it only returns some https://github.com/Revadike/InternalSteamWebAPI/wiki/Get-Apps-In-Genre
    # async def apps(self) -> list[Store]:
    #     raise NotImplementedError


@dataclass(slots=True)
class StoreGenre(Genre[str]):
    ...


@impl_eq_via_id
class Tag(Generic[NameT]):
    __slots__ = ("_state", "id", "name")

    def __init__(self, _state: ConnectionState, id: int, name: NameT = None):
        self._state = _state
        self.id = id
        self.name = name

    @property
    def url(self: Tag[str]) -> str:
        """The URL of the tag on the Steam Store."""
        return str(URL.STORE / f"tag/{self.name}")

    async def fetch(self) -> StoreTag:
        """Fetches the tag."""
        (item,) = await self._state.fetch_app_tag(self.id)
        return StoreTag(self._state, item.id, item.name, item.visible)

    @utils.todo
    async def apps(self) -> AsyncGenerator[AppStoreItem, None]:
        raise NotImplementedError  # TODO store.QueryRequest
        yield


class StoreTag(Tag[str]):
    __slots__ = ("visible",)

    def __init__(self, state: ConnectionState, id: int, name: str, visible: bool):
        super().__init__(state, id, name)
        self.visible = visible


# https://store.steampowered.com/tagdata/populartags/english
class PopularTag(Tag[str]):
    ...
