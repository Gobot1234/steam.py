from __future__ import annotations

from typing import TYPE_CHECKING

from ...enums import Enum, Flags, IntEnum, classproperty

if TYPE_CHECKING:
    from typing_extensions import Self

__all__ = (
    "GCGoodbyeReason",
    "TradeResponse",
    "Mercenary",
    "ItemSlot",
    "WearLevel",
    "BackpackSortType",
    "ItemFlags",
    "ItemOrigin",
    "ItemQuality",
    "Part",
    "Spell",
    "Sheen",
    "Killstreak",
    "Attribute",
    "EMsg",
)


# fmt: off
class GCGoodbyeReason(IntEnum):
    GCGoingDown = 1
    NoSession   = 2


class TradeResponse(IntEnum):
    Accepted                        = 0
    Declined                        = 1
    TradeBannedInitiator            = 2
    TradeBannedTarget               = 3
    TargetAlreadyTrading            = 4
    Disabled                        = 5
    NotLoggedIn                     = 6
    Cancel                          = 7
    TooSoon                         = 8
    TooSoonPenalty                  = 9
    ConnectionFailed                = 10
    AlreadyTrading                  = 11
    AlreadyHasTradeRequest          = 12
    NoResponse                      = 13
    CyberCafeInitiator              = 14
    CyberCafeTarget                 = 15
    SchoolLabInitiator              = 16
    SchoolLabTarget                 = 16
    InitiatorBlockedTarget          = 18
    InitiatorNeedsVerifiedEmail     = 20
    InitiatorNeedsSteamGuard        = 21
    TargetAccountCannotTrade        = 22
    InitiatorSteamGuardDuration     = 23
    InitiatorPasswordResetProbation = 24
    InitiatorNewDeviceCooldown      = 25
    OKToDeliver                     = 50


class Mercenary(IntEnum):
    Scout    = 1
    Sniper   = 2
    Soldier  = 3
    Demoman  = 4
    Medic    = 5
    Heavy    = 6
    Pyro     = 7
    Spy      = 8
    Engineer = 9


class ItemSlot(IntEnum):
    Primary   = 0
    Secondary = 1
    Melee     = 2
    Sapper    = 4
    PDA       = 5
    PDA2      = 6
    Cosmetic1 = 7
    Cosmetic2 = 8
    Action    = 9
    Cosmetic3 = 10
    Taunt1    = 11
    Taunt2    = 12
    Taunt3    = 13
    Taunt4    = 14
    Taunt5    = 15
    Taunt6    = 16
    Taunt7    = 17
    Taunt8    = 18
    Misc      = 100  # these are not real but are used for BackPackItem.slot
    Gift      = 101
    CraftItem = 102


class WearLevel(Enum):
    FactoryNew    = "(Factory New)"
    MinimalWear   = "(Minimal Wear)"
    FieldTested   = "(Field-Tested)"
    WellWorn      = "(Well-Worn)"
    BattleScarred = "(Battle Scarred)"


class BackpackSortType(IntEnum):  # N.B only in game ones will actually work
    Name     = 1
    Defindex = 2
    Rarity   = 3
    Type     = 4
    Date     = 5
    Class    = 101
    Slot     = 102


# lifted from https://github.com/OthmanAba/TeamFortress2/blob/master/tf2_src/game/shared/econ/econ_item_constants.h
class ItemFlags(Flags):
    CannotTrade                                = 1 << 0
    CannotCraft                                = 1 << 1
    CanBeTradedByFreeAccounts                  = 1 << 2
    NotEcon                                    = 1 << 3
    """Items that cannot interact in the economy (can't be traded, gift-wrapped, crafted, etc.)"""
    PurchasedAfterStoreCraftabilityChanges2012 = 1 << 4
    """Cosmetic items coming from the store are now usable in crafting"""
    ForceBlueTeam                              = 1 << 5
    StoreItem                                  = 1 << 6
    Preview                                    = 1 << 7


class ItemOrigin(IntEnum):
    Invalid                        = -1
    Drop                           = 0
    Achievement                    = 1
    Purchased                      = 2
    Traded                         = 3
    Crafted                        = 4
    StorePromotion                 = 5
    Gifted                         = 6
    SupportGranted                 = 7
    FoundInCrate                   = 8
    Earned                         = 9
    ThirdPartyPromotion            = 10
    GiftWrapped                    = 11
    HalloweenDrop                  = 12
    PackageItem                    = 13
    Foreign                        = 14
    CDKey                          = 15
    CollectionReward               = 16
    PreviewItem                    = 17
    SteamWorkshopContribution      = 18
    PeriodicScoreReward            = 19
    MvMMissionCompletionReward     = 20
    MvMSquadSurplusReward          = 21
    RecipeOutput                   = 22
    QuestDrop                      = 23
    QuestLoanerItem                = 24
    TradeUp                        = 25
    ViralCompetitiveBetaPassSpread = 26
    Max                            = 27


class ItemQuality(IntEnum):
    Normal          = 0
    Genuine         = 1
    Vintage         = 3
    Rarity3         = 4
    Unusual         = 5
    Unique          = 6
    Community       = 7
    Valve           = 8
    SelfMade        = 9
    Customized      = 10
    Strange         = 11
    Completed       = 12
    Haunted         = 13
    Collectors      = 14
    DecoratedWeapon = 15


# class Paint(IntEnum):
#     An Air of Debonair = 0x654740
#     An Air of Debonair = 0x28394D
#     Balaclavas Are Forever = 0x3B1F23
#     Balaclavas Are Forever = 0x18233D
#     Cream Spirit = 0xC36C2D
#     Cream Spirit = 0xB88035
#     Operator's Overalls = 0x483838
#     Operator's Overalls = 0x384248
#     Team Spirit = 0xB8383B
#     Team Spirit = 0x5885A2
#     The Value of Teamwork = 0x803020
#     The Value of Teamwork = 0x256D8D
#     Waterlogged Lab Coat = 0xA89A8C
#     Waterlogged Lab Coat = 0x839FA3
#     A Color Similar to Slate = 0x2F4F4F
#     A Deep Commitment to Purple = 0x7D4071
#     A Distinctive Lack of Hue = 0x141414
#     A Mann's Mint = 0xBCDDB3
#     After Eight = 0x2D2D24
#     Aged Moustache Grey = 0x7E7E7E
#     An Extraordinary Abundance of Tinge = 0xE6E6E6
#     Australium Gold = 0xE7B53B
#     Color No. 216-190-216 = 0xD8BED8
#     Dark Salmon Injustice = 0xE9967A
#     Drably Olive = 0x808000
#     Indubitably Green = 0x729E42
#     Mann Co. Orange = 0xCF7336
#     Muskelmannbraun = 0xA57545
#     Noble Hatter's Violet = 0x51384A
#     Peculiarly Drab Tincture = 0xC5AF91
#     Pink as Hell = 0xFF69B4
#     Radigan Conagher Brown = 0x694D3A
#     The Bitter Taste of Defeat and Lime = 0x32CD32
#     The Color of a Gentlemann's Business Pants = 0xF0E68C
#     Ye Olde Rustic Colour = 0x7C6C57
#     Zepheniah's Gree = 0x424F3B


class Part(IntEnum):
    # Kills                              = 0
    # Ubers                              = 1
    KillAssists                        = 2
    # SentryKills                        = 3
    # SoddenVictims                      = 4
    # SpiesShocked                       = 5
    # HeadsTaken                         = 6
    # Humiliations                       = 7
    # GiftsGiven                         = 8
    # DeathsFeigned                      = 9
    ScoutsKilled                       = 10
    SnipersKilled                      = 11
    SoldiersKilled                     = 12
    DemomenKilled                      = 13
    HeaviesKilled                      = 14
    PyrosKilled                        = 15
    SpiesKilled                        = 16
    EngineersKilled                    = 17
    MedicsKilled                       = 18
    BuildingsDestroyed                 = 19
    ProjectilesReflected               = 20
    HeadshotKills                      = 21
    AirborneEnemyKills                 = 22
    GibKills                           = 23
    # BuildingsSapped                    = 24
    # TickleFightsWon                    = 25
    # OpponentsFlattened                 = 26
    KillsUnderAFullMoon                = 27
    Dominations                        = 28
    Revenges                           = 30
    PosthumousKills                    = 31
    TeammatesExtinguished              = 32
    CriticalKills                      = 33
    KillsWhileExplosiveJumping         = 34
    SappersDestroyed                   = 36
    CloakedSpiesKilled                 = 37
    MedicsKilledThatHaveFullÜberCharge = 38
    RobotsDestroyed                    = 39
    GiantRobotsDestroyed               = 40
    KillsWhileLowHealth                = 44
    KillsDuringHalloween               = 45
    RobotsKilledDuringHalloween        = 46
    DefenderKills                      = 47
    SubmergedEnemyKills                = 48
    # KillsWhileInvulnÜberCharged        = 49
    # FoodItemsEaten                     = 50
    # BannersDeployed                    = 51
    # SecondsCloaked                     = 58
    # HealthDispensedtoTeammates         = 59
    # TeammatesTeleported                = 60
    TanksDestroyed                     = 61
    LongDistanceKills                  = 62
    # KillEaterEvent_UniquePlayerKills   = 63
    # PointsScored                       = 64
    # DoubleDonks                        = 65
    # TeammatesWhipped                   = 66
    KillsduringVictoryTime             = 67
    RobotScoutsDestroyed               = 68
    RobotSpiesDestroyed                = 74
    TauntKills                         = 77
    UnusualWearingPlayerKills          = 78
    BurningPlayerKills                 = 79
    KillstreaksEnded                   = 80
    FreezecamTauntAppearances          = 81
    DamageDealt                        = 82
    FiresSurvived                      = 83
    AlliedHealingDone                  = 84
    PointBlankKills                    = 85
    # WrangledSentryKills                = 86
    Kills                              = 87
    FullHealthKills                    = 88
    TauntingPlayerKills                = 89
    # CarnivalKills                      = 90
    # CarnivalUnderworldKills            = 91
    # CarnivalGamesWon                   = 92
    NotCritnorMiniCritKills            = 93
    PlayerHits                         = 94
    Assists                            = 95
    # ContractsCompleted                 = 96
    Kills_                             = 97
    # ContractPoints                     = 98
    # ContractBonusPoints                = 99
    # TimesPerformed                     = 100
    # KillsAndAssistsduringInvasionEvent = 101
    # KillsAndAssistson2FortInvasion     = 102
    # KillsAndAssistsonProbed            = 103
    # KillsAndAssistsonByre              = 104
    # KillsAndAssistsonWatergate         = 105
    # SoulsCollected                     = 106
    # MerasmissionsCompleted             = 107
    # HalloweenTransmutesPerformed       = 108
    # PowerUpCanteensUsed                = 109
    # ContractPointsEarned               = 110
    # ContractPointsContributedToFriends = 111

class Spell(IntEnum):
    VoicesFromBelow         = 1006
    PumpkinBombs            = 1007
    HalloweenFire           = 1008
    Exorcism                = 1009
    PutrescentPigmentation  = 8900
    DieJob                  = 8901
    ChromaticCorruption     = 8902
    SpectralSpectrum        = 8903
    SinisterStaining        = 8904
    TeamSpiritFootprints    = 8914
    GangreenFootprints      = 8915
    CorpseGrayFootprints    = 8916
    ViolentVioletFootprints = 8917
    RottenOrangeFootprints  = 8918
    BruisedPurpleFootprints = 8919
    HeadlessHorseshoe       = 8920

    @classproperty
    def indices(cls: type[Self]) -> dict[int, dict[int, Spell]]:  # type: ignore
        return {
            1004: {
                0: cls.DieJob,
                1: cls.ChromaticCorruption,
                2: cls.PutrescentPigmentation,
                3: cls.SpectralSpectrum,
                4: cls.SinisterStaining,
            },
            1005: {
                1: cls.TeamSpiritFootprints,
                2: cls.HeadlessHorseshoe,
                3100495: cls.CorpseGrayFootprints,
                5322826: cls.ViolentVioletFootprints,
                8208497: cls.BruisedPurpleFootprints,
                8421376: cls.GangreenFootprints,
                13595446: cls.RottenOrangeFootprints,
            }
        }


class Sheen(IntEnum):
    TeamShine        = 1
    DeadlyDaffodil   = 2
    Manndarin        = 3
    MeanGreen        = 4
    AgonizingEmerald = 5
    VillainousViolet = 6
    HotRod           = 7


class Killstreak(IntEnum):
    FireHorns         = 2002
    CerebralDischarge = 2003
    Tornado           = 2004
    Flames            = 2005
    Singularity       = 2006
    Incinerator       = 2007
    HypnoBeam         = 2008


class Attribute(IntEnum):
    Paint         = 1031
    CustomTexture = 1051
    MakersMark    = 1053
    Killstreak    = 1094
    GiftedBy      = 2570
    Festivizer    = 2572


class EMsg(IntEnum):
    SOCreate                                    = 21
    SOUpdate                                    = 22
    SODestroy                                   = 23
    SOCacheSubscribed                           = 24
    SOCacheUnsubscribed                         = 25
    SOUpdateMultiple                            = 26
    SOCacheSubscriptionCheck                    = 27
    SOCacheSubscriptionRefresh                  = 28
    SOCacheSubscribedUpToDate                   = 29

    Base                                        = 1000
    SetSingleItemPosition                       = 1001
    Craft                                       = 1002
    CraftResponse                               = 1003
    Delete                                      = 1004
    VerifyCacheSubscription                     = 1005
    NameItem                                    = 1006
    UnlockCrate                                 = 1007
    UnlockCrateResponse                         = 1008
    PaintItem                                   = 1009
    PaintItemResponse                           = 1010
    GoldenWrenchBroadcast                       = 1011
    MOTDRequest                                 = 1012
    MOTDRequestResponse                         = 1013
    NameBaseItem                                = 1019
    NameBaseItemResponse                        = 1020
    CustomizeItemTexture                        = 1023
    CustomizeItemTextureResponse                = 1024
    UseItemRequest                              = 1025
    UseItemResponse                             = 1026
    RespawnPostLoadoutChange                    = 1029
    RemoveItemName                              = 1030
    RemoveItemPaint                             = 1031
    GiftWrapItem                                = 1032
    GiftWrapItemResponse                        = 1033
    DeliverGift                                 = 1034
    DeliverGiftResponseReceiver                 = 1036
    UnwrapGiftRequest                           = 1037
    UnwrapGiftResponse                          = 1038
    SetItemStyle                                = 1039
    UsedClaimCodeItem                           = 1040
    SortItems                                   = 1041
    LookupAccount                               = 1043
    LookupAccountResponse                       = 1044
    LookupAccountName                           = 1045
    LookupAccountNameResponse                   = 1046
    UpdateItemSchema                            = 1049
    RequestInventoryRefresh                     = 1050
    RemoveCustomTexture                         = 1051
    RemoveCustomTextureResponse                 = 1052
    RemoveMakersMark                            = 1053
    RemoveMakersMarkResponse                    = 1054
    RemoveUniqueCraftIndex                      = 1055
    RemoveUniqueCraftIndexResponse              = 1056
    SaxxyBroadcast                              = 1057
    BackpackSortFinished                        = 1058
    AdjustItemEquippedState                     = 1059
    CollectItem                                 = 1061
    ItemAcknowledged                            = 1062
    PresetsSelectPresetForClass                 = 1063
    PresetsSetItemPosition                      = 1064
    ReportAbuse                                 = 1065
    ReportAbuseResponse                         = 1066
    PresetsSelectPresetForClassReply            = 1067
    NameItemNotification                        = 1068
    ClientDisplayNotification                   = 1069
    ApplyStrangePart                            = 1070
    IncrementKillCountAttribute                 = 1071
    IncrementKillCountResponse                  = 1072
    RemoveStrangePart                           = 1073
    ResetStrangeScores                          = 1074
    GiftedItems                                 = 1075
    ApplyUpgradeCard                            = 1077
    RemoveUpgradeCard                           = 1078
    ApplyStrangeRestriction                     = 1079
    ClientRequestMarketData                     = 1080
    ClientRequestMarketDataResponse             = 1081
    ApplyXifier                                 = 1082
    ApplyXifierResponse                         = 1083
    TrackUniquePlayerPairEvent                  = 1084
    FulfillDynamicRecipeComponent               = 1085
    FulfillDynamicRecipeComponentResponse       = 1086
    SetItemEffectVerticalOffset                 = 1087
    SetHatEffectUseHeadOrigin                   = 1088
    ItemEaterRecharger                          = 1089
    ItemEaterRechargerResponse                  = 1090
    ApplyBaseItemXifier                         = 1091
    ApplyClassTransmogrifier                    = 1092
    ApplyHalloweenSpellbookPage                 = 1093
    RemoveKillStreak                            = 1094
    RemoveKillStreakResponse                    = 1095
    TFSpecificItemBroadcast                     = 1096
    IncrementKillCountAttributeMultiple         = 1097
    DeliverGiftResponseGiver                    = 1098
    SetItemPositions                            = 1100
    LookupMultipleAccountNames                  = 1101
    LookupMultipleAccountNamesResponse          = 1102
    TradingBase                                 = 1500
    TradingInitiateTradeRequest                 = 1501
    TradingInitiateTradeResponse                = 1502
    TradingStartSession                         = 1503
    TradingSessionClosed                        = 1509
    TradingCancelSession                        = 1510
    TradingInitiateTradeRequestResponse         = 1514
    ServerBrowserFavoriteServer                 = 1601
    ServerBrowserBlacklistServer                = 1602
    ServerRentalsBase                           = 1700
    ItemPreviewCheckStatus                      = 1701
    ItemPreviewStatusResponse                   = 1702
    ItemPreviewRequest                          = 1703
    ItemPreviewRequestResponse                  = 1704
    ItemPreviewExpire                           = 1705
    ItemPreviewExpireNotification               = 1706
    ItemPreviewItemBoughtNotification           = 1708
    DevNewItemRequest                           = 2001
    DevNewItemRequestResponse                   = 2002
    DevDebugRollLootRequest                     = 2003

    StoreGetUserData                            = 2500
    StoreGetUserDataResponse                    = 2501
    StorePurchaseFinalize                       = 2512
    StorePurchaseFinalizeResponse               = 2513
    StorePurchaseCancel                         = 2514
    StorePurchaseCancelResponse                 = 2515
    StorePurchaseQueryTxn                       = 2508
    StorePurchaseQueryTxnResponse               = 2509
    StorePurchaseInit                           = 2510
    StorePurchaseInitResponse                   = 2511
    GCToGCDirtySDOCache                         = 2516
    GCToGCDirtyMultipleSDOCache                 = 2517
    GCToGCUpdateSQLKeyValue                     = 2518
    GCToGCBroadcastConsoleCommand               = 2521
    ServerVersionUpdated                        = 2522
    ApplyAutograph                              = 2523
    GCToGCWebAPIAccountChanged                  = 2524
    RequestAnnouncements                        = 2525
    RequestAnnouncementsResponse                = 2526
    RequestPassportItemGrant                    = 2527
    ClientVersionUpdated                        = 2528
    ItemPurgatoryFinalizePurchase               = 2531
    ItemPurgatoryFinalizePurchaseResponse       = 2532
    ItemPurgatoryRefundPurchase                 = 2533
    ItemPurgatoryRefundPurchaseResponse         = 2534
    GCToGCPlayerStrangeCountAdjustments         = 2535
    RequestStoreSalesData                       = 2536
    RequestStoreSalesDataResponse               = 2537
    RequestStoreSalesDataUpToDateResponse       = 2538
    GCToGCPingRequest                           = 2539
    GCToGCPingResponse                          = 2540
    GCToGCGetUserSessionServer                  = 2541
    GCToGCGetUserSessionServerResponse          = 2542
    GCToGCGetUserServerMembers                  = 2543
    GCToGCGetUserServerMembersResponse          = 2544
    GCToGCGrantSelfMadeItemToAccount            = 2555
    GCToGCThankedByNewUser                      = 2556
    ShuffleCrateContents                        = 2557
    QuestObjectiveProgress                      = 2558
    QuestCompleted                              = 2559
    ApplyDuckToken                              = 2560
    QuestCompleteRequest                        = 2561
    QuestObjectivePointsChange                  = 2562
    QuestObjectiveRequestLoanerItems            = 2564
    QuestObjectiveRequestLoanerResponse         = 2565
    ApplyStrangeCountTransfer                   = 2566
    CraftCollectionUpgrade                      = 2567
    CraftHalloweenOffering                      = 2568
    QuestDiscardRequest                         = 2569
    RemoveGiftedBy                              = 2570
    RemoveGiftedByResponse                      = 2571
    RemoveFestivizer                            = 2572
    RemoveFestivizerResponse                    = 2573
    CraftCommonStatClock                        = 2574


    PingRequest                                 = 3001
    PingResponse                                = 3002

    ClientWelcome                               = 4004
    ServerWelcome                               = 4005
    ClientHello                                 = 4006
    ServerHello                                 = 4007
    ClientGoodbye                               = 4008
    ServerGoodbye                               = 4009

    SystemMessage                               = 4001
    ReplicateConVars                            = 4002
    ConVarUpdated                               = 4003
    InviteToParty                               = 4501
    InvitationCreated                           = 4502
    PartyInviteResponse                         = 4503
    KickFromParty                               = 4504
    LeaveParty                                  = 4505
    ServerAvailable                             = 4506
    ClientConnectToServer                       = 4507
    GameServerInfo                              = 4508
    Error                                       = 4509
    ReplayUploadedToYouTube                     = 4510
    LANServerAvailable                          = 4511

    ReportWarKill                               = 5001
    VoteKickBanPlayer                           = 5018
    VoteKickBanPlayerResult                     = 5019
    FreeTrialChooseMostHelpfulFriend            = 5022
    RequestTF2Friends                           = 5023
    RequestTF2FriendsResponse                   = 5024
    ReplaySubmitContestEntry                    = 5026
    ReplaySubmitContestEntryResponse            = 5027
    SaxxyAwarded                                = 5029
    FreeTrialThankedBySomeone                   = 5028
    FreeTrialThankedSomeone                     = 5030
    FreeTrialConvertedToPremium                 = 5031
    CoachingAddToCoaches                        = 5200
    CoachingAddToCoachesResponse                = 5201
    CoachingRemoveFromCoaches                   = 5202
    CoachingRemoveFromCoachesResponse           = 5203
    CoachingFindCoach                           = 5204
    CoachingFindCoachResponse                   = 5205
    CoachingAskCoach                            = 5206
    CoachingAskCoachResponse                    = 5207
    CoachingCoachJoinGame                       = 5208
    CoachingCoachJoining                        = 5209
    CoachingCoachJoined                         = 5210
    CoachingLikeCurrentCoach                    = 5211
    CoachingRemoveCurrentCoach                  = 5212
    CoachingAlreadyRatedCoach                   = 5213
    DuelRequest                                 = 5500
    DuelResponse                                = 5501
    DuelResults                                 = 5502
    DuelStatus                                  = 5503
    HalloweenReservedItem                       = 5607
    HalloweenGrantItem                          = 5608
    HalloweenGrantItemResponse                  = 5609
    HalloweenServerBossEvent                    = 5612
    HalloweenMerasmus2012                       = 5613
    HalloweenUpdateMerasmusLootLevel            = 5614
    GameServerLevelInfo                         = 5700
    GameServerAuthChallenge                     = 5701
    GameServerAuthChallengeResponse             = 5702
    GameServerCreateIdentity                    = 5703
    GameServerCreateIdentityResponse            = 5704
    GameServerList                              = 5705
    GameServerListResponse                      = 5706
    GameServerAuthResult                        = 5707
    GameServerResetIdentity                     = 5708
    GameServerResetIdentityResponse             = 5709
    ClientUseServerModificationItem             = 5710
    ClientUseServerModificationItemResponse     = 5711
    GameServerUseServerModificationItem         = 5712
    GameServerUseServerModificationItemResponse = 5713
    GameServerServerModificationItemExpired     = 5714
    GameServerModificationItemState             = 5715
    GameServerAckPolicy                         = 5716
    GameServerAckPolicyResponse                 = 5717
    QPScoreServers                              = 5800
    QPScoreServersResponse                      = 5801
    QPPlayerJoining                             = 5802
    GameMatchSignOut                            = 6204
    CreateOrUpdateParty                         = 6233
    AbandonCurrentGame                          = 6235
    ForceSOCacheResend                          = 6237
    RequestChatChannelList                      = 6260
    RequestChatChannelListResponse              = 6261
    ReadyUp                                     = 6270
    KickedFromMatchmakingQueue                  = 6271
    LeaverDetected                              = 6272
    LeaverDetectedResponse                      = 6287
    PlayerFailedToConnect                       = 6288
    ExitMatchmaking                             = 6289
    AcceptInvite                                = 6291
    AcceptInviteResponse                        = 6292
    MatchmakingProgress                         = 6293
    MvMVictoryInfo                              = 6294
    GameServerMatchmakingStatus                 = 6295
    CreateOrUpdatePartyReply                    = 6296
    MvMVictory                                  = 6297
    MvMVictoryReply                             = 6298
    GameServerKickingLobby                      = 6299
    LeaveGameAndPrepareToJoinParty              = 6300
    RemovePlayerFromLobby                       = 6301
    SetLobbySafeToLeave                         = 6302
    UpdatePeriodicEvent                         = 6400
    ClientVerificationChallenge                 = 6500
    ClientVerificationChallengeResponse         = 6501
    ClientVerificationVerboseResponse           = 6502
    ClientSetItemSlotAttribute                  = 6503
    PlayerSkillRatingAdjustment                 = 6504
    WarIndividualUpdate                         = 6505
    WarJoinWar                                  = 6506
    WarRequestGlobalStats                       = 6507
    WarGlobalStatsResponse                      = 6508
    WorldStatusBroadcast                        = 6518
    DevGrantWarKill                             = 10001
