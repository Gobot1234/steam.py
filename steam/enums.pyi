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

# fmt: off

class EResult(IntEnum):
    Invalid: IntEnum                         = 0
    OK: IntEnum                              = 1  #: Success
    Fail: IntEnum                            = 2  #: Generic failure
    NoConnection: IntEnum                    = 3  #: No/failed network connection
    InvalidPassword: IntEnum                 = 5  #: Password/ticket is invalid
    LoggedInElsewhere: IntEnum               = 6  #: Same user logged in elsewhere
    InvalidProtocolVersion: IntEnum          = 7
    InvalidParameter: IntEnum                = 8
    FileNotFound: IntEnum                    = 9
    Busy: IntEnum                            = 10  #: Called method busy - action not taken
    InvalidState: IntEnum                    = 11  #: Called object was in an invalid state
    InvalidName: IntEnum                     = 12
    InvalidEmail: IntEnum                    = 13
    DuplicateName: IntEnum                   = 14
    AccessDenied: IntEnum                    = 15
    Timeout: IntEnum                         = 16
    Banned: IntEnum                          = 17  #: VAC2 banned
    AccountNotFound: IntEnum                 = 18
    InvalidSteamID: IntEnum                  = 19
    ServiceUnavailable: IntEnum              = 20  #: The requested service is currently unavailable
    NotLoggedOn: IntEnum                     = 21
    Pending: IntEnum                         = 22  #: Request is pending (may be in process, or waiting on third party)
    EncryptionFailure: IntEnum               = 23
    InsufficientPrivilege: IntEnum           = 24
    LimitExceeded: IntEnum                   = 25  #: Too much of a good thing
    Revoked: IntEnum                         = 26  #: Access has been revoked (used for revoked guest passes)
    Expired: IntEnum                         = 27  #: License/Guest pass the user is trying to access is expired
    AlreadyRedeemed: IntEnum                 = 28  #: Guest pass has already been redeemed by account, cannot be acked again
    DuplicateRequest: IntEnum                = 29
    AlreadyOwned: IntEnum                    = 30  #: All the games in guest pass redemption request are already owned by the user
    IPNotFound: IntEnum                      = 31
    PersistFailed: IntEnum                   = 32  #: Failed to write change to the data store
    LockingFailed: IntEnum                   = 33  #: Failed to acquire access lock for this operation
    LogonSessionReplaced: IntEnum            = 34
    ConnectFailed: IntEnum                   = 35
    HandshakeFailed: IntEnum                 = 36
    IOFailure: IntEnum                       = 37
    RemoteDisconnect: IntEnum                = 38
    ShoppingCartNotFound: IntEnum            = 39
    Blocked: IntEnum                         = 40
    Ignored: IntEnum                         = 41
    NoMatch: IntEnum                         = 42
    AccountDisabled: IntEnum                 = 43
    ServiceReadOnly: IntEnum                 = 44
    AccountNotFeatured: IntEnum              = 45  #: Account doesn't have value, so this feature isn't available
    AdministratorOK: IntEnum                 = 46  #: Allowed to take this action, but only because requester is admin
    ContentVersion: IntEnum                  = 47  #: A Version mismatch in content transmitted within the Steam protocol
    TryAnotherCM: IntEnum                    = 48  #: The current CM can't service the user making a request, should try another
    PasswordRequiredToKickSession: IntEnum   = 49  #: You are already logged in elsewhere, this cached credential login has failed
    AlreadyLoggedInElsewhere: IntEnum        = 50  #: You are already logged in elsewhere, you must wait
    Suspended: IntEnum                       = 51  #: Long running operation (content download) suspended/paused
    Cancelled: IntEnum                       = 52  #: Operation canceled (typically by user content download)
    DataCorruption: IntEnum                  = 53  #: Operation canceled because data is ill formed or unrecoverable
    DiskFull: IntEnum                        = 54  #: Operation canceled - not enough disk space.
    RemoteCallFailed: IntEnum                = 55  #: An remote call or IPC call failed
    ExternalAccountUnlinked: IntEnum         = 57  #: External account (PSN, Facebook...) is not linked to a Steam account
    PSNTicketInvalid: IntEnum                = 58  #: PSN ticket was invalid
    ExternalAccountAlreadyLinked: IntEnum    = 59  #: External account (PSN, Facebook...) is already linked to some other account
    RemoteFileConflict: IntEnum              = 60  #: The sync cannot resume due to a conflict between the local and remote files
    IllegalPassword: IntEnum                 = 61  #: The requested new password is not legal
    SameAsPreviousValue: IntEnum             = 62  #: New value is the same as the old one (secret question and answer)
    AccountLogonDenied: IntEnum              = 63  #: Account login denied due to 2nd factor authentication failure
    CannotUseOldPassword: IntEnum            = 64  #: The requested new password is not legal
    InvalidLoginAuthCode: IntEnum            = 65  #: Account login denied due to auth code invalid
    HardwareNotCapableOfIPT: IntEnum         = 67
    IPTInitError: IntEnum                    = 68
    ParentalControlRestricted: IntEnum       = 69  #: Operation failed due to parental control restrictions for current user
    FacebookQueryError: IntEnum              = 70
    ExpiredLoginAuthCode: IntEnum            = 71  #: Account login denied due to auth code expired
    IPLoginRestrictionFailed:  int       = 72
    VerifiedEmailRequired: IntEnum           = 74
    NoMatchingURL: IntEnum                   = 75
    BadResponse: IntEnum                     = 76  #: Parse failure, missing field, etc.
    RequirePasswordReEntry: IntEnum          = 77  #: The user cannot complete the action until they re-enter their password
    ValueOutOfRange: IntEnum                 = 78  #: The value entered is outside the acceptable range
    UnexpectedError: IntEnum                 = 79  #: Something happened that we didn't expect to ever happen
    Disabled: IntEnum                        = 80  #: The requested service has been configured to be unavailable
    InvalidCEGSubmission: IntEnum            = 81  #: The set of files submitted to the CEG server are not valid!
    RestrictedDevice: IntEnum                = 82  #: The device being used is not allowed to perform this action
    RegionLocked: IntEnum                    = 83  #: The action could not be complete because it is region restricted
    RateLimitExceeded: IntEnum               = 84  #: Temporary rate limit exceeded. different from k_EResultLimitExceeded
    LoginDeniedNeedTwoFactor: IntEnum        = 85  #: Need two-factor code to login
    ItemDeleted: IntEnum                     = 86  #: The thing we're trying to access has been deleted
    AccountLoginDeniedThrottle: IntEnum      = 87  #: Login attempt failed, try to throttle response to possible attacker
    TwoFactorCodeMismatch: IntEnum           = 88  #: Two factor code mismatch
    TwoFactorActivationCodeMismatch: IntEnum = 89  #: Activation code for two-factor didn't match
    NotModified: IntEnum                     = 91  #: Data not modified
    TimeNotSynced: IntEnum                   = 93  #: The time presented is out of range or tolerance
    SMSCodeFailed: IntEnum                   = 94  #: SMS code failure (no match, none pending, etc.)
    AccountActivityLimitExceeded: IntEnum    = 96  #: Too many changes to this account
    PhoneActivityLimitExceeded: IntEnum      = 97  #: Too many changes to this phone
    RefundToWallet: IntEnum                  = 98  #: Cannot refund to payment method, must use wallet
    EmailSendFailure: IntEnum                = 99  #: Cannot send an email
    NotSettled: IntEnum                      = 100  #: Can't perform operation till payment has settled
    NeedCaptcha: IntEnum                     = 101  #: Needs to provide a valid captcha
    GSLTDenied: IntEnum                      = 102  #: A game server login token owned by this token's owner has been banned
    GSOwnerDenied: IntEnum                   = 103  #: Game server owner is denied for other reason
    InvalidItemType: IntEnum                 = 104  #: The type of thing we were requested to act on is invalid
    IPBanned: IntEnum                        = 105  #: The ip address has been banned from taking this action
    GSLTExpired: IntEnum                     = 106  #: This token has expired from disuse; can be reset for use
    InsufficientFunds: IntEnum               = 107  #: User doesn't have enough wallet funds to complete the action
    TooManyPending: IntEnum                  = 108  #: There are too many of this thing pending already
    NoSiteLicensesFound: IntEnum             = 109  #: No site licenses found
    WGNetworkSendExceeded: IntEnum           = 110  #: The WG couldn't send a response because we exceeded max network send size
    AccountNotFriends:  IntEnum              = 111
    LimitedUserAccount: IntEnum              = 112
    CantRemoveItem: IntEnum                  = 113


class EUniverse(IntEnum):
    Invalid: IntEnum  = 0
    Public: IntEnum   = 1
    Beta: IntEnum     = 2
    Internal: IntEnum = 3
    Dev: IntEnum      = 4
    Max: IntEnum      = 6

    def __str__(self):
        return self.name


class EType(IntEnum):
    Invalid: IntEnum        = 0
    Individual: IntEnum     = 1  #: Single user account
    Multiseat: IntEnum      = 2  #: Multiseat (e.g. cybercafe) account
    GameServer: IntEnum     = 3  #: Game server account
    AnonGameServer: IntEnum = 4  #: Anonymous game server account
    Pending: IntEnum        = 5
    ContentServer: IntEnum  = 6  #: Content server
    Clan: IntEnum           = 7
    Chat: IntEnum           = 8
    ConsoleUser: IntEnum    = 9  #: Fake SteamID for local PSN account on PS3 or Live account on 360, etc.
    AnonUser: IntEnum       = 10
    Max: IntEnum            = 11

    def __str__(self):
        return self.name


class ETypeChar(IntEnum):
    I: IntEnum = EType.Invalid
    U: IntEnum = EType.Individual
    M: IntEnum = EType.Multiseat
    G: IntEnum = EType.GameServer
    A: IntEnum = EType.AnonGameServer
    P: IntEnum = EType.Pending
    C: IntEnum = EType.ContentServer
    g: IntEnum = EType.Clan
    T: IntEnum = EType.Chat
    L: IntEnum = EType.Chat  #: Lobby/group chat, 'c' for clan chat
    c: IntEnum = EType.Chat  #: Clan chat
    a: IntEnum = EType.AnonUser

    def __str__(self):
        return self.name


class EInstanceFlag(IntEnum):
    MMSLobby = 0x20000
    Lobby    = 0x40000
    Clan     = 0x80000


class EFriendRelationship(IntEnum):
    NONE: IntEnum             = 0
    Blocked: IntEnum          = 1
    RequestRecipient: IntEnum = 2
    Friend: IntEnum           = 3
    RequestInitiator: IntEnum = 4
    Ignored: IntEnum          = 5
    IgnoredFriend: IntEnum    = 6
    SuggestedFriend: IntEnum  = 7
    Max: IntEnum              = 8


class EPersonaState(IntEnum):
    Offline: IntEnum        = 0
    Online: IntEnum         = 1
    Busy: IntEnum           = 2
    Away: IntEnum           = 3
    Snooze: IntEnum         = 4
    LookingToTrade: IntEnum = 5
    LookingToPlay: IntEnum  = 6
    Max: IntEnum            = 7

    def __str__(self):
        return self.name


class EPersonaStateFlag(IntEnum):
    NONE: IntEnum                 = 0
    HasRichPresence: IntEnum      = 1
    InJoinableGame: IntEnum       = 2
    Golden: IntEnum               = 4
    RemotePlayTogether: IntEnum   = 8
    ClientTypeWeb: IntEnum        = 256
    ClientTypeMobile: IntEnum     = 512
    ClientTypeTenfoot: IntEnum    = 1024
    ClientTypeVR: IntEnum         = 2048
    LaunchTypeGamepad: IntEnum    = 4096
    LaunchTypeCompatTool: IntEnum = 8192

    def __str__(self):
        return self.name


class ECommunityVisibilityState(IntEnum):
    NONE: IntEnum        = 0
    Private: IntEnum     = 1
    FriendsOnly: IntEnum = 2
    Public: IntEnum      = 3


class ETradeOfferState(IntEnum):
    Invalid: IntEnum                   = 1
    Active: IntEnum                    = 2
    Accepted: IntEnum                  = 3
    Countered: IntEnum                 = 4
    Expired: IntEnum                   = 5
    Canceled: IntEnum                  = 6
    Declined: IntEnum                  = 7
    InvalidItems: IntEnum              = 8
    ConfirmationNeed: IntEnum          = 9
    CanceledBySecondaryFactor: IntEnum = 10
    StateInEscrow: IntEnum             = 11


class EChatEntryType(IntEnum):
    Invalid: IntEnum          = 0
    ChatMsg: IntEnum          = 1  #: Normal text message from another user
    Typing: IntEnum           = 2  #: Another user is typing (not used in multi-user chat)
    InviteGame: IntEnum       = 3  #: Invite from other user into that users current game
    LeftConversation: IntEnum = 6  #: user has left the conversation ( closed chat window )
    Entered: IntEnum          = 7  #: User has entered the conversation (used in multi-user chat and group chat)
    WasKicked: IntEnum        = 8  #: user was kicked (data: 64-bit steamid of actor performing the kick)
    WasBanned: IntEnum        = 9  #: user was banned (data: 64-bit steamid of actor performing the ban)
    Disconnected: IntEnum     = 10  #: user disconnected
    HistoricalChat: IntEnum   = 11  #: a chat message from user's chat history or offline message
    LinkBlocked: IntEnum      = 14  #: a link was removed by the chat filter.


class EUIMode(IntEnum):
    Desktop: IntEnum    = 0
    BigPicture: IntEnum = 1
    Mobile: IntEnum     = 2
    Web: IntEnum        = 3


class EUserBadge(IntEnum):
    Invalid: IntEnum                           = 0
    YearsOfService: IntEnum                    = 1
    Community: IntEnum                         = 2
    Portal2PotatoARG: IntEnum                  = 3
    TreasureHunt: IntEnum                      = 4
    SummerSale2011: IntEnum                    = 5
    WinterSale2011: IntEnum                    = 6
    SummerSale2012: IntEnum                    = 7
    WinterSale2012: IntEnum                    = 8
    CommunityTranslator: IntEnum               = 9
    CommunityModerator: IntEnum                = 10
    ValveEmployee: IntEnum                     = 11
    GameDeveloper: IntEnum                     = 12
    GameCollector: IntEnum                     = 13
    TradingCardBetaParticipant: IntEnum        = 14
    SteamBoxBeta: IntEnum                      = 15
    Summer2014RedTeam: IntEnum                 = 16
    Summer2014BlueTeam: IntEnum                = 17
    Summer2014PinkTeam: IntEnum                = 18
    Summer2014GreenTeam: IntEnum               = 19
    Summer2014PurpleTeam: IntEnum              = 20
    Auction2014: IntEnum                       = 21
    GoldenProfile2014: IntEnum                 = 22
    TowerAttackMiniGame: IntEnum               = 23
    Winter2015ARG_RedHerring: IntEnum          = 24
    SteamAwards2016Nominations: IntEnum        = 25
    StickerCompletionist2017: IntEnum          = 26
    SteamAwards2017Nominations: IntEnum        = 27
    SpringCleaning2018: IntEnum                = 28
    Salien: IntEnum                            = 29
    RetiredModerator: IntEnum                  = 30
    SteamAwards2018Nominations: IntEnum        = 31
    ValveModerator: IntEnum                    = 32
    WinterSale2018: IntEnum                    = 33
    LunarNewYearSale2019: IntEnum              = 34
    LunarNewYearSale2019GoldenProfile: IntEnum = 35
    SpringCleaning2019: IntEnum                = 36
    Summer2019: IntEnum                        = 37
    Summer2019TeamHare: IntEnum                = 38
    Summer2019TeamTortoise: IntEnum            = 39
    Summer2019TeamCorgi: IntEnum               = 40
    Summer2019TeamCockatiel: IntEnum           = 41
    Summer2019TeamPig: IntEnum                 = 42
    SteamAwards2019Nominations: IntEnum        = 43
    WinterSaleEvent2019: IntEnum               = 44
