"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from collections.abc import Mapping

from typing_extensions import Self

from ...enums import Flags, IntEnum, classproperty

__all__ = (
    "ItemQuality",
    "ItemFlags",
    "ItemOrigin",
    "Rank",
)

# fmt: off
class ItemCustomizationNotification(IntEnum):
    NameItem              = 1006
    UnlockCrate           = 1007
    XRayItemReveal        = 1008
    XRayItemClaim         = 1009
    CasketTooFull         = 1011
    CasketContents        = 1012
    CasketAdded           = 1013
    CasketRemoved         = 1014
    CasketInvFull         = 1015
    NameBaseItem          = 1019
    RemoveItemName        = 1030
    RemoveSticker         = 1053
    ApplySticker          = 1086
    StatTrakSwap          = 1088
    ActivateFanToken      = 9178
    ActivateOperationCoin = 9179
    GraffitiUnseal        = 9185
    GenerateSouvenir      = 9204


# All 3 lifted from
# https://github.com/perilouswithadollarsign/cstrike15_src/blob/f82112a2388b841d72cb62ca48ab1846dfcc11c8/game/shared/econ/econ_item_constants.h
class ItemQuality(IntEnum):
    Undefined  = -1
    Normal     = 0
    Genuine    = 1
    Vintage    = 2
    Unusual    = 3
    Unique     = 4
    Community  = 5
    Developer  = 6
    SelfMade   = 7
    Customised = 8
    Strange    = 9
    Completed  = 10
    Haunted    = 11
    Tournament = 12
    Favoured   = 13
    Max        = 14


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
    Invalid                   = -1
    Drop                      = 0
    Achievement               = 1
    Purchased                 = 2
    Traded                    = 3
    Crafted                   = 4
    StorePromotion            = 5
    Gifted                    = 6
    SupportGranted            = 7
    FoundInCrate              = 8
    Earned                    = 9
    ThirdPartyPromotion       = 10
    GiftWrapped               = 11
    HalloweenDrop             = 12
    PackageItem               = 13
    Foreign                   = 14
    CDKey                     = 15
    CollectionReward          = 16
    PreviewItem               = 17
    SteamWorkshopContribution = 18
    PeriodicScoreReward       = 19
    Recycling                 = 20
    TournamentDrop            = 21
    StockItem                 = 22
    QuestReward               = 23
    LevelUpReward             = 24
    Max                       = 25



class Rank(IntEnum):
    NotRanked                   = 0
    SilverI                     = 1
    SilverII                    = 2
    SilverIII                   = 3
    SilverIV                    = 4
    SilverElite                 = 5
    SilverEliteMaster           = 6
    GoldNovaI                   = 7
    GoldNovaII                  = 8
    GoldNovaIII                 = 9
    GoldNovaMaster              = 10
    MasterGuardianI             = 11
    MasterGuardianII            = 12
    MasterGuardianElite         = 13
    DistinguishedMasterGuardian = 14
    LegendaryEagle              = 15
    LegendaryEagleMaster        = 16
    SupremeMasterFirstClass     = 17
    TheGlobalElite              = 18

    @classproperty
    def DISPLAY_NAMES(cls: type[Self]) -> Mapping[Self, str]:  # type: ignore
        return {
            cls.NotRanked:                   "Not Ranked",
            cls.SilverI:                     "Silver I",
            cls.SilverII:                    "Silver II",
            cls.SilverIII:                   "Silver III",
            cls.SilverIV:                    "Silver IV",
            cls.SilverElite:                 "Silver Elite",
            cls.SilverEliteMaster:           "Silver Elite Master",
            cls.GoldNovaI:                   "Gold Nova I",
            cls.GoldNovaII:                  "Gold Nova II",
            cls.GoldNovaIII:                 "Gold Nova III",
            cls.GoldNovaMaster:              "Gold Nova Master",
            cls.MasterGuardianI:             "Master Guardian I",
            cls.MasterGuardianII:            "Master Guardian II",
            cls.MasterGuardianElite:         "Master Guardian Elite",
            cls.DistinguishedMasterGuardian: "Distinguished Master Guardian",
            cls.LegendaryEagle:              "Legendary Eagle",
            cls.LegendaryEagleMaster:        "Legendary Eagle Master",
            cls.SupremeMasterFirstClass:     "Supreme Master First Class",
            cls.TheGlobalElite:              "The Global Elite",
        }

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAMES[self]


class EMsg(IntEnum):
    # ESOMsg
    SOCreate                               = 21
    SOUpdate                               = 22
    SODestroy                              = 23
    SOCacheSubscribed                      = 24
    SOCacheUnsubscribed                    = 25
    SOUpdateMultiple                       = 26
    SOCacheSubscriptionCheck               = 27
    SOCacheSubscriptionRefresh             = 28

    # EGCItemMsg
    EGCItemMsgBase                         = 1000
    SetItemPosition                        = 1001
    Craft                                  = 1002
    CraftResponse                          = 1003
    Delete                                 = 1004
    VerifyCacheSubscription                = 1005
    NameItem                               = 1006
    UnlockCrate                            = 1007
    UnlockCrateResponse                    = 1008
    PaintItem                              = 1009
    PaintItemResponse                      = 1010
    GoldenWrenchBroadcast                  = 1011
    MOTDRequest                            = 1012
    MOTDRequestResponse                    = 1013
    NameBaseItem                           = 1019
    NameBaseItemResponse                   = 1020
    CustomizeItemTexture                   = 1023
    CustomizeItemTextureResponse           = 1024
    UseItemRequest                         = 1025
    UseItemResponse                        = 1026
    RemoveItemName                         = 1030
    RemoveItemPaint                        = 1031
    GiftWrapItem                           = 1032
    GiftWrapItemResponse                   = 1033
    DeliverGift                            = 1034
    DeliverGiftResponseGiver               = 1035
    DeliverGiftResponseReceiver            = 1036
    UnwrapGiftRequest                      = 1037
    UnwrapGiftResponse                     = 1038
    SetItemStyle                           = 1039
    UsedClaimCodeItem                      = 1040
    SortItems                              = 1041
    LookupAccount                          = 1043
    LookupAccountResponse                  = 1044
    LookupAccountName                      = 1045
    LookupAccountNameResponse              = 1046
    UpdateItemSchema                       = 1049
    RemoveCustomTexture                    = 1051
    RemoveCustomTextureResponse            = 1052
    RemoveMakersMark                       = 1053
    RemoveMakersMarkResponse               = 1054
    RemoveUniqueCraftIndex                 = 1055
    RemoveUniqueCraftIndexResponse         = 1056
    SaxxyBroadcast                         = 1057
    BackpackSortFinished                   = 1058
    AdjustItemEquippedState                = 1059
    CollectItem                            = 1061
    PresetsSelectPresetForClass            = 1063
    PresetsSetItemPosition                 = 1064
    ReportAbuse                            = 1065
    ReportAbuseResponse                    = 1066
    PresetsSelectPresetForClassReply       = 1067
    NameItemNotification                   = 1068
    ApplyConsumableEffects                 = 1069
    ConsumableExhausted                    = 1070
    ShowItemsPickedUp                      = 1071
    ClientDisplayNotification              = 1072
    ApplyStrangePart                       = 1073
    IncrementKillCountAttribute            = 1074
    IncrementKillCountResponse             = 1075
    ApplyPennantUpgrade                    = 1076
    SetItemPositions                       = 1077
    ApplyEggEssence                        = 1078
    NameEggEssenceResponse                 = 1079
    PaintKitItem                           = 1080
    PaintKitBaseItem                       = 1081
    PaintKitItemResponse                   = 1082
    GiftedItems                            = 1083
    UnlockItemStyle                        = 1084
    UnlockItemStyleResponse                = 1085
    ApplySticker                           = 1086
    ItemAcknowledged                       = 1087
    StatTrakSwap                           = 1088
    UserTrackTimePlayedConsecutively       = 1089
    ItemCustomizationNotification          = 1090
    ModifyItemAttribute                    = 1091
    CasketItemAdd                          = 1092
    CasketItemExtract                      = 1093
    CasketItemLoadContents                 = 1094
    TradingBase                            = 1500
    TradingInitiateTradeRequest            = 1501
    TradingInitiateTradeResponse           = 1502
    TradingStartSession                    = 1503
    TradingSetItem                         = 1504
    TradingRemoveItem                      = 1505
    TradingUpdateTradeInfo                 = 1506
    TradingSetReadiness                    = 1507
    TradingReadinessResponse               = 1508
    TradingSessionClosed                   = 1509
    TradingCancelSession                   = 1510
    TradingTradeChatMsg                    = 1511
    TradingConfirmOffer                    = 1512
    TradingTradeTypingChatMsg              = 1513
    ServerBrowserFavoriteServer            = 1601
    ServerBrowserBlacklistServer           = 1602
    ServerRentalsBase                      = 1700
    ItemPreviewCheckStatus                 = 1701
    ItemPreviewStatusResponse              = 1702
    ItemPreviewRequest                     = 1703
    ItemPreviewRequestResponse             = 1704
    ItemPreviewExpire                      = 1705
    ItemPreviewExpireNotification          = 1706
    ItemPreviewItemBoughtNotification      = 1707
    DevNewItemRequest                      = 2001
    DevNewItemRequestResponse              = 2002
    DevPaintKitDropItem                    = 2003
    StoreGetUserData                       = 2500
    StoreGetUserDataResponse               = 2501
    StorePurchaseFinalize                  = 2504
    StorePurchaseFinalizeResponse          = 2505
    StorePurchaseCancel                    = 2506
    StorePurchaseCancelResponse            = 2507
    StorePurchaseQueryTxn                  = 2508
    StorePurchaseQueryTxnResponse          = 2509
    StorePurchaseInit                      = 2510
    StorePurchaseInitResponse              = 2511
    BannedWordListRequest                  = 2512
    BannedWordListResponse                 = 2513
    GCToGCBannedWordListBroadcast          = 2514
    GCToGCBannedWordListUpdated            = 2515
    GCToGCDirtySDOCache                    = 2516
    GCToGCDirtyMultipleSDOCache            = 2517
    GCToGCUpdateSQLKeyValue                = 2518
    GCToGCIsTrustedServer                  = 2519
    GCToGCIsTrustedServerResponse          = 2520
    GCToGCBroadcastConsoleCommand          = 2521
    ServerVersionUpdated                   = 2522
    ApplyAutograph                         = 2523
    GCToGCWebAPIAccountChanged             = 2524
    RequestAnnouncements                   = 2525
    RequestAnnouncementsResponse           = 2526
    RequestPassportItemGrant               = 2527
    ClientVersionUpdated                   = 2528

    # EGCBaseClientMsg
    ClientWelcome                          = 4004
    ServerWelcome                          = 4005
    ClientHello                            = 4006
    ServerHello                            = 4007
    ClientConnectionStatus                 = 4009
    ServerConnectionStatus                 = 4010

    # ECsgoGCMsg
    ECsgoGCMsgBase                         = 9100
    MatchmakingStart                       = 9101
    MatchmakingStop                        = 9102
    MatchmakingClient2ServerPing           = 9103
    MatchmakingGC2ClientUpdate             = 9104
    MatchmakingGC2ServerReserve            = 9105
    MatchmakingServerReservationResponse   = 9106
    MatchmakingGC2ClientReserve            = 9107
    MatchmakingServerRoundStats            = 9108
    MatchmakingClient2GCHello              = 9109
    MatchmakingGC2ClientHello              = 9110
    MatchmakingServerMatchEnd              = 9111
    MatchmakingGC2ClientAbandon            = 9112
    MatchmakingServer2GCKick               = 9113
    MatchmakingGC2ServerConfirm            = 9114
    MatchmakingGCOperationalStats          = 9115
    MatchmakingGC2ServerRankUpdate         = 9116
    MatchmakingOperator2GCBlogUpdate       = 9117
    ServerNotificationForUserPenalty       = 9118
    ClientReportPlayer                     = 9119
    ClientReportServer                     = 9120
    ClientCommendPlayer                    = 9121
    ClientReportResponse                   = 9122
    ClientCommendPlayerQuery               = 9123
    ClientCommendPlayerQueryResponse       = 9124
    WatchInfoUsers                         = 9126
    ClientRequestPlayersProfile            = 9127
    PlayersProfile                         = 9128
    SetMyMedalsInfo                        = 9129
    PlayerEarnedRewardNotification         = 9130
    PlayerOverwatchCaseUpdate              = 9131
    PlayerOverwatchCaseAssignment          = 9132
    PlayerOverwatchCaseStatus              = 9133
    GC2ClientTextMsg                       = 9134
    Client2GCTextMsg                       = 9135
    MatchEndRunRewardDrops                 = 9136
    MatchEndRewardDropsNotification        = 9137
    ClientRequestWatchInfoFriends2         = 9138
    MatchList                              = 9139
    MatchListRequestCurrentLiveGames       = 9140
    MatchListRequestRecentUserGames        = 9141
    GC2ServerReservationUpdate             = 9142
    ClientVarValueNotificationInfo         = 9144
    TournamentMatchRewardDropsNotification = 9145
    MatchListRequestTournamentGames        = 9146
    MatchListRequestFullGameInfo           = 9147
    GiftsLeaderboardRequest                = 9148
    GiftsLeaderboardResponse               = 9149
    ServerVarValueNotificationInfo         = 9150
    ClientSubmitSurveyVote                 = 9152
    Server2GCClientValidate                = 9153
    MatchListRequestLiveGameForUser        = 9154
    Server2GCPureServerValidationFailure   = 9155
    Client2GCEconPreviewDataBlockRequest   = 9156
    Client2GCEconPreviewDataBlockResponse  = 9157
    AccountPrivacySettings                 = 9158
    SetMyActivityInfo                      = 9159
    MatchListRequestTournamentPredictions  = 9160
    MatchListUploadTournamentPredictions   = 9161
    DraftSummary                           = 9162
    ClientRequestJoinFriendData            = 9163
    ClientRequestJoinServerData            = 9164
    ClientRequestNewMission                = 9165
