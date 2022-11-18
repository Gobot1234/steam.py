"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from typing import TypedDict

from .id import ID32, AppID, BundleID, PackageID


class Bundle(TypedDict):
    bundleid: BundleID
    name: str
    packageids: list[PackageID]
    appids: list[AppID]
    header_image_url: str
    main_capsule: str
    initial_price: int
    final_price: int
    formatted_orig_price: str
    formatted_final_price: str
    discount_percent: int
    available_windows: bool
    available_mac: bool
    available_linux: bool
    support_vrhmod: bool
    support_vrhmod_only: bool
    creator_clan_ids: list[ID32]
    localized_langs: list[int]
    coming_soon: bool
    library_Asset: str
    no_main_cap: bool
    deck_compatibility_category: int
