"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .vdf import TypedVDFDict, VDFBool, VDFDict, VDFInt, VDFList

if TYPE_CHECKING:
    from typing import Literal

    from multidict import MultiDict
    from typing_extensions import NotRequired, Required


class AppInfo(TypedVDFDict):
    appid: str
    common: Common
    extended: NotRequired[Extended]
    config: VDFDict
    depots: Depot | VDFDict
    ufs: MultiDict[VDFInt]
    install: MultiDict[Any]
    sysreqs: MultiDict[MultiDict[Any]]
    localization: MultiDict[MultiDict[VDFDict]]
    albummetadata: MultiDict[Any]


class Common(TypedVDFDict, total=False):
    name: Required[str]
    type: Required[str]
    has_adult_content: VDFBool
    has_adult_content_violence: VDFBool
    has_adult_content_sex: VDFBool
    content_descriptors: MultiDict[str]
    market_presence: VDFBool
    workshop_visible: VDFBool
    community_hub_visible: VDFBool
    community_visible_stats: VDFBool
    controller_support: Literal["full", "partial", "none"]
    associations: VDFList[CommonAssociations]
    category: MultiDict[VDFBool]  # category_{id}: "1" cause lol valve
    languages: MultiDict[VDFBool]
    supported_languages: MultiDict[LanguageSupport] | str  # This can occasionally be an empty string
    steam_release_date: str
    review_score: str
    review_percentage: str
    oslist: str
    icon: str
    logo: str
    parent: VDFInt
    clienticns: str
    clienticon: str
    clienttga: str
    gameid: str
    genres: VDFList[VDFInt]
    store_tags: VDFList[VDFInt]
    header_image: MultiDict[str]
    library_assets: CommonLibraryAssets
    linuxclienticon: str
    logo_small: str
    metacritic_fullurl: str
    metacritic_name: str
    metacritic_score: VDFInt
    metacritic_url: str
    primary_genre: str
    review_percentage: str
    review_score: str
    small_capsule: MultiDict[str]
    steam_deck_compatibility: CommonSteamDeckCompatibility
    steam_release_date: str
    store_asset_mtime: str
    store_tags: VDFList[VDFInt]
    sortas: str
    name_localized: Any
    releasestate: str
    original_release_date: str
    exfgls: str
    eulas: VDFList[MultiDict[Any]]
    osarch: str
    osextended: str
    releasestatesteamchina: str
    requireskbmouse: str
    steamchinaapproved: str
    name_linux: str
    controllervr: MultiDict[VDFBool]
    playareavr: MultiDict[Any]
    review_percentage_bombs: str
    review_score_bombs: str
    freeondemand: VDFBool
    visibleonlyonavailableplatforms: str
    app_retired_publisher_request: str
    mastersubs_granting_app: str
    driverversion: str
    openvrsupport: str
    othervrsupport: str
    othervrsupport_rift_13: str
    section_type: str
    kbmousegame: str
    openvr_action_manifest_path: str
    hideinfriendslist: str
    systemprofile: str
    steam_deck_blog_url: str
    onquitdemomsg: str
    onlyvrsupport: str
    openvr_controller_bindings: VDFList[MultiDict[Any]]
    osvrsupport: str
    releasestateoverride: str
    releasestateoverridecountries: str
    releasestateoverrideinverse: str
    restricted_countries: str


class CommonAssociations(TypedVDFDict):
    name: str
    type: str


class CommonLibraryAssets(TypedVDFDict):
    library_capsule: str
    library_hero: str
    library_logo: str
    logo_position: CommonLogoPosition


class CommonLogoPosition(TypedVDFDict):
    height_pct: str
    pinned_position: str
    width_pct: str


class CommonSteamDeckCompatibility(TypedVDFDict):
    category: str
    configuration: CommonConfiguration
    test_timestamp: str
    tested_build_id: str
    tests: VDFList[MultiDict[Any]]


class CommonConfiguration(TypedVDFDict):
    gamescope_frame_limiter_not_supported: str
    non_deck_display_glyphs: str
    primary_player_is_controller_slot_0: str
    recommended_runtime: str
    requires_h264: str
    requires_internet_for_setup: str
    requires_internet_for_singleplayer: str
    requires_manual_keyboard_invoke: str
    requires_non_controller_launcher_nav: str
    small_text: str
    supported_input: str


class Extended(TypedVDFDict, total=False):
    isfreeapp: VDFBool
    homepage: str
    demoofappid: VDFInt
    developer: str
    publisher: str
    dependantonapp: str
    developer_url: str
    gamedir: str
    icon: str
    icon2: str
    minclientversion: str
    order: str
    primarycache: str
    serverbrowsername: str
    vacmacmodulecache: str
    vacmodulecache: str
    vacmodulefilename: str
    gamemanualurl: str
    hdaddon: str
    listofdlc: str
    initialsellpage: str
    no_revenue_accumulation: str
    preloadsellpage: str
    releasedpage: str
    sellpage: str
    state: str
    checkpkgstate: str
    noservers: str
    sourcegame: str
    visibleonlywhensubscribed: str
    disableoverlay: str
    installscript: str
    validoslist: str
    disableshaderreporting: str
    deckresolutionoverride: str
    directx_minver: str
    supports64bit: str
    dedicatedserverfolder: str
    video: str
    languages: str
    languages_macos: str
    preloadunlocktime: str
    requiressse: str
    dependantonapppreventrecurseholes: str
    aliases: str
    loadallbeforelaunch: str
    primarycache_linux: str
    visibleonlywheninstalled: str
    dlcavailableonstore: str
    guideappid: str
    installscript_macos: str
    otten: str
    installscriptosx: str
    languages_mac: str
    thirdpartycdkey: str
    minclientversion_pw_csgo: str
    primarycache_macos: str
    preloadcountdowntext1: str
    preloadcountdowntext2: str
    preloadcountdowntext3: str
    preloadcountdowntexttime: str
    preloadcountdownurl: str
    primarycache_mac: str
    legacykeydisklocation: str
    legacykeyregistrationmethod: str
    legacykeyregistrylocation: str
    showcdkeyonlaunch: str
    supportscdkeycopytoclipboard: str
    cpu_min: str
    cpu_min_amd: str
    ram_min: str
    os_min: str
    dlcpurchasefromingame: str
    hasexternalregistrationurl: str
    legacykeylinkedexternally: str
    showcdkeyinmenu: str
    externalsubscriptionurl2: str
    existingretail: str
    launcheula: str
    cwdoverride: str
    mustownapptopurchase: str
    hadthirdpartycdkey: str
    inhibitautoversionroll: str
    retailautostart: str
    suppressims: str
    g4w_gdf: str
    g4w_type: str
    requirentfspartition: str
    existingretail1: str
    requiredappid: str
    onquitdemomsg: str
    nodefaultenglishcontent: str
    launchredirect: str
    disableoverlay_macos: str
    isconverteddlc: str
    musicalbumavailableonstore: str
    musicalbumforappid: str
    sdk_notownedbydefault: str
    canskipinstallappchooser: str
    allowelevation: str
    dlcforappid: str
    ismediafile: str
    mediafiletype: str
    launcheula_macos: str
    vrheadsetstreaming: str
    absolutemousecoordinates: str
    additional_dependencies: VDFList[VDFBool]
    installscript_linux: str
    allowmicrotxnfromrestrictedcountries: str
    microtxnrestrictedcountries: str
    disablestreaming: str
    foo: str
    anti_cheat_support_url: str
    demoforappid: str
    remoteplaytogethertestingbranches: str
    disableosxdrmloader: str
    overlaywindowblacklist: str
    disableoverlayinjection: str
    disableoverlayinjection_linux: str
    betaforappid: str


class Manifest(TypedVDFDict, total=False):
    gid: Required[VDFInt]
    size: VDFInt
    download: VDFInt


class Depot(TypedVDFDict, total=False):
    name: str
    config: Required[MultiDict[str]]
    manifests: MultiDict[VDFInt | Manifest]  # {branch name: id}
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


class LanguageSupport(TypedVDFDict):
    supported: NotRequired[str]
    full_audio: NotRequired[str]
    subtitles: NotRequired[str]
