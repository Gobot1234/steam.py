"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""


from typing_extensions import TypedDict


class FetchedPackage(TypedDict):
    packageid: int
    name: str
    appids: list[int]
    localized_langs: list[int]
    formatted_orig_price: str
    orig_price_cents: int
    formatted_final_price: str
    release_date: str
    available_windows: bool
    available_mac: bool
    available_linux: bool
    support_vrhmd: bool
    support_vrhmd_only: bool
    creator_clan_ids: list[int]
    final_price_cents: int
    coming_soon: bool
    no_main_cap: bool
    deck_compatibility_category: int
    discount_percent: int
    discount_end_rtime: int
    header_image_url: str
    main_capsule: str
    library_asset: str
