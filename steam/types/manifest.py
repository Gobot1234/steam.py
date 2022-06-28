"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import Any

from multidict import MultiDict
from typing_extensions import Literal, NotRequired, Required

from .vdf import TypedVDFDict, VDFDict, VDFInt, VDFList


class GameInfo(TypedVDFDict):
    appid: str
    common: Common
    extended: NotRequired[Extended]
    config: VDFDict
    depots: Depot | VDFDict
    ufs: MultiDict[VDFInt]
    sysreqs: MultiDict[MultiDict[Any]]
    localization: MultiDict[MultiDict[VDFDict]]


Bools = Literal["0", "1"]


class Common(TypedVDFDict, total=False):
    name: Required[str]
    type: Required[str]
    has_adult_content: Bools
    has_adult_content_violence: Bools
    market_presence: Bools
    workshop_visible: Bools
    community_hub_visible: Bools
    community_visible_stats: Bools
    controller_support: Literal["full", "partial", "none"]
    associations: VDFList[CommonAssociations]
    languages: MultiDict[Bools]
    steam_release_date: str
    review_score: str
    review_percentage: str
    oslist: str
    icon: str
    logo: str
    parent: int


class CommonAssociations(TypedVDFDict):
    name: str
    type: str


class Extended(TypedVDFDict, total=False):
    isfreeapp: Bools
    listofdlc: str
    homepage: str


class Depot(TypedVDFDict, total=False):
    name: str
    config: Required[MultiDict[str]]
    manifests: MultiDict[VDFInt]  # {branch name: id}
    encryptedmanifests: MultiDict[MultiDict[VDFInt]]  # {branch name: {encrypted_gid2: VDFInt}}
    branches: MultiDict[Branch]
    maxsize: VDFInt
    depotfromapp: VDFInt
    sharedinstall: bool
    system_defined: bool


class Branch(TypedVDFDict):
    buildid: VDFInt
    timeupdated: VDFInt
    pwdrequired: NotRequired[bool]
    description: NotRequired[str]


class PackageInfo(TypedVDFDict):
    packageid: int
    billingtype: int
    licensetype: int
    status: int
    extended: ExtendedPackageInfo
    appids: VDFList[int]
    depotids: VDFList[int]
    appitems: VDFList[int]


class ExtendedPackageInfo(TypedVDFDict):
    excludefromsharing: NotRequired[int]
    allowpurchasefromrestrictedcountries: NotRequired[bool]
    purchaserestrictedcountries: NotRequired[str]
