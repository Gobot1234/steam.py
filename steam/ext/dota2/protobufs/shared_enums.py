# Generated by the protocol buffer compiler.  DO NOT EDIT!
# sources: dota_shared_enums.proto
# plugin: python-betterproto


import betterproto


class EMatchGroupServerStatus(betterproto.Enum):
    OK = 0
    LimitedAvailability = 1
    Offline = 2


class GameMode(betterproto.Enum):
    NONE = 0
    AllPick = 1
    CaptainsMode = 2
    RandomDraft = 3
    SingleDraft = 4
    AllRandom = 5
    Intro = 6
    Diretide = 7
    ReverseCaptainsMode = 8
    Frostivus = 9
    Tutorial = 10
    MidOnly = 11
    LeastPlayed = 12
    NewPlayerMode = 13
    CompendiumMatch = 14
    Custom = 15
    CaptainsDraft = 16
    BalancedDraft = 17
    AbilityDraft = 18
    Event = 19
    AllRandomDeathMatch = 20
    Mid1v1 = 21
    AllDraft = 22
    Turbo = 23
    Mutation = 24
    CoachesChallenge = 25


class Team(betterproto.Enum):
    GoodGuys = 0
    BadGuys = 1
    Broadcaster = 2
    Spectator = 3
    PlayerPool = 4
    NoTeam = 5
    Custom1 = 6
    Custom2 = 7
    Custom3 = 8
    Custom4 = 9
    Custom5 = 10
    Custom6 = 11
    Custom7 = 12
    Custom8 = 13
    Neutrals = 14


class EMatchOutcome(betterproto.Enum):
    Unknown = 0
    RadVictory = 2
    DireVictory = 3
    NeutralVictory = 4
    NoTeamWinner = 5
    Custom1Victory = 6
    Custom2Victory = 7
    Custom3Victory = 8
    Custom4Victory = 9
    Custom5Victory = 10
    Custom6Victory = 11
    Custom7Victory = 12
    Custom8Victory = 13
    NotScoredPoorNetworkConditions = 64
    NotScoredLeaver = 65
    NotScoredServerCrash = 66
    NotScoredNeverStarted = 67
    NotScoredCanceled = 68
    NotScoredSuspicious = 69


class MatchVote(betterproto.Enum):
    Invalid = 0
    Positive = 1
    Negative = 2


class EEvent(betterproto.Enum):
    NONE = 0
    Diretide = 1
    SpringFestival = 2
    Frostivus2013 = 3
    Compendium2014 = 4
    NexonPcBang = 5
    PwrdDac2015 = 6
    NewBloom2015 = 7
    International2015 = 8
    FallMajor2015 = 9
    OraclePa = 10
    NewBloom2015Prebeast = 11
    Frostivus = 12
    WinterMajor2016 = 13
    International2016 = 14
    FallMajor2016 = 15
    WinterMajor2017 = 16
    NewBloom2017 = 17
    International2017 = 18
    PlusSubscription = 19
    SinglesDay2017 = 20
    Frostivus2017 = 21
    International2018 = 22
    Frostivus2018 = 23
    NewBloom2019 = 24
    International2019 = 25
    NewPlayerExperience = 26
    Frostivus2019 = 27
    NewBloom2020 = 28
    International2020 = 29
    TeamFandom = 30
    Diretide2020 = 31
    Spring2021 = 32
    Fall2021 = 33
    TeamFandomFall2021 = 34
    Team20212022Tour2 = 35
    International2022 = 36
    Team20212022Tour3 = 37
    TeamInternational2022 = 38
    PermanentGrants = 39
    MuertaReleaseSpring2023 = 40
    Team2023Tour1 = 41
    Team2023Tour2 = 42
    Team023Tour3 = 43
    International2023 = 45
    TenthAnniversary = 46
    Frostivus2023 = 48
