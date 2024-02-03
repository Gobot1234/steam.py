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
