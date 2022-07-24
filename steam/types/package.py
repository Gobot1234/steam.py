"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""


from typing_extensions import TypedDict


class FetchedPackageApp(TypedDict):
    id: int
    name: str


class FetchedPackagePrice(TypedDict):
    currency: str
    initial: int
    final: int
    discount_percent: int
    individual: int


class FetchedPackagePlatform(TypedDict):
    windows: bool
    mac: bool
    linux: bool


class FetchedPackageController(TypedDict):
    full_gamepad: bool


class FetchedPackageReleaseDate(TypedDict):
    coming_soon: bool
    date: str


class FetchedPackage(TypedDict):
    packageid: int
    name: str
    page_content: str
    page_image: str
    header_image: str
    small_logo: str
    apps: list[FetchedPackageApp]
    price: FetchedPackagePrice
    platforms: FetchedPackagePlatform
    controller: FetchedPackageController
    release_date: FetchedPackageReleaseDate
