from enum import Enum as Enum
from typing import Any, T, Union, overload

# makes things much nicer for linters

# pretend these don't exist :)
class EnumMember:
    name: str
    value: Any

class IntEnumMember(EnumMember): ...

class Enum(Enum):
    @classmethod
    @overload
    def try_value(cls, value: Enum) -> Enum: ...
    @classmethod
    @overload
    def try_value(cls, value: T) -> Union[Enum, T]: ...

class IntEnum(int, Enum): ...

class EResult(IntEnum):
    Invalid: EResult
    OK: EResult
    Fail: EResult
    NoConnection: EResult
    InvalidPassword: EResult
    LoggedInElsewhere: EResult
    InvalidProtocolVersion: EResult
    InvalidParameter: EResult
    FileNotFound: EResult
    Busy: EResult
    InvalidState: EResult
    InvalidName: EResult
    InvalidEmail: EResult
    DuplicateName: EResult
    AccessDenied: EResult
    Timeout: EResult
    Banned: EResult
    AccountNotFound: EResult
    InvalidSteamID: EResult
    ServiceUnavailable: EResult
    NotLoggedOn: EResult
    Pending: EResult
    EncryptionFailure: EResult
    InsufficientPrivilege: EResult
    LimitExceeded: EResult
    Revoked: EResult
    Expired: EResult
    AlreadyRedeemed: EResult
    DuplicateRequest: EResult
    AlreadyOwned: EResult
    IPNotFound: EResult
    PersistFailed: EResult
    LockingFailed: EResult
    LogonSessionReplaced: EResult
    ConnectFailed: EResult
    HandshakeFailed: EResult
    IOFailure: EResult
    RemoteDisconnect: EResult
    ShoppingCartNotFound: EResult
    Blocked: EResult
    Ignored: EResult
    NoMatch: EResult
    AccountDisabled: EResult
    ServiceReadOnly: EResult
    AccountNotFeatured: EResult
    AdministratorOK: EResult
    ContentVersion: EResult
    TryAnotherCM: EResult
    PasswordRequiredToKickSession: EResult
    AlreadyLoggedInElsewhere: EResult
    Suspended: EResult
    Cancelled: EResult
    DataCorruption: EResult
    DiskFull: EResult
    RemoteCallFailed: EResult
    ExternalAccountUnlinked: EResult
    PSNTicketInvalid: EResult
    ExternalAccountAlreadyLinked: EResult
    RemoteFileConflict: EResult
    IllegalPassword: EResult
    SameAsPreviousValue: EResult
    AccountLogonDenied: EResult
    CannotUseOldPassword: EResult
    InvalidLoginAuthCode: EResult
    HardwareNotCapableOfIPT: EResult
    IPTInitError: EResult
    ParentalControlRestricted: EResult
    FacebookQueryError: EResult
    ExpiredLoginAuthCode: EResult
    IPLoginRestrictionFailed: EResult
    VerifiedEmailRequired: EResult
    NoMatchingURL: EResult
    BadResponse: EResult
    RequirePasswordReEntry: EResult
    ValueOutOfRange: EResult
    UnexpectedError: EResult
    Disabled: EResult
    InvalidCEGSubmission: EResult
    RestrictedDevice: EResult
    RegionLocked: EResult
    RateLimitExceeded: EResult
    LoginDeniedNeedTwoFactor: EResult
    ItemDeleted: EResult
    AccountLoginDeniedThrottle: EResult
    TwoFactorCodeMismatch: EResult
    TwoFactorActivationCodeMismatch: EResult
    NotModified: EResult
    TimeNotSynced: EResult
    SMSCodeFailed: EResult
    AccountActivityLimitExceeded: EResult
    PhoneActivityLimitExceeded: EResult
    RefundToWallet: EResult
    EmailSendFailure: EResult
    NotSettled: EResult
    NeedCaptcha: EResult
    GSLTDenied: EResult
    GSOwnerDenied: EResult
    InvalidItemType: EResult
    IPBanned: EResult
    GSLTExpired: EResult
    InsufficientFunds: EResult
    TooManyPending: EResult
    NoSiteLicensesFound: EResult
    WGNetworkSendExceeded: EResult
    AccountNotFriends: EResult
    LimitedUserAccount: EResult
    CantRemoveItem: EResult

class EUniverse(IntEnum):
    Invalid: EUniverse
    Public: EUniverse
    Beta: EUniverse
    Internal: EUniverse
    Dev: EUniverse
    Max: EUniverse
    def __str__(self): ...

class EType(IntEnum):
    Invalid: EType
    Individual: EType
    Multiseat: EType
    GameServer: EType
    AnonGameServer: EType
    Pending: EType
    ContentServer: EType
    Clan: EType
    Chat: EType
    ConsoleUser: EType
    AnonUser: EType
    Max: EType
    def __str__(self): ...

class ETypeChar(IntEnum):
    I: ETypeChar = EType.Invalid
    U: ETypeChar = EType.Individual
    M: ETypeChar = EType.Multiseat
    G: ETypeChar = EType.GameServer
    A: ETypeChar = EType.AnonGameServer
    P: ETypeChar = EType.Pending
    C: ETypeChar = EType.ContentServer
    g: ETypeChar = EType.Clan
    T: ETypeChar = EType.Chat
    L: ETypeChar = EType.Chat
    c: ETypeChar = EType.Chat
    a: ETypeChar = EType.AnonUser
    def __str__(self): ...

class EInstanceFlag(IntEnum):
    MMSLobby: EInstanceFlag
    Lobby: EInstanceFlag
    Clan: EInstanceFlag

class EFriendRelationship(IntEnum):
    NONE: EFriendRelationship
    Blocked: EFriendRelationship
    RequestRecipient: EFriendRelationship
    Friend: EFriendRelationship
    RequestInitiator: EFriendRelationship
    Ignored: EFriendRelationship
    IgnoredFriend: EFriendRelationship
    SuggestedFriend: EFriendRelationship
    Max: EFriendRelationship

class EPersonaState(IntEnum):
    Offline: EPersonaState
    Online: EPersonaState
    Busy: EPersonaState
    Away: EPersonaState
    Snooze: EPersonaState
    LookingToTrade: EPersonaState
    LookingToPlay: EPersonaState
    Max: EPersonaState
    def __str__(self): ...

class EPersonaStateFlag(IntEnum):
    NONE: EPersonaStateFlag
    HasRichPresence: EPersonaStateFlag
    InJoinableGame: EPersonaStateFlag
    Golden: EPersonaStateFlag
    RemotePlayTogether: EPersonaStateFlag
    ClientTypeWeb: EPersonaStateFlag
    ClientTypeMobile: EPersonaStateFlag
    ClientTypeTenfoot: EPersonaStateFlag
    ClientTypeVR: EPersonaStateFlag
    LaunchTypeGamepad: EPersonaStateFlag
    LaunchTypeCompatTool: EPersonaStateFlag
    def __str__(self): ...

class ECommunityVisibilityState(IntEnum):
    NONE: ECommunityVisibilityState
    Private: ECommunityVisibilityState
    FriendsOnly: ECommunityVisibilityState
    Public: ECommunityVisibilityState

class ETradeOfferState(IntEnum):
    Invalid: ETradeOfferState
    Active: ETradeOfferState
    Accepted: ETradeOfferState
    Countered: ETradeOfferState
    Expired: ETradeOfferState
    Canceled: ETradeOfferState
    Declined: ETradeOfferState
    InvalidItems: ETradeOfferState
    ConfirmationNeed: ETradeOfferState
    CanceledBySecondaryFactor: ETradeOfferState
    StateInEscrow: ETradeOfferState

class EChatEntryType(IntEnum):
    Invalid: EChatEntryType
    ChatMsg: EChatEntryType
    Typing: EChatEntryType
    InviteGame: EChatEntryType
    LeftConversation: EChatEntryType
    Entered: EChatEntryType
    WasKicked: EChatEntryType
    WasBanned: EChatEntryType
    Disconnected: EChatEntryType
    HistoricalChat: EChatEntryType
    LinkBlocked: EChatEntryType

class EUIMode(IntEnum):
    Desktop: EUIMode
    BigPicture: EUIMode
    Mobile: EUIMode
    Web: EUIMode

class EUserBadge(IntEnum):
    Invalid: EUserBadge
    YearsOfService: EUserBadge
    Community: EUserBadge
    Portal2PotatoARG: EUserBadge
    TreasureHunt: EUserBadge
    SummerSale2011: EUserBadge
    WinterSale2011: EUserBadge
    SummerSale2012: EUserBadge
    WinterSale2012: EUserBadge
    CommunityTranslator: EUserBadge
    CommunityModerator: EUserBadge
    ValveEmployee: EUserBadge
    GameDeveloper: EUserBadge
    GameCollector: EUserBadge
    TradingCardBetaParticipant: EUserBadge
    SteamBoxBeta: EUserBadge
    Summer2014RedTeam: EUserBadge
    Summer2014BlueTeam: EUserBadge
    Summer2014PinkTeam: EUserBadge
    Summer2014GreenTeam: EUserBadge
    Summer2014PurpleTeam: EUserBadge
    Auction2014: EUserBadge
    GoldenProfile2014: EUserBadge
    TowerAttackMiniGame: EUserBadge
    Winter2015ARG_RedHerring: EUserBadge
    SteamAwards2016Nominations: EUserBadge
    StickerCompletionist2017: EUserBadge
    SteamAwards2017Nominations: EUserBadge
    SpringCleaning2018: EUserBadge
    Salien: EUserBadge
    RetiredModerator: EUserBadge
    SteamAwards2018Nominations: EUserBadge
    ValveModerator: EUserBadge
    WinterSale2018: EUserBadge
    LunarNewYearSale2019: EUserBadge
    LunarNewYearSale2019GoldenProfile: EUserBadge
    SpringCleaning2019: EUserBadge
    Summer2019: EUserBadge
    Summer2019TeamHare: EUserBadge
    Summer2019TeamTortoise: EUserBadge
    Summer2019TeamCorgi: EUserBadge
    Summer2019TeamCockatiel: EUserBadge
    Summer2019TeamPig: EUserBadge
    SteamAwards2019Nominations: EUserBadge
    WinterSaleEvent2019: EUserBadge
