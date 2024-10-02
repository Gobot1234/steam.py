"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...enums import IntEnum, classproperty

if TYPE_CHECKING:
    from collections.abc import Mapping

    from typing_extensions import Self

__all__ = (
    "Hero",
    "GameMode",
    "LobbyType",
    "MatchOutcome",
    "RankTier",
)


# fmt: off
class Hero(IntEnum):
    """Enum representing Dota 2 hero.

    Primarily, mapping hero_id to hero name.
    """
    NONE              = 0
    AntiMage          = 1
    Axe               = 2
    Bane              = 3
    Bloodseeker       = 4
    CrystalMaiden     = 5
    DrowRanger        = 6
    Earthshaker       = 7
    Juggernaut        = 8
    Mirana            = 9
    Morphling         = 10
    ShadowFiend       = 11
    PhantomLancer     = 12
    Puck              = 13
    Pudge             = 14
    Razor             = 15
    SandKing          = 16
    StormSpirit       = 17
    Sven              = 18
    Tiny              = 19
    VengefulSpirit    = 20
    Windranger        = 21
    Zeus              = 22
    Kunkka            = 23
    Lina              = 25
    Lion              = 26
    ShadowShaman      = 27
    Slardar           = 28
    Tidehunter        = 29
    WitchDoctor       = 30
    Lich              = 31
    Riki              = 32
    Enigma            = 33
    Tinker            = 34
    Sniper            = 35
    Necrophos         = 36
    Warlock           = 37
    Beastmaster       = 38
    QueenOfPain       = 39
    Venomancer        = 40
    FacelessVoid      = 41
    WraithKing        = 42
    DeathProphet      = 43
    PhantomAssassin   = 44
    Pugna             = 45
    TemplarAssassin   = 46
    Viper             = 47
    Luna              = 48
    DragonKnight      = 49
    Dazzle            = 50
    Clockwerk         = 51
    Leshrac           = 52
    NaturesProphet    = 53
    Lifestealer       = 54
    DarkSeer          = 55
    Clinkz            = 56
    Omniknight        = 57
    Enchantress       = 58
    Huskar            = 59
    NightStalker      = 60
    Broodmother       = 61
    BountyHunter      = 62
    Weaver            = 63
    Jakiro            = 64
    Batrider          = 65
    Chen              = 66
    Spectre           = 67
    AncientApparition = 68
    Doom              = 69
    Ursa              = 70
    SpiritBreaker     = 71
    Gyrocopter        = 72
    Alchemist         = 73
    Invoker           = 74
    Silencer          = 75
    OutworldDevourer  = 76
    Lycan             = 77
    Brewmaster        = 78
    ShadowDemon       = 79
    LoneDruid         = 80
    ChaosKnight       = 81
    Meepo             = 82
    TreantProtector   = 83
    OgreMagi          = 84
    Undying           = 85
    Rubick            = 86
    Disruptor         = 87
    NyxAssassin       = 88
    NagaSiren         = 89
    KeeperOfTheLight  = 90
    Io                = 91
    Visage            = 92
    Slark             = 93
    Medusa            = 94
    TrollWarlord      = 95
    CentaurWarrunner  = 96
    Magnus            = 97
    Timbersaw         = 98
    Bristleback       = 99
    Tusk              = 100
    SkywrathMage      = 101
    Abaddon           = 102
    ElderTitan        = 103
    LegionCommander   = 104
    Techies           = 105
    EmberSpirit       = 106
    EarthSpirit       = 107
    Underlord         = 108
    Terrorblade       = 109
    Phoenix           = 110
    Oracle            = 111
    WinterWyvern      = 112
    ArcWarden         = 113
    MonkeyKing        = 114
    DarkWillow        = 119
    Pangolier         = 120
    Grimstroke        = 121
    Hoodwink          = 123
    VoidSpirit        = 126
    Snapfire          = 128
    Mars              = 129
    Ringmaster        = 131
    Dawnbreaker       = 135
    Marci             = 136
    PrimalBeast       = 137
    Muerta            = 138

    @classproperty
    def DISPLAY_NAMES(cls: type[Self]) -> Mapping[Hero, str]:  # type: ignore
        return {
            cls.NONE             : "None",  # happens when player disconnects or hasn't picked yet.
            cls.AntiMage         : "Anti-Mage",
            cls.Axe              : "Axe",
            cls.Bane             : "Bane",
            cls.Bloodseeker      : "Bloodseeker",
            cls.CrystalMaiden    : "Crystal Maiden",
            cls.DrowRanger       : "Drow Ranger",
            cls.Earthshaker      : "Earthshaker",
            cls.Juggernaut       : "Juggernaut",
            cls.Mirana           : "Mirana",
            cls.Morphling        : "Morphling",
            cls.ShadowFiend      : "Shadow Fiend",
            cls.PhantomLancer    : "Phantom Lancer",
            cls.Puck             : "Puck",
            cls.Pudge            : "Pudge",
            cls.Razor            : "Razor",
            cls.SandKing         : "Sand King",
            cls.StormSpirit      : "Storm Spirit",
            cls.Sven             : "Sven",
            cls.Tiny             : "Tiny",
            cls.VengefulSpirit   : "Vengeful Spirit",
            cls.Windranger       : "Windranger",
            cls.Zeus             : "Zeus",
            cls.Kunkka           : "Kunkka",
            cls.Lina             : "Lina",
            cls.Lion             : "Lion",
            cls.ShadowShaman     : "Shadow Shaman",
            cls.Slardar          : "Slardar",
            cls.Tidehunter       : "Tidehunter",
            cls.WitchDoctor      : "Witch Doctor",
            cls.Lich             : "Lich",
            cls.Riki             : "Riki",
            cls.Enigma           : "Enigma",
            cls.Tinker           : "Tinker",
            cls.Sniper           : "Sniper",
            cls.Necrophos        : "Necrophos",
            cls.Warlock          : "Warlock",
            cls.Beastmaster      : "Beastmaster",
            cls.QueenOfPain      : "Queen of Pain",
            cls.Venomancer       : "Venomancer",
            cls.FacelessVoid     : "Faceless Void",
            cls.WraithKing       : "Wraith King",
            cls.DeathProphet     : "Death Prophet",
            cls.PhantomAssassin  : "Phantom Assassin",
            cls.Pugna            : "Pugna",
            cls.TemplarAssassin  : "Templar Assassin",
            cls.Viper            : "Viper",
            cls.Luna             : "Luna",
            cls.DragonKnight     : "Dragon Knight",
            cls.Dazzle           : "Dazzle",
            cls.Clockwerk        : "Clockwerk",
            cls.Leshrac          : "Leshrac",
            cls.NaturesProphet   : "Nature's Prophet",
            cls.Lifestealer      : "Lifestealer",
            cls.DarkSeer         : "Dark Seer",
            cls.Clinkz           : "Clinkz",
            cls.Omniknight       : "Omniknight",
            cls.Enchantress      : "Enchantress",
            cls.Huskar           : "Huskar",
            cls.NightStalker     : "Night Stalker",
            cls.Broodmother      : "Broodmother",
            cls.BountyHunter     : "Bounty Hunter",
            cls.Weaver           : "Weaver",
            cls.Jakiro           : "Jakiro",
            cls.Batrider         : "Batrider",
            cls.Chen             : "Chen",
            cls.Spectre          : "Spectre",
            cls.AncientApparition: "Ancient Apparition",
            cls.Doom             : "Doom",
            cls.Ursa             : "Ursa",
            cls.SpiritBreaker    : "Spirit Breaker",
            cls.Gyrocopter       : "Gyrocopter",
            cls.Alchemist        : "Alchemist",
            cls.Invoker          : "Invoker",
            cls.Silencer         : "Silencer",
            cls.OutworldDevourer : "Outworld Devourer",
            cls.Lycan            : "Lycan",
            cls.Brewmaster       : "Brewmaster",
            cls.ShadowDemon      : "Shadow Demon",
            cls.LoneDruid        : "Lone Druid",
            cls.ChaosKnight      : "Chaos Knight",
            cls.Meepo            : "Meepo",
            cls.TreantProtector  : "Treant Protector",
            cls.OgreMagi         : "Ogre Magi",
            cls.Undying          : "Undying",
            cls.Rubick           : "Rubick",
            cls.Disruptor        : "Disruptor",
            cls.NyxAssassin      : "Nyx Assassin",
            cls.NagaSiren        : "Naga Siren",
            cls.KeeperOfTheLight : "Keeper of the Light",
            cls.Io               : "Io",
            cls.Visage           : "Visage",
            cls.Slark            : "Slark",
            cls.Medusa           : "Medusa",
            cls.TrollWarlord     : "Troll Warlord",
            cls.CentaurWarrunner : "Centaur Warrunner",
            cls.Magnus           : "Magnus",
            cls.Timbersaw        : "Timbersaw",
            cls.Bristleback      : "Bristleback",
            cls.Tusk             : "Tusk",
            cls.SkywrathMage     : "Skywrath Mage",
            cls.Abaddon          : "Abaddon",
            cls.ElderTitan       : "Elder Titan",
            cls.LegionCommander  : "Legion Commander",
            cls.Techies          : "Techies",
            cls.EmberSpirit      : "Ember Spirit",
            cls.EarthSpirit      : "Earth Spirit",
            cls.Underlord        : "Underlord",
            cls.Terrorblade      : "Terrorblade",
            cls.Phoenix          : "Phoenix",
            cls.Oracle           : "Oracle",
            cls.WinterWyvern     : "Winter Wyvern",
            cls.ArcWarden        : "Arc Warden",
            cls.MonkeyKing       : "Monkey King",
            cls.DarkWillow       : "Dark Willow",
            cls.Pangolier        : "Pangolier",
            cls.Grimstroke       : "Grimstroke",
            cls.Hoodwink         : "Hoodwink",
            cls.VoidSpirit       : "Void Spirit",
            cls.Snapfire         : "Snapfire",
            cls.Mars             : "Mars",
            cls.Ringmaster       : "Ringmaster",
            cls.Dawnbreaker      : "Dawnbreaker",
            cls.Marci            : "Marci",
            cls.PrimalBeast      : "Primal Beast",
            cls.Muerta           : "Muerta",
        }

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAMES[self]

    @property
    def id(self) -> int:
        return self.value

    def __bool__(self) -> bool:  # type: ignore # idk I need `Hero.NONE` to be `False`
        return bool(self.value)


class GameMode(IntEnum):  # source: dota_shared_enums.proto
    NONE                = 0
    AllPick             = 1
    CaptainsMode        = 2
    RandomDraft         = 3
    SingleDraft         = 4
    AllRandom           = 5
    Intro               = 6
    Diretide            = 7
    ReverseCaptainsMode = 8
    Frostivus           = 9
    Tutorial            = 10
    MidOnly             = 11
    LeastPlayed         = 12
    NewPlayerMode       = 13
    CompendiumMatch     = 14
    Custom              = 15
    CaptainsDraft       = 16
    BalancedDraft       = 17
    AbilityDraft        = 18
    Event               = 19
    AllRandomDeathMatch = 20
    Mid1v1              = 21
    AllDraft            = 22
    Turbo               = 23
    Mutation            = 24
    CoachesChallenge    = 25

    @classproperty
    def DISPLAY_NAMES(cls: type[Self]) -> Mapping[GameMode, str]:  # type: ignore
        return {
                cls.NONE               : "None",
                cls.AllPick            : "All Pick",
                cls.CaptainsMode       : "Captain's Mode",
                cls.RandomDraft        : "Random Draft",
                cls.SingleDraft        : "Single Draft",
                cls.AllRandom          : "All Random",
                cls.Intro              : "Intro",
                cls.Diretide           : "Diretide",
                cls.ReverseCaptainsMode: "Reverse Captain's Mode",
                cls.Frostivus          : "Frostivus",  # XMAS, The Greeviling
                cls.Tutorial           : "Tutorial",
                cls.MidOnly            : "Mid Only",
                cls.LeastPlayed        : "Least Played",
                cls.NewPlayerMode      : "New Player Mode",
                cls.CompendiumMatch    : "Compendium Match",
                cls.Custom             : "Custom Game",
                cls.CaptainsDraft      : "Captain's Draft",
                cls.BalancedDraft      : "Balanced Draft",
                cls.AbilityDraft       : "Ability Draft",
                cls.Event              : "Event Game",
                cls.AllRandomDeathMatch: "All Random DeathMatch",
                cls.Mid1v1             : "1v1 Mid Only",
                cls.AllDraft           : "All Draft",  # Ranked Matchmaking
                cls.Turbo              : "Turbo",
                cls.Mutation           : "Mutation",
                cls.CoachesChallenge   : "Coaches Challenge",
        }

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAMES[self]


class LobbyType(IntEnum):  # source: dota_gcmessages_common_lobby.proto
    Invalid          = -1
    Unranked         = 0
    Practice         = 1
    CoopBotMatch     = 4
    Ranked           = 7
    BattleCup        = 9
    LocalBotMatch    = 10
    Spectator        = 11
    EventGameMode    = 12
    NewPlayerMode    = 14
    FeaturedGameMode = 15

    @classproperty
    def DISPLAY_NAMES(cls: type[Self]) -> Mapping[LobbyType, str]:  # type: ignore
        return {
            cls.Invalid         : "Invalid",
            cls.Unranked        : "Unranked",
            cls.Practice        : "Practice",
            cls.CoopBotMatch    : "Coop Bots",
            cls.Ranked          : "Ranked",
            cls.BattleCup       : "Battle Cup",
            cls.LocalBotMatch   : "Local Bot Match",
            cls.Spectator       : "Spectator",
            cls.EventGameMode   : "Event",
            cls.NewPlayerMode   : "New Player Mode",
            cls.FeaturedGameMode: "Featured Gamemode",
        }

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAMES[self]


class RankTier(IntEnum):
    """Enum representing Dota 2 Rank Tier.

    Commonly called "ranked medals".
    """
    Uncalibrated = 0
    Herald1      = 11
    Herald2      = 12
    Herald3      = 13
    Herald4      = 14
    Herald5      = 15
    Guardian1    = 21
    Guardian2    = 22
    Guardian3    = 23
    Guardian4    = 24
    Guardian5    = 25
    Crusader1    = 31
    Crusader2    = 32
    Crusader3    = 33
    Crusader4    = 34
    Crusader5    = 35
    Archon1      = 41
    Archon2      = 42
    Archon3      = 43
    Archon4      = 44
    Archon5      = 45
    Legend1      = 51
    Legend2      = 52
    Legend3      = 53
    Legend4      = 54
    Legend5      = 55
    Ancient1     = 61
    Ancient2     = 62
    Ancient3     = 63
    Ancient4     = 64
    Ancient5     = 65
    Divine1      = 71
    Divine2      = 72
    Divine3      = 73
    Divine4      = 74
    Divine5      = 75
    Immortal     = 80

    @property
    def division(self) -> str:
        if self.value % 10 == 0:
            return self.name
        else:
            return self.name[:-1]

    @property
    def stars(self) -> str:
        return self.value % 10

    # do we need it as a factory helper method?
    @property
    def display_name(self) -> str:
        suffix = f' {self.stars}' if self.stars else ''
        return self.division + suffix


class MatchOutcome(IntEnum):  # source: dota_shared_enums.proto
    """Represents Match Outcome."""
    Unknown                        = 0
    RadiantVictory                 = 2
    DireVictory                    = 3
    NeutralVictory                 = 4
    NoTeamWinner                   = 5
    Custom1Victory                 = 6
    Custom2Victory                 = 7
    Custom3Victory                 = 8
    Custom4Victory                 = 9
    Custom5Victory                 = 10
    Custom6Victory                 = 11
    Custom7Victory                 = 12
    Custom8Victory                 = 13
    NotScoredPoorNetworkConditions = 64
    NotScoredLeaver                = 65
    NotScoredServerCrash           = 66
    NotScoredNeverStarted          = 67
    NotScoredCanceled              = 68
    NotScoredSuspicious            = 69


class EMsg(IntEnum):
    # EGCBaseClientMsg - source: gcsystemmsgs.proto
    PingRequest                  = 3001
    PingResponse                 = 3002
    GCToClientPollConvarRequest  = 3003
    GCToClientPollConvarResponse = 3004
    CompressedMsgToClient        = 3005
    CompressedMsgToClient_Legacy = 523
    GCToClientRequestDropped     = 3006
    ClientWelcome                = 4004
    ServerWelcome                = 4005
    ClientHello                  = 4006
    ServerHello                  = 4007
    ClientConnectionStatus       = 4009
    ServerConnectionStatus       = 4010

    # EDOTAGCMsg - source: dota_gcmessages_msgid.proto
    DOTABase                                                     = 7000
    GameMatchSignOut                                             = 7004
    GameMatchSignOutResponse                                     = 7005
    JoinChatChannel                                              = 7009
    JoinChatChannelResponse                                      = 7010
    OtherJoinedChannel                                           = 7013
    OtherLeftChannel                                             = 7014
    ServerToGCRequestStatus                                      = 7026
    StartFindingMatch                                            = 7033
    ConnectedPlayers                                             = 7034
    AbandonCurrentGame                                           = 7035
    StopFindingMatch                                             = 7036
    PracticeLobbyCreate                                          = 7038
    PracticeLobbyLeave                                           = 7040
    PracticeLobbyLaunch                                          = 7041
    PracticeLobbyList                                            = 7042
    PracticeLobbyListResponse                                    = 7043
    PracticeLobbyJoin                                            = 7044
    PracticeLobbySetDetails                                      = 7046
    PracticeLobbySetTeamSlot                                     = 7047
    InitialQuestionnaireResponse                                 = 7049
    PracticeLobbyResponse                                        = 7055
    BroadcastNotification                                        = 7056
    LiveScoreboardUpdate                                         = 7057
    RequestChatChannelList                                       = 7060
    RequestChatChannelListResponse                               = 7061
    ReadyUp                                                      = 7070
    KickedFromMatchmakingQueue                                   = 7071
    LeaverDetected                                               = 7072
    SpectateFriendGame                                           = 7073
    SpectateFriendGameResponse                                   = 7074
    ReportsRemainingRequest                                      = 7076
    ReportsRemainingResponse                                     = 7077
    SubmitPlayerReport                                           = 7078
    SubmitPlayerReportResponse                                   = 7079
    PracticeLobbyKick                                            = 7081
    SubmitPlayerReportV2                                         = 7082
    SubmitPlayerReportResponseV2                                 = 7083
    RequestSaveGames                                             = 7084
    RequestSaveGamesServer                                       = 7085
    RequestSaveGamesResponse                                     = 7086
    LeaverDetectedResponse                                       = 7087
    PlayerFailedToConnect                                        = 7088
    GCToRelayConnect                                             = 7089
    GCToRelayConnectresponse                                     = 7090
    WatchGame                                                    = 7091
    WatchGameResponse                                            = 7092
    BanStatusRequest                                             = 7093
    BanStatusResponse                                            = 7094
    MatchDetailsRequest                                          = 7095
    MatchDetailsResponse                                         = 7096
    CancelWatchGame                                              = 7097
    Popup                                                        = 7102
    FriendPracticeLobbyListRequest                               = 7111
    FriendPracticeLobbyListResponse                              = 7112
    PracticeLobbyJoinResponse                                    = 7113
    CreateTeam                                                   = 7115
    CreateTeamResponse                                           = 7116
    TeamInviteInviterToGC                                        = 7122
    TeamInviteImmediateResponseToInviter                         = 7123
    TeamInviteRequestToInvitee                                   = 7124
    TeamInviteInviteeResponseToGC                                = 7125
    TeamInviteResponseToInviter                                  = 7126
    TeamInviteResponseToInvitee                                  = 7127
    KickTeamMember                                               = 7128
    KickTeamMemberResponse                                       = 7129
    LeaveTeam                                                    = 7130
    LeaveTeamResponse                                            = 7131
    ApplyTeamToPracticeLobby                                     = 7142
    TransferTeamAdmin                                            = 7144
    PracticeLobbyJoinBroadcastChannel                            = 7149
    TournamentItemEvent                                          = 7150
    TournamentItemEventResponse                                  = 7151
    TeamFanfare                                                  = 7156
    ResponseTeamFanfare                                          = 7157
    GameServerUploadSaveGame                                     = 7158
    GameServerSaveGameResult                                     = 7159
    GameServerGetLoadGame                                        = 7160
    GameServerGetLoadGameResult                                  = 7161
    EditTeamDetails                                              = 7166
    EditTeamDetailsResponse                                      = 7167
    ReadyUpStatus                                                = 7170
    GCToGCMatchCompleted                                         = 7186
    BalancedShuffleLobby                                         = 7188
    MatchmakingStatsRequest                                      = 7197
    MatchmakingStatsResponse                                     = 7198
    BotGameCreate                                                = 7199
    SetMatchHistoryAccess                                        = 7200
    SetMatchHistoryAccessResponse                                = 7201
    UpgradeLeagueItem                                            = 7203
    UpgradeLeagueItemResponse                                    = 7204
    WatchDownloadedReplay                                        = 7206
    ClientsRejoinChatChannels                                    = 7217
    GCToGCGetUserChatInfo                                        = 7218
    GCToGCGetUserChatInfoResponse                                = 7219
    GCToGCLeaveAllChatChannels                                   = 7220
    GCToGCUpdateAccountChatBan                                   = 7221
    GCToGCCanInviteUserToTeam                                    = 7234
    GCToGCCanInviteUserToTeamResponse                            = 7235
    GCToGCGetUserRank                                            = 7236
    GCToGCGetUserRankResponse                                    = 7237
    GCToGCAdjustUserRank                                         = 7238
    GCToGCAdjustUserRankResponse                                 = 7239
    GCToGCUpdateTeamStats                                        = 7240
    GCToGCValidateTeam                                           = 7241
    GCToGCValidateTeamResponse                                   = 7242
    GCToGCGetLeagueAdmin                                         = 7255
    GCToGCGetLeagueAdminResponse                                 = 7256
    LeaveChatChannel                                             = 7272
    ChatMessage                                                  = 7273
    GetHeroStandings                                             = 7274
    GetHeroStandingsResponse                                     = 7275
    ItemEditorReservationsRequest                                = 7283
    ItemEditorReservationsResponse                               = 7284
    ItemEditorReserveItemDef                                     = 7285
    ItemEditorReserveItemDefResponse                             = 7286
    ItemEditorReleaseReservation                                 = 7287
    ItemEditorReleaseReservationResponse                         = 7288
    RewardTutorialPrizes                                         = 7289
    FantasyLivePlayerStats                                       = 7308
    FantasyFinalPlayerStats                                      = 7309
    FlipLobbyTeams                                               = 7320
    GCToGCEvaluateReportedPlayer                                 = 7322
    GCToGCEvaluateReportedPlayerResponse                         = 7323
    GCToGCProcessPlayerReportForTarget                           = 7324
    GCToGCProcessReportSuccess                                   = 7325
    NotifyAccountFlagsChange                                     = 7326
    SetProfilePrivacy                                            = 7327
    SetProfilePrivacyResponse                                    = 7328
    ClientSuspended                                              = 7342
    PartyMemberSetCoach                                          = 7343
    PracticeLobbySetCoach                                        = 7346
    ChatModeratorBan                                             = 7359
    LobbyUpdateBroadcastChannelInfo                              = 7367
    GCToGCGrantTournamentItem                                    = 7372
    GCToGCUpgradeTwitchViewerItems                               = 7375
    GCToGCGetLiveMatchAffiliates                                 = 7376
    GCToGCGetLiveMatchAffiliatesResponse                         = 7377
    GCToGCUpdatePlayerPennantCounts                              = 7378
    GCToGCGetPlayerPennantCounts                                 = 7379
    GCToGCGetPlayerPennantCountsResponse                         = 7380
    GameMatchSignOutPermissionRequest                            = 7381
    GameMatchSignOutPermissionResponse                           = 7382
    AwardEventPoints                                             = 7384
    GetEventPoints                                               = 7387
    GetEventPointsResponse                                       = 7388
    PartyLeaderWatchGamePrompt                                   = 7397
    CompendiumSetSelection                                       = 7405
    CompendiumDataRequest                                        = 7406
    CompendiumDataResponse                                       = 7407
    GetPlayerMatchHistory                                        = 7408
    GetPlayerMatchHistoryResponse                                = 7409
    GCToGCMatchmakingAddParty                                    = 7410
    GCToGCMatchmakingRemoveParty                                 = 7411
    GCToGCMatchmakingRemoveAllParties                            = 7412
    GCToGCMatchmakingMatchFound                                  = 7413
    GCToGCUpdateMatchManagementStats                             = 7414
    GCToGCUpdateMatchmakingStats                                 = 7415
    GCToServerPingRequest                                        = 7416
    GCToServerPingResponse                                       = 7417
    GCToServerEvaluateToxicChat                                  = 7418
    ServerToGCEvaluateToxicChat                                  = 7419
    ServerToGCEvaluateToxicChatResponse                          = 7420
    GCToGCProcessMatchLeaver                                     = 7426
    NotificationsRequest                                         = 7427
    NotificationsResponse                                        = 7428
    GCToGCModifyNotification                                     = 7429
    LeagueAdminList                                              = 7434
    NotificationsMarkReadRequest                                 = 7435
    ServerToGCRequestBatchPlayerResources                        = 7450
    ServerToGCRequestBatchPlayerResourcesResponse                = 7451
    CompendiumSetSelectionResponse                               = 7453
    PlayerInfoSubmit                                             = 7456
    PlayerInfoSubmitResponse                                     = 7457
    GCToGCGetAccountLevel                                        = 7458
    GCToGCGetAccountLevelResponse                                = 7459
    DOTAGetWeekendTourneySchedule                                = 7464
    DOTAWeekendTourneySchedule                                   = 7465
    JoinableCustomGameModesRequest                               = 7466
    JoinableCustomGameModesResponse                              = 7467
    JoinableCustomLobbiesRequest                                 = 7468
    JoinableCustomLobbiesResponse                                = 7469
    QuickJoinCustomLobby                                         = 7470
    QuickJoinCustomLobbyResponse                                 = 7471
    GCToGCGrantEventPointAction                                  = 7472
    GCToGCSetCompendiumSelection                                 = 7478
    HasItemQuery                                                 = 7484
    HasItemResponse                                              = 7485
    GCToGCGrantEventPointActionMsg                               = 7488
    GCToGCGetCompendiumSelections                                = 7492
    GCToGCGetCompendiumSelectionsResponse                        = 7493
    ServerToGCMatchConnectionStats                               = 7494
    GCToClientTournamentItemDrop                                 = 7495
    SQLDelayedGrantLeagueDrop                                    = 7496
    ServerGCUpdateSpectatorCount                                 = 7497
    GCToGCEmoticonUnlock                                         = 7501
    SignOutDraftInfo                                             = 7502
    ClientToGCEmoticonDataRequest                                = 7503
    GCToClientEmoticonData                                       = 7504
    PracticeLobbyToggleBroadcastChannelCameramanStatus           = 7505
    RedeemItem                                                   = 7518
    RedeemItemResponse                                           = 7519
    ClientToGCGetAllHeroProgress                                 = 7521
    ClientToGCGetAllHeroProgressResponse                         = 7522
    GCToGCGetServerForClient                                     = 7523
    GCToGCGetServerForClientResponse                             = 7524
    SQLProcessTournamentGameOutcome                              = 7525
    SQLGrantTrophyToAccount                                      = 7526
    ClientToGCGetTrophyList                                      = 7527
    ClientToGCGetTrophyListResponse                              = 7528
    GCToClientTrophyAwarded                                      = 7529
    GCGameBotMatchSignOut                                        = 7530
    GCGameBotMatchSignOutPermissionRequest                       = 7531
    SignOutBotInfo                                               = 7532
    GCToGCUpdateProfileCards                                     = 7533
    ClientToGCGetProfileCard                                     = 7534
    ClientToGCGetProfileCardResponse                             = 7535
    ClientToGCGetBattleReport                                    = 7536
    ClientToGCGetBattleReportResponse                            = 7537
    ClientToGCSetProfileCardSlots                                = 7538
    GCToClientProfileCardUpdated                                 = 7539
    ServerToGCVictoryPredictions                                 = 7540
    ClientToGCGetBattleReportAggregateStats                      = 7541
    ClientToGCGetBattleReportAggregateStatsResponse              = 7542
    ClientToGCGetBattleReportInfo                                = 7543
    ClientToGCGetBattleReportInfoResponse                        = 7544
    SignOutCommunicationSummary                                  = 7545
    ServerToGCRequestStatus_Response                             = 7546
    ClientToGCCreateHeroStatue                                   = 7547
    GCToClientHeroStatueCreateResult                             = 7548
    GCToLANServerRelayConnect                                    = 7549
    ClientToGCAcknowledgeBattleReport                            = 7550
    ClientToGCAcknowledgeBattleReportResponse                    = 7551
    ClientToGCGetBattleReportMatchHistory                        = 7552
    ClientToGCGetBattleReportMatchHistoryResponse                = 7553
    ServerToGCReportKillSummaries                                = 7554
    GCToGCUpdatePlayerPredictions                                = 7561
    GCToServerPredictionResult                                   = 7562
    GCToGCReplayMonitorValidateReplay                            = 7569
    LobbyEventPoints                                             = 7572
    GCToGCGetCustomGameTickets                                   = 7573
    GCToGCGetCustomGameTicketsResponse                           = 7574
    GCToGCCustomGamePlayed                                       = 7576
    GCToGCGrantEventPointsToUser                                 = 7577
    GameserverCrashReport                                        = 7579
    GameserverCrashReportResponse                                = 7580
    GCToClientSteamDatagramTicket                                = 7581
    GCToGCSendAccountsEventPoints                                = 7583
    ClientToGCRerollPlayerChallenge                              = 7584
    ServerToGCRerollPlayerChallenge                              = 7585
    RerollPlayerChallengeResponse                                = 7586
    SignOutUpdatePlayerChallenge                                 = 7587
    ClientToGCSetPartyLeader                                     = 7588
    ClientToGCCancelPartyInvites                                 = 7589
    SQLGrantLeagueMatchToTicketHolders                           = 7592
    GCToGCEmoticonUnlockNoRollback                               = 7594
    ClientToGCApplyGemCombiner                                   = 7603
    ClientToGCGetAllHeroOrder                                    = 7606
    ClientToGCGetAllHeroOrderResponse                            = 7607
    SQLGCToGCGrantBadgePoints                                    = 7608
    GCToGCCheckOwnsEntireEmoticonRange                           = 7611
    GCToGCCheckOwnsEntireEmoticonRangeResponse                   = 7612
    GCToClientRequestLaneSelection                               = 7623
    GCToClientRequestLaneSelectionResponse                       = 7624
    ServerToGCCavernCrawlIsHeroActive                            = 7625
    ServerToGCCavernCrawlIsHeroActiveResponse                    = 7626
    ClientToGCPlayerCardSpecificPurchaseRequest                  = 7627
    ClientToGCPlayerCardSpecificPurchaseResponse                 = 7628
    GCtoServerTensorflowInstance                                 = 7629
    SQLSetIsLeagueAdmin                                          = 7630
    GCToGCGetLiveLeagueMatches                                   = 7631
    GCToGCGetLiveLeagueMatchesResponse                           = 7632
    LeagueInfoListAdminsRequest                                  = 7633
    LeagueInfoListAdminsReponse                                  = 7634
    GCToGCLeagueMatchStarted                                     = 7645
    GCToGCLeagueMatchCompleted                                   = 7646
    GCToGCLeagueMatchStartedResponse                             = 7647
    LeagueAvailableLobbyNodesRequest                             = 7650
    LeagueAvailableLobbyNodes                                    = 7651
    GCToGCLeagueRequest                                          = 7652
    GCToGCLeagueResponse                                         = 7653
    GCToGCLeagueNodeGroupRequest                                 = 7654
    GCToGCLeagueNodeGroupResponse                                = 7655
    GCToGCLeagueNodeRequest                                      = 7656
    GCToGCLeagueNodeResponse                                     = 7657
    GCToGCRealtimeStatsTerseRequest                              = 7658
    GCToGCRealtimeStatsTerseResponse                             = 7659
    GCToGCGetTopMatchesRequest                                   = 7660
    GCToGCGetTopMatchesResponse                                  = 7661
    ClientToGCGetFilteredPlayers                                 = 7662
    GCToClientGetFilteredPlayersResponse                         = 7663
    ClientToGCRemoveFilteredPlayer                               = 7664
    GCToClientRemoveFilteredPlayerResponse                       = 7665
    GCToClientPlayerBeaconState                                  = 7666
    GCToClientPartyBeaconUpdate                                  = 7667
    GCToClientPartySearchInvite                                  = 7668
    ClientToGCUpdatePartyBeacon                                  = 7669
    ClientToGCRequestActiveBeaconParties                         = 7670
    GCToClientRequestActiveBeaconPartiesResponse                 = 7671
    ClientToGCManageFavorites                                    = 7672
    GCToClientManageFavoritesResponse                            = 7673
    ClientToGCJoinPartyFromBeacon                                = 7674
    GCToClientJoinPartyFromBeaconResponse                        = 7675
    ClientToGCGetFavoritePlayers                                 = 7676
    GCToClientGetFavoritePlayersResponse                         = 7677
    ClientToGCVerifyFavoritePlayers                              = 7678
    GCToClientVerifyFavoritePlayersResponse                      = 7679
    GCToClientPartySearchInvites                                 = 7680
    GCToClientRequestMMInfo                                      = 7681
    ClientToGCMMInfo                                             = 7682
    SignOutTextMuteInfo                                          = 7683
    ClientToGCPurchaseLabyrinthBlessings                         = 7684
    ClientToGCPurchaseLabyrinthBlessingsResponse                 = 7685
    ClientToGCPurchaseFilteredPlayerSlot                         = 7686
    GCToClientPurchaseFilteredPlayerSlotResponse                 = 7687
    ClientToGCUpdateFilteredPlayerNote                           = 7688
    GCToClientUpdateFilteredPlayerNoteResponse                   = 7689
    ClientToGCClaimSwag                                          = 7690
    GCToClientClaimSwagResponse                                  = 7691
    ServerToGCLockCharmTrading                                   = 8004
    ClientToGCPlayerStatsRequest                                 = 8006
    GCToClientPlayerStatsResponse                                = 8007
    ClearPracticeLobbyTeam                                       = 8008
    ClientToGCFindTopSourceTVGames                               = 8009
    GCToClientFindTopSourceTVGamesResponse                       = 8010
    LobbyList                                                    = 8011
    LobbyListResponse                                            = 8012
    PlayerStatsMatchSignOut                                      = 8013
    ClientToGCSocialFeedPostCommentRequest                       = 8016
    GCToClientSocialFeedPostCommentResponse                      = 8017
    ClientToGCCustomGamesFriendsPlayedRequest                    = 8018
    GCToClientCustomGamesFriendsPlayedResponse                   = 8019
    ClientToGCFriendsPlayedCustomGameRequest                     = 8020
    GCToClientFriendsPlayedCustomGameResponse                    = 8021
    TopCustomGamesList                                           = 8024
    ClientToGCSetPartyOpen                                       = 8029
    ClientToGCMergePartyInvite                                   = 8030
    GCToClientMergeGroupInviteReply                              = 8031
    ClientToGCMergePartyResponse                                 = 8032
    GCToClientMergePartyResponseReply                            = 8033
    ClientToGCGetProfileCardStats                                = 8034
    ClientToGCGetProfileCardStatsResponse                        = 8035
    ClientToGCTopLeagueMatchesRequest                            = 8036
    ClientToGCTopFriendMatchesRequest                            = 8037
    GCToClientProfileCardStatsUpdated                            = 8040
    ServerToGCRealtimeStats                                      = 8041
    GCToServerRealtimeStatsStartStop                             = 8042
    GCToGCGetServersForClients                                   = 8045
    GCToGCGetServersForClientsResponse                           = 8046
    PracticeLobbyKickFromTeam                                    = 8047
    ChatGetMemberCount                                           = 8048
    ChatGetMemberCountResponse                                   = 8049
    ClientToGCSocialFeedPostMessageRequest                       = 8050
    GCToClientSocialFeedPostMessageResponse                      = 8051
    CustomGameListenServerStartedLoading                         = 8052
    CustomGameClientFinishedLoading                              = 8053
    PracticeLobbyCloseBroadcastChannel                           = 8054
    StartFindingMatchResponse                                    = 8055
    SQLGCToGCGrantAccountFlag                                    = 8057
    GCToClientTopLeagueMatchesResponse                           = 8061
    GCToClientTopFriendMatchesResponse                           = 8062
    ClientToGCMatchesMinimalRequest                              = 8063
    ClientToGCMatchesMinimalResponse                             = 8064
    GCToClientChatRegionsEnabled                                 = 8067
    ClientToGCPingData                                           = 8068
    GCToGCEnsureAccountInParty                                   = 8071
    GCToGCEnsureAccountInPartyResponse                           = 8072
    ClientToGCGetProfileTickets                                  = 8073
    ClientToGCGetProfileTicketsResponse                          = 8074
    GCToClientMatchGroupsVersion                                 = 8075
    ClientToGCH264Unsupported                                    = 8076
    ClientToGCGetQuestProgress                                   = 8078
    ClientToGCGetQuestProgressResponse                           = 8079
    SignOutXPCoins                                               = 8080
    GCToClientMatchSignedOut                                     = 8081
    GetHeroStatsHistory                                          = 8082
    GetHeroStatsHistoryResponse                                  = 8083
    ClientToGCPrivateChatInvite                                  = 8084
    ClientToGCPrivateChatKick                                    = 8088
    ClientToGCPrivateChatPromote                                 = 8089
    ClientToGCPrivateChatDemote                                  = 8090
    GCToClientPrivateChatResponse                                = 8091
    ClientToGCLatestConductScorecardRequest                      = 8095
    ClientToGCLatestConductScorecard                             = 8096
    ClientToGCWageringRequest                                    = 8099
    GCToClientWageringResponse                                   = 8100
    ClientToGCEventGoalsRequest                                  = 8103
    ClientToGCEventGoalsResponse                                 = 8104
    GCToGCLeaguePredictionsUpdate                                = 8108
    GCToGCAddUserToPostGameChat                                  = 8110
    ClientToGCHasPlayerVotedForMVP                               = 8111
    ClientToGCHasPlayerVotedForMVPResponse                       = 8112
    ClientToGCVoteForMVP                                         = 8113
    ClientToGCVoteForMVPResponse                                 = 8114
    GCToGCGetEventOwnership                                      = 8115
    GCToGCGetEventOwnershipResponse                              = 8116
    GCToClientAutomatedTournamentStateChange                     = 8117
    ClientToGCWeekendTourneyOpts                                 = 8118
    ClientToGCWeekendTourneyOptsResponse                         = 8119
    ClientToGCWeekendTourneyLeave                                = 8120
    ClientToGCWeekendTourneyLeaveResponse                        = 8121
    ClientToGCTeammateStatsRequest                               = 8124
    ClientToGCTeammateStatsResponse                              = 8125
    ClientToGCGetGiftPermissions                                 = 8126
    ClientToGCGetGiftPermissionsResponse                         = 8127
    ClientToGCVoteForArcana                                      = 8128
    ClientToGCVoteForArcanaResponse                              = 8129
    ClientToGCRequestArcanaVotesRemaining                        = 8130
    ClientToGCRequestArcanaVotesRemainingResponse                = 8131
    TransferTeamAdminResponse                                    = 8132
    GCToClientTeamInfo                                           = 8135
    GCToClientTeamsInfo                                          = 8136
    ClientToGCMyTeamInfoRequest                                  = 8137
    ClientToGCPublishUserStat                                    = 8140
    GCToGCSignoutSpendWager                                      = 8141
    SubmitLobbyMVPVote                                           = 8144
    SubmitLobbyMVPVoteResponse                                   = 8145
    SignOutCommunityGoalProgress                                 = 8150
    GCToClientLobbyMVPAwarded                                    = 8152
    GCToClientQuestProgressUpdated                               = 8153
    GCToClientWageringUpdate                                     = 8154
    GCToClientArcanaVotesUpdate                                  = 8155
    ClientToGCSetSpectatorLobbyDetails                           = 8157
    ClientToGCSetSpectatorLobbyDetailsResponse                   = 8158
    ClientToGCCreateSpectatorLobby                               = 8159
    ClientToGCCreateSpectatorLobbyResponse                       = 8160
    ClientToGCSpectatorLobbyList                                 = 8161
    ClientToGCSpectatorLobbyListResponse                         = 8162
    SpectatorLobbyGameDetails                                    = 8163
    ServerToGCCompendiumInGamePredictionResults                  = 8166
    ServerToGCCloseCompendiumInGamePredictionVoting              = 8167
    ClientToGCOpenPlayerCardPack                                 = 8168
    ClientToGCOpenPlayerCardPackResponse                         = 8169
    ClientToGCSelectCompendiumInGamePrediction                   = 8170
    ClientToGCSelectCompendiumInGamePredictionResponse           = 8171
    ClientToGCWeekendTourneyGetPlayerStats                       = 8172
    ClientToGCWeekendTourneyGetPlayerStatsResponse               = 8173
    ClientToGCRecyclePlayerCard                                  = 8174
    ClientToGCRecyclePlayerCardResponse                          = 8175
    ClientToGCCreatePlayerCardPack                               = 8176
    ClientToGCCreatePlayerCardPackResponse                       = 8177
    ClientToGCGetPlayerCardRosterRequest                         = 8178
    ClientToGCGetPlayerCardRosterResponse                        = 8179
    ClientToGCSetPlayerCardRosterRequest                         = 8180
    ClientToGCSetPlayerCardRosterResponse                        = 8181
    ServerToGCCloseCompendiumInGamePredictionVotingResponse      = 8183
    LobbyBattleCupVictory                                        = 8186
    GetPlayerCardItemInfo                                        = 8187
    GetPlayerCardItemInfoResponse                                = 8188
    ClientToGCRequestSteamDatagramTicket                         = 8189
    ClientToGCRequestSteamDatagramTicketResponse                 = 8190
    GCToClientBattlePassRollupRequest                            = 8191
    GCToClientBattlePassRollupResponse                           = 8192
    ClientToGCTransferSeasonalMMRRequest                         = 8193
    ClientToGCTransferSeasonalMMRResponse                        = 8194
    GCToGCPublicChatCommunicationBan                             = 8195
    GCToGCUpdateAccountInfo                                      = 8196
    ChatReportPublicSpam                                         = 8197
    ClientToGCSetPartyBuilderOptions                             = 8198
    ClientToGCSetPartyBuilderOptionsResponse                     = 8199
    GCToClientPlaytestStatus                                     = 8200
    ClientToGCJoinPlaytest                                       = 8201
    ClientToGCJoinPlaytestResponse                               = 8202
    LobbyPlaytestDetails                                         = 8203
    SetFavoriteTeam                                              = 8204
    GCToClientBattlePassRollupListRequest                        = 8205
    GCToClientBattlePassRollupListResponse                       = 8206
    ClaimEventAction                                             = 8209
    ClaimEventActionResponse                                     = 8210
    GetPeriodicResource                                          = 8211
    GetPeriodicResourceResponse                                  = 8212
    PeriodicResourceUpdated                                      = 8213
    ServerToGCSpendWager                                         = 8214
    GCToGCSignoutSpendWagerToken                                 = 8215
    SubmitTriviaQuestionAnswer                                   = 8216
    SubmitTriviaQuestionAnswerResponse                           = 8217
    ClientToGCGiveTip                                            = 8218
    ClientToGCGiveTipResponse                                    = 8219
    StartTriviaSession                                           = 8220
    StartTriviaSessionResponse                                   = 8221
    AnchorPhoneNumberRequest                                     = 8222
    AnchorPhoneNumberResponse                                    = 8223
    UnanchorPhoneNumberRequest                                   = 8224
    UnanchorPhoneNumberResponse                                  = 8225
    GCToGCSignoutSpendRankWager                                  = 8229
    GCToGCGetFavoriteTeam                                        = 8230
    GCToGCGetFavoriteTeamResponse                                = 8231
    SignOutEventGameData                                         = 8232
    ClientToGCQuickStatsRequest                                  = 8238
    ClientToGCQuickStatsResponse                                 = 8239
    GCToGCSubtractEventPointsFromUser                            = 8240
    SelectionPriorityChoiceRequest                               = 8241
    SelectionPriorityChoiceResponse                              = 8242
    GCToGCCompendiumInGamePredictionResults                      = 8243
    GameAutographReward                                          = 8244
    GameAutographRewardResponse                                  = 8245
    DestroyLobbyRequest                                          = 8246
    DestroyLobbyResponse                                         = 8247
    PurchaseItemWithEventPoints                                  = 8248
    PurchaseItemWithEventPointsResponse                          = 8249
    ServerToGCMatchPlayerItemPurchaseHistory                     = 8250
    GCToGCGrantPlusHeroMatchResults                              = 8251
    ServerToGCMatchStateHistory                                  = 8255
    PurchaseHeroRandomRelic                                      = 8258
    PurchaseHeroRandomRelicResponse                              = 8259
    ClientToGCClaimEventActionUsingItem                          = 8260
    ClientToGCClaimEventActionUsingItemResponse                  = 8261
    PartyReadyCheckRequest                                       = 8262
    PartyReadyCheckResponse                                      = 8263
    PartyReadyCheckAcknowledge                                   = 8264
    GetRecentPlayTimeFriendsRequest                              = 8265
    GetRecentPlayTimeFriendsResponse                             = 8266
    GCToClientCommendNotification                                = 8267
    ProfileRequest                                               = 8268
    ProfileResponse                                              = 8269
    ProfileUpdate                                                = 8270
    ProfileUpdateResponse                                        = 8271
    HeroGlobalDataRequest                                        = 8274
    HeroGlobalDataResponse                                       = 8275
    ClientToGCRequestPlusWeeklyChallengeResult                   = 8276
    ClientToGCRequestPlusWeeklyChallengeResultResponse           = 8277
    GCToGCGrantPlusPrepaidTime                                   = 8278
    PrivateMetadataKeyRequest                                    = 8279
    PrivateMetadataKeyResponse                                   = 8280
    GCToGCReconcilePlusStatus                                    = 8281
    GCToGCCheckPlusStatus                                        = 8282
    GCToGCCheckPlusStatusResponse                                = 8283
    GCToGCReconcilePlusAutoGrantItems                            = 8284
    GCToGCReconcilePlusStatusUnreliable                          = 8285
    GCToClientCavernCrawlMapPathCompleted                        = 8288
    ClientToGCCavernCrawlClaimRoom                               = 8289
    ClientToGCCavernCrawlClaimRoomResponse                       = 8290
    ClientToGCCavernCrawlUseItemOnRoom                           = 8291
    ClientToGCCavernCrawlUseItemOnRoomResponse                   = 8292
    ClientToGCCavernCrawlUseItemOnPath                           = 8293
    ClientToGCCavernCrawlUseItemOnPathResponse                   = 8294
    ClientToGCCavernCrawlRequestMapState                         = 8295
    ClientToGCCavernCrawlRequestMapStateResponse                 = 8296
    SignOutTips                                                  = 8297
    ClientToGCRequestEventPointLogV2                             = 8298
    ClientToGCRequestEventPointLogResponseV2                     = 8299
    ClientToGCRequestEventTipsSummary                            = 8300
    ClientToGCRequestEventTipsSummaryResponse                    = 8301
    ClientToGCRequestSocialFeed                                  = 8303
    ClientToGCRequestSocialFeedResponse                          = 8304
    ClientToGCRequestSocialFeedComments                          = 8305
    ClientToGCRequestSocialFeedCommentsResponse                  = 8306
    ClientToGCCavernCrawlGetClaimedRoomCount                     = 8308
    ClientToGCCavernCrawlGetClaimedRoomCountResponse             = 8309
    GCToGCReconcilePlusAutoGrantItemsUnreliable                  = 8310
    ServerToGCAddBroadcastTimelineEvent                          = 8311
    GCToServerUpdateSteamBroadcasting                            = 8312
    ClientToGCRecordContestVote                                  = 8313
    GCToClientRecordContestVoteResponse                          = 8314
    GCToGCGrantAutograph                                         = 8315
    GCToGCGrantAutographResponse                                 = 8316
    SignOutConsumableUsage                                       = 8317
    LobbyEventGameDetails                                        = 8318
    DevGrantEventPoints                                          = 8319
    DevGrantEventPointsResponse                                  = 8320
    DevGrantEventAction                                          = 8321
    DevGrantEventActionResponse                                  = 8322
    DevResetEventState                                           = 8323
    DevResetEventStateResponse                                   = 8324
    GCToGCReconcileEventOwnership                                = 8325
    ConsumeEventSupportGrantItem                                 = 8326
    ConsumeEventSupportGrantItemResponse                         = 8327
    GCToClientClaimEventActionUsingItemCompleted                 = 8328
    GCToClientCavernCrawlMapUpdated                              = 8329
    ServerToGCRequestPlayerRecentAccomplishments                 = 8330
    ServerToGCRequestPlayerRecentAccomplishmentsResponse         = 8331
    ClientToGCRequestPlayerRecentAccomplishments                 = 8332
    ClientToGCRequestPlayerRecentAccomplishmentsResponse         = 8333
    ClientToGCRequestPlayerHeroRecentAccomplishments             = 8334
    ClientToGCRequestPlayerHeroRecentAccomplishmentsResponse     = 8335
    SignOutEventActionGrants                                     = 8336
    ClientToGCRequestPlayerCoachMatches                          = 8337
    ClientToGCRequestPlayerCoachMatchesResponse                  = 8338
    ClientToGCSubmitCoachTeammateRating                          = 8341
    ClientToGCSubmitCoachTeammateRatingResponse                  = 8342
    GCToClientCoachTeammateRatingsChanged                        = 8343
    ClientToGCRequestPlayerCoachMatch                            = 8345
    ClientToGCRequestPlayerCoachMatchResponse                    = 8346
    ClientToGCRequestContestVotes                                = 8347
    ClientToGCRequestContestVotesResponse                        = 8348
    ClientToGCMVPVoteTimeout                                     = 8349
    ClientToGCMVPVoteTimeoutResponse                             = 8350
    MatchMatchmakingStats                                        = 8360
    ClientToGCSubmitPlayerMatchSurvey                            = 8361
    ClientToGCSubmitPlayerMatchSurveyResponse                    = 8362
    SQLGCToGCGrantAllHeroProgressAccount                         = 8363
    SQLGCToGCGrantAllHeroProgressVictory                         = 8364
    DevDeleteEventActions                                        = 8365
    DevDeleteEventActionsResponse                                = 8366
    GCToGCGetAllHeroCurrent                                      = 8635
    GCToGCGetAllHeroCurrentResponse                              = 8636
    SubmitPlayerAvoidRequest                                     = 8637
    SubmitPlayerAvoidRequestResponse                             = 8638
    GCToClientNotificationsUpdated                               = 8639
    GCtoGCAssociatedExploiterAccountInfo                         = 8640
    GCtoGCAssociatedExploiterAccountInfoResponse                 = 8641
    GCtoGCRequestRecalibrationCheck                              = 8642
    GCToClientVACReminder                                        = 8643
    ClientToGCUnderDraftBuy                                      = 8644
    ClientToGCUnderDraftBuyResponse                              = 8645
    ClientToGCUnderDraftReroll                                   = 8646
    ClientToGCUnderDraftRerollResponse                           = 8647
    NeutralItemStats                                             = 8648
    ClientToGCCreateGuild                                        = 8649
    ClientToGCCreateGuildResponse                                = 8650
    ClientToGCSetGuildInfo                                       = 8651
    ClientToGCSetGuildInfoResponse                               = 8652
    ClientToGCAddGuildRole                                       = 8653
    ClientToGCAddGuildRoleResponse                               = 8654
    ClientToGCModifyGuildRole                                    = 8655
    ClientToGCModifyGuildRoleResponse                            = 8656
    ClientToGCRemoveGuildRole                                    = 8657
    ClientToGCRemoveGuildRoleResponse                            = 8658
    ClientToGCJoinGuild                                          = 8659
    ClientToGCJoinGuildResponse                                  = 8660
    ClientToGCLeaveGuild                                         = 8661
    ClientToGCLeaveGuildResponse                                 = 8662
    ClientToGCInviteToGuild                                      = 8663
    ClientToGCInviteToGuildResponse                              = 8664
    ClientToGCDeclineInviteToGuild                               = 8665
    ClientToGCDeclineInviteToGuildResponse                       = 8666
    ClientToGCCancelInviteToGuild                                = 8667
    ClientToGCCancelInviteToGuildResponse                        = 8668
    ClientToGCKickGuildMember                                    = 8669
    ClientToGCKickGuildMemberResponse                            = 8670
    ClientToGCSetGuildMemberRole                                 = 8671
    ClientToGCSetGuildMemberRoleResponse                         = 8672
    ClientToGCRequestGuildData                                   = 8673
    ClientToGCRequestGuildDataResponse                           = 8674
    GCToClientGuildDataUpdated                                   = 8675
    ClientToGCRequestGuildMembership                             = 8676
    ClientToGCRequestGuildMembershipResponse                     = 8677
    GCToClientGuildMembershipUpdated                             = 8678
    ClientToGCAcceptInviteToGuild                                = 8681
    ClientToGCAcceptInviteToGuildResponse                        = 8682
    ClientToGCSetGuildRoleOrder                                  = 8683
    ClientToGCSetGuildRoleOrderResponse                          = 8684
    ClientToGCRequestGuildFeed                                   = 8685
    ClientToGCRequestGuildFeedResponse                           = 8686
    ClientToGCRequestAccountGuildEventData                       = 8687
    ClientToGCRequestAccountGuildEventDataResponse               = 8688
    GCToClientAccountGuildEventDataUpdated                       = 8689
    ClientToGCRequestActiveGuildContracts                        = 8690
    ClientToGCRequestActiveGuildContractsResponse                = 8691
    GCToClientActiveGuildContractsUpdated                        = 8692
    GCToClientGuildFeedUpdated                                   = 8693
    ClientToGCSelectGuildContract                                = 8694
    ClientToGCSelectGuildContractResponse                        = 8695
    GCToGCCompleteGuildContracts                                 = 8696
    ClientToGCAddPlayerToGuildChat                               = 8698
    ClientToGCAddPlayerToGuildChatResponse                       = 8699
    ClientToGCUnderDraftSell                                     = 8700
    ClientToGCUnderDraftSellResponse                             = 8701
    ClientToGCUnderDraftRequest                                  = 8702
    ClientToGCUnderDraftResponse                                 = 8703
    ClientToGCUnderDraftRedeemReward                             = 8704
    ClientToGCUnderDraftRedeemRewardResponse                     = 8705
    GCToServerLobbyHeroBanRates                                  = 8708
    SignOutGuildContractProgress                                 = 8711
    SignOutMVPStats                                              = 8712
    ClientToGCRequestActiveGuildChallenge                        = 8713
    ClientToGCRequestActiveGuildChallengeResponse                = 8714
    GCToClientActiveGuildChallengeUpdated                        = 8715
    ClientToGCRequestReporterUpdates                             = 8716
    ClientToGCRequestReporterUpdatesResponse                     = 8717
    ClientToGCAcknowledgeReporterUpdates                         = 8718
    SignOutGuildChallengeProgress                                = 8720
    ClientToGCRequestGuildEventMembers                           = 8721
    ClientToGCRequestGuildEventMembersResponse                   = 8722
    ClientToGCReportGuildContent                                 = 8725
    ClientToGCReportGuildContentResponse                         = 8726
    ClientToGCRequestAccountGuildPersonaInfo                     = 8727
    ClientToGCRequestAccountGuildPersonaInfoResponse             = 8728
    ClientToGCRequestAccountGuildPersonaInfoBatch                = 8729
    ClientToGCRequestAccountGuildPersonaInfoBatchResponse        = 8730
    GCToClientUnderDraftGoldUpdated                              = 8731
    GCToServerRecordTrainingData                                 = 8732
    SignOutBounties                                              = 8733
    LobbyFeaturedGamemodeProgress                                = 8734
    LobbyGauntletProgress                                        = 8735
    ClientToGCSubmitDraftTriviaMatchAnswer                       = 8736
    ClientToGCSubmitDraftTriviaMatchAnswerResponse               = 8737
    GCToGCSignoutSpendBounty                                     = 8738
    ClientToGCApplyGauntletTicket                                = 8739
    ClientToGCUnderDraftRollBackBench                            = 8740
    ClientToGCUnderDraftRollBackBenchResponse                    = 8741
    GCToGCGetEventActionScore                                    = 8742
    GCToGCGetEventActionScoreResponse                            = 8743
    ServerToGCGetGuildContracts                                  = 8744
    ServerToGCGetGuildContractsResponse                          = 8745
    LobbyEventGameData                                           = 8746
    GCToClientGuildMembersDataUpdated                            = 8747
    SignOutReportActivityMarkers                                 = 8748
    SignOutDiretideCandy                                         = 8749
    GCToClientPostGameItemAwardNotification                      = 8750
    ClientToGCGetOWMatchDetails                                  = 8751
    ClientToGCGetOWMatchDetailsResponse                          = 8752
    ClientToGCSubmitOWConviction                                 = 8753
    ClientToGCSubmitOWConvictionResponse                         = 8754
    GCToGCGetAccountSteamChina                                   = 8755
    GCToGCGetAccountSteamChinaResponse                           = 8756
    ClientToGCClaimLeaderboardRewards                            = 8757
    ClientToGCClaimLeaderboardRewardsResponse                    = 8758
    ClientToGCRecalibrateMMR                                     = 8759
    ClientToGCRecalibrateMMRResponse                             = 8760
    GCToGCGrantEventPointActionList                              = 8761
    ClientToGCChinaSSAURLRequest                                 = 8764
    ClientToGCChinaSSAURLResponse                                = 8765
    ClientToGCChinaSSAAcceptedRequest                            = 8766
    ClientToGCChinaSSAAcceptedResponse                           = 8767
    SignOutOverwatchSuspicion                                    = 8768
    ServerToGCGetSuspicionConfig                                 = 8769
    ServerToGCGetSuspicionConfigResponse                         = 8770
    GCToGCGrantPlusHeroChallengeMatchResults                     = 8771
    GCToClientOverwatchCasesAvailable                            = 8772
    ServerToGCAccountCheck                                       = 8773
    ClientToGCStartWatchingOverwatch                             = 8774
    ClientToGCStopWatchingOverwatch                              = 8775
    SignOutPerfData                                              = 8776
    ClientToGCGetDPCFavorites                                    = 8777
    ClientToGCGetDPCFavoritesResponse                            = 8778
    ClientToGCSetDPCFavoriteState                                = 8779
    ClientToGCSetDPCFavoriteStateResponse                        = 8780
    ClientToGCOverwatchReplayError                               = 8781
    ServerToGCPlayerChallengeHistory                             = 8782
    SignOutBanData                                               = 8783
    WebapiDPCSeasonResults                                       = 8784
    ClientToGCCoachFriend                                        = 8785
    ClientToGCCoachFriendResponse                                = 8786
    ClientToGCRequestPrivateCoachingSession                      = 8787
    ClientToGCRequestPrivateCoachingSessionResponse              = 8788
    ClientToGCAcceptPrivateCoachingSession                       = 8789
    ClientToGCAcceptPrivateCoachingSessionResponse               = 8790
    ClientToGCLeavePrivateCoachingSession                        = 8791
    ClientToGCLeavePrivateCoachingSessionResponse                = 8792
    ClientToGCGetCurrentPrivateCoachingSession                   = 8793
    ClientToGCGetCurrentPrivateCoachingSessionResponse           = 8794
    GCToClientPrivateCoachingSessionUpdated                      = 8795
    ClientToGCSubmitPrivateCoachingSessionRating                 = 8796
    ClientToGCSubmitPrivateCoachingSessionRatingResponse         = 8797
    ClientToGCGetAvailablePrivateCoachingSessions                = 8798
    ClientToGCGetAvailablePrivateCoachingSessionsResponse        = 8799
    ClientToGCGetAvailablePrivateCoachingSessionsSummary         = 8800
    ClientToGCGetAvailablePrivateCoachingSessionsSummaryResponse = 8801
    ClientToGCJoinPrivateCoachingSessionLobby                    = 8802
    ClientToGCJoinPrivateCoachingSessionLobbyResponse            = 8803
    ClientToGCRespondToCoachFriendRequest                        = 8804
    ClientToGCRespondToCoachFriendRequestResponse                = 8805
    ClientToGCSetEventActiveSeasonID                             = 8806
    ClientToGCSetEventActiveSeasonIDResponse                     = 8807
    ServerToGCMatchPlayerNeutralItemEquipHistory                 = 8808
    ServerToGCCompendiumChosenInGamePredictions                  = 8809
    ClientToGCCreateTeamPlayerCardPack                           = 8810
    ClientToGCCreateTeamPlayerCardPackResponse                   = 8811
    GCToServerSubmitCheerData                                    = 8812
    GCToServerCheerConfig                                        = 8813
    ServerToGCGetCheerConfig                                     = 8814
    ServerToGCGetCheerConfigResponse                             = 8815
    GCToGCGrantAutographByID                                     = 8816
    GCToServerCheerScalesOverride                                = 8817
    GCToServerGetCheerState                                      = 8818
    ServerToGCReportCheerState                                   = 8819
    GCToServerScenarioSave                                       = 8820
    GCToServerAbilityDraftLobbyData                              = 8821
    SignOutReportCommunications                                  = 8822
    ClientToGCBatchGetPlayerCardRosterRequest                    = 8823
    ClientToGCBatchGetPlayerCardRosterResponse                   = 8824
    ClientToGCGetStickerbookRequest                              = 8825
    ClientToGCGetStickerbookResponse                             = 8826
    ClientToGCCreateStickerbookPageRequest                       = 8827
    ClientToGCCreateStickerbookPageResponse                      = 8828
    ClientToGCDeleteStickerbookPageRequest                       = 8829
    ClientToGCDeleteStickerbookPageResponse                      = 8830
    ClientToGCPlaceStickersRequest                               = 8831
    ClientToGCPlaceStickersResponse                              = 8832
    ClientToGCPlaceCollectionStickersRequest                     = 8833
    ClientToGCPlaceCollectionStickersResponse                    = 8834
    ClientToGCOrderStickerbookTeamPageRequest                    = 8835
    ClientToGCOrderStickerbookTeamPageResponse                   = 8836
    ServerToGCGetStickerHeroes                                   = 8837
    ServerToGCGetStickerHeroesResponse                           = 8838
    ClientToGCCandyShopGetUserData                               = 8840
    ClientToGCCandyShopGetUserDataResponse                       = 8841
    GCToClientCandyShopUserDataUpdated                           = 8842
    ClientToGCCandyShopPurchaseReward                            = 8843
    ClientToGCCandyShopPurchaseRewardResponse                    = 8844
    ClientToGCCandyShopDoExchange                                = 8845
    ClientToGCCandyShopDoExchangeResponse                        = 8846
    ClientToGCCandyShopDoVariableExchange                        = 8847
    ClientToGCCandyShopDoVariableExchangeResponse                = 8848
    ClientToGCCandyShopRerollRewards                             = 8849
    ClientToGCCandyShopRerollRewardsResponse                     = 8850
    ClientToGCSetHeroSticker                                     = 8851
    ClientToGCSetHeroStickerResponse                             = 8852
    ClientToGCGetHeroStickers                                    = 8853
    ClientToGCGetHeroStickersResponse                            = 8854
    ClientToGCSetFavoritePage                                    = 8855
    ClientToGCSetFavoritePageResponse                            = 8856
    ClientToGCCandyShopDevGrantCandy                             = 8857
    ClientToGCCandyShopDevGrantCandyResponse                     = 8858
    ClientToGCCandyShopDevClearInventory                         = 8859
    ClientToGCCandyShopDevClearInventoryResponse                 = 8860
    ClientToGCCandyShopOpenBags                                  = 8861
    ClientToGCCandyShopOpenBagsResponse                          = 8862
    ClientToGCCandyShopDevGrantCandyBags                         = 8863
    ClientToGCCandyShopDevGrantCandyBagsResponse                 = 8864
    ClientToGCCandyShopDevShuffleExchange                        = 8865
    ClientToGCCandyShopDevShuffleExchangeResponse                = 8866
    ClientToGCCandyShopDevGrantRerollCharges                     = 8867
    ClientToGCCandyShopDevGrantRerollChargesResponse             = 8868
    LobbyAdditionalAccountData                                   = 8869
    ServerToGCLobbyInitialized                                   = 8870
    ClientToGCCollectorsCacheAvailableDataRequest                = 8871
    GCToClientCollectorsCacheAvailableDataResponse               = 8872
    ClientToGCUploadMatchClip                                    = 8873
    GCToClientUploadMatchClipResponse                            = 8874
    GCToServerSetSteamLearnKeysChanged                           = 8876
    SignOutMuertaMinigame                                        = 8877
    GCToServerLobbyHeroRoleStats                                 = 8878
    ClientToGCRankRequest                                        = 8879
    GCToClientRankResponse                                       = 8880
    GCToClientRankUpdate                                         = 8881
    SignOutMapStats                                              = 8882
    ClientToGCMapStatsRequest                                    = 8883
    GCToClientMapStatsResponse                                   = 8884
    GCToServerSetSteamLearnInferencing                           = 8885
    ClientToGCShowcaseGetUserData                                = 8886
    ClientToGCShowcaseGetUserDataResponse                        = 8887
    ClientToGCShowcaseSetUserData                                = 8888
    ClientToGCShowcaseSetUserDataResponse                        = 8889
    ClientToGCFantasyCraftingGetData                             = 8890
    ClientToGCFantasyCraftingGetDataResponse                     = 8891
    ClientToGCFantasyCraftingPerformOperation                    = 8892
    ClientToGCFantasyCraftingPerformOperationResponse            = 8893
    GCToClientFantasyCraftingGetDataUpdated                      = 8894
    ClientToGCFantasyCraftingDevModifyTablet                     = 8895
    ClientToGCFantasyCraftingDevModifyTabletResponse             = 8896
    ClientToGCRoadToTIGetQuests                                  = 8897
    ClientToGCRoadToTIGetQuestsResponse                          = 8898
    ClientToGCRoadToTIGetActiveQuest                             = 8899
    ClientToGCRoadToTIGetActiveQuestResponse                     = 8900
    ClientToGCBingoGetUserData                                   = 8901
    ClientToGCBingoGetUserDataResponse                           = 8902
    ClientToGCBingoClaimRow                                      = 8903
    ClientToGCBingoClaimRowResponse                              = 8904
    ClientToGCBingoDevRerollCard                                 = 8905
    ClientToGCBingoDevRerollCardResponse                         = 8906
    ClientToGCBingoGetStatsData                                  = 8907
    ClientToGCBingoGetStatsDataResponse                          = 8908
    GCToClientBingoUserDataUpdated                               = 8909
    GCToClientRoadToTIQuestDataUpdated                           = 8910
    ClientToGCRoadToTIUseItem                                    = 8911
    ClientToGCRoadToTIUseItemResponse                            = 8912
    ClientToGCShowcaseSubmitReport                               = 8913
    ClientToGCShowcaseSubmitReportResponse                       = 8914
    ClientToGCShowcaseAdminGetReportsRollupList                  = 8915
    ClientToGCShowcaseAdminGetReportsRollupListResponse          = 8916
    ClientToGCShowcaseAdminGetReportsRollup                      = 8917
    ClientToGCShowcaseAdminGetReportsRollupResponse              = 8918
    ClientToGCShowcaseAdminGetUserDetails                        = 8919
    ClientToGCShowcaseAdminGetUserDetailsResponse                = 8920
    ClientToGCShowcaseAdminConvict                               = 8921
    ClientToGCShowcaseAdminConvictResponse                       = 8922
    ClientToGCShowcaseAdminExonerate                             = 8923
    ClientToGCShowcaseAdminExonerateResponse                     = 8924
    ClientToGCShowcaseAdminReset                                 = 8925
    ClientToGCShowcaseAdminResetResponse                         = 8926
    ClientToGCShowcaseAdminLockAccount                           = 8927
    ClientToGCShowcaseAdminLockAccountResponse                   = 8928
    ClientToGCFantasyCraftingSelectPlayer                        = 8929
    ClientToGCFantasyCraftingSelectPlayerResponse                = 8930
    ClientToGCFantasyCraftingGenerateTablets                     = 8931
    ClientToGCFantasyCraftingGenerateTabletsResponse             = 8932
    ClientToGcFantasyCraftingUpgradeTablets                      = 8933
    ClientToGcFantasyCraftingUpgradeTabletsResponse              = 8934
    ClientToGCFantasyCraftingRerollOptions                       = 8936
    ClientToGCFantasyCraftingRerollOptionsResponse               = 8937
    ClientToGCRoadToTIDevForceQuest                              = 8935
    LobbyRoadToTIMatchQuestData                                  = 8939
    ClientToGCShowcaseModerationGetQueue                         = 8940
    ClientToGCShowcaseModerationGetQueueResponse                 = 8941
    ClientToGCShowcaseModerationApplyModeration                  = 8942
    ClientToGCShowcaseModerationApplyModerationResponse          = 8943
# fmt: on
