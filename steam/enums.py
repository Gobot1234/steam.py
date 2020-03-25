# -*- coding: utf-8 -*-

"""
Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Taken from https://github.com/ValvePython/steam/blob/master/steam/enums/common.py
"""

import enum
from collections import namedtuple


class URL:
    API = 'https://api.steampowered.com'
    COMMUNITY = 'https://steamcommunity.com'
    STORE = 'https://store.steampowered.com'


GAME_TUPLE = namedtuple('GAME_TUPLE', ('title', 'app_id', 'context_id', 'is_steam_game'))
GAMES = {
        440: GAME_TUPLE('Team Fortress 2', 440, 2, True),
        570: GAME_TUPLE('DOTA 2', 570, 2, True),
        730: GAME_TUPLE('Counter Strike Global-Offensive', 730, 2, True),
        753: GAME_TUPLE('Steam', 753, 6, True),
        'Team Fortress 2': GAME_TUPLE('Team Fortress 2', 440, 2, True),
        'TF2': GAME_TUPLE('Team Fortress 2', 440, 2, True),
        'DOTA 2': GAME_TUPLE('DOTA 2', 570, 2, True),
        'Counter Strike Global-Offensive': GAME_TUPLE('Counter Strike Global-Offensive', 730, 2, True),
        'CSGO': GAME_TUPLE('Counter Strike Global-Offensive', 730, 2, True),
        'Steam': GAME_TUPLE('Steam', 753, 6, True)
    }


class Game:
    """Represents a Steam game.

    Parameters
    ----------
    title: Optional[:class:`str`]
        The game's title.
    app_id: Optional[:class:`int`]
        The game's app_id.
    is_steam_game: Optional[bool]
        Whether or not the game is an official Steam game.
        Defaults to ``True``

    Attributes
    -----------
    title: Optional[:class:`str`]
        The game's title.
    app_id: Optional[:class:`int`]
        The game's app_id.
    context_id: :class:`int`
        The context id of the game normally 2.
    is_steam_game: bool
        Whether or not the game is an official Steam game.
    """

    __slots__ = ('title', 'app_id', 'context_id', 'is_steam_game', '_game')

    def __init__(self, *, title: str = None, app_id: int = None, is_steam_game: bool = True):
        try:
            if title:
                self._game = GAMES[title]
            elif app_id:
                self._game = GAMES[app_id]
            elif not is_steam_game:
                self.title = title
                self.app_id = None
                self.context_id = None
                self.is_steam_game = False
            else:
                raise ValueError('missing a game title or app_id kwarg')
        except KeyError:  # Make the game a fake game
            self.title = title
            self.app_id = app_id
            self.context_id = 2
            self.is_steam_game = True
        else:
            self.title = self._game[0]
            self.app_id = self._game[1]
            self.context_id = self._game[2]
            self.is_steam_game = self._game[3]

    def __repr__(self):
        attrs = (
            'title', 'app_id', 'context_id'
        )
        resolved = [f'{attr}={repr(getattr(self, attr))}' for attr in attrs]
        return f"<Game {' '.join(resolved)}>"

    def __eq__(self, other):
        return isinstance(other, Game) and self.app_id == other.app_id

    def __ne__(self, other):
        return not self.__eq__(other)


class EResult(enum.IntEnum):
    Invalid = 0
    OK = 1  #: Success
    Fail = 2  #: Generic failure
    NoConnection = 3  #: No/failed network connection
    InvalidPassword = 5  #: Password/ticket is invalid
    LoggedInElsewhere = 6  #: Same user logged in elsewhere
    InvalidProtocolVersion = 7
    InvalidParameter = 8
    FileNotFound = 9
    Busy = 10  #: Called method busy - action not taken
    InvalidState = 11  #: Called object was in an invalid state
    InvalidName = 12
    InvalidEmail = 13
    DuplicateName = 14
    AccessDenied = 15
    Timeout = 16
    Banned = 17  #: VAC2 banned
    AccountNotFound = 18
    InvalidSteamID = 19
    ServiceUnavailable = 20  #: The requested service is currently unavailable
    NotLoggedOn = 21
    Pending = 22  #: Request is pending (may be in process, or waiting on third party)
    EncryptionFailure = 23
    InsufficientPrivilege = 24
    LimitExceeded = 25  #: Too much of a good thing
    Revoked = 26  #: Access has been revoked (used for revoked guest passes)
    Expired = 27  #: License/Guest pass the user is trying to access is expired
    AlreadyRedeemed = 28  #: Guest pass has already been redeemed by account, cannot be acked again
    DuplicateRequest = 29
    AlreadyOwned = 30  #: All the games in guest pass redemption request are already owned by the user
    IPNotFound = 31
    PersistFailed = 32  #: Failed to write change to the data store
    LockingFailed = 33  #: Failed to acquire access lock for this operation
    LogonSessionReplaced = 34
    ConnectFailed = 35
    HandshakeFailed = 36
    IOFailure = 37
    RemoteDisconnect = 38
    ShoppingCartNotFound = 39
    Blocked = 40
    Ignored = 41
    NoMatch = 42
    AccountDisabled = 43
    ServiceReadOnly = 44
    AccountNotFeatured = 45  #: Account doesn't have value, so this feature isn't available
    AdministratorOK = 46  #: Allowed to take this action, but only because requester is admin
    ContentVersion = 47  #: A Version mismatch in content transmitted within the Steam protocol
    TryAnotherCM = 48  #: The current CM can't service the user making a request, should try another
    PasswordRequiredToKickSession = 49  #: You are already logged in elsewhere, this cached credential login has failed
    AlreadyLoggedInElsewhere = 50  #: You are already logged in elsewhere, you must wait
    Suspended = 51  #: Long running operation (content download) suspended/paused
    Cancelled = 52  #: Operation canceled (typically by user content download)
    DataCorruption = 53  #: Operation canceled because data is ill formed or unrecoverable
    DiskFull = 54  #: Operation canceled - not enough disk space.
    RemoteCallFailed = 55  #: An remote call or IPC call failed
    PasswordUnset = 56  #: Password could not be verified as it's unset server side
    ExternalAccountUnlinked = 57  #: External account (PSN, Facebook...) is not linked to a Steam account
    PSNTicketInvalid = 58  #: PSN ticket was invalid
    ExternalAccountAlreadyLinked = 59  #: External account (PSN, Facebook...) is already linked to some other account
    RemoteFileConflict = 60  #: The sync cannot resume due to a conflict between the local and remote files
    IllegalPassword = 61  #: The requested new password is not legal
    SameAsPreviousValue = 62  #: New value is the same as the old one (secret question and answer)
    AccountLogonDenied = 63  #: Account login denied due to 2nd factor authentication failure
    CannotUseOldPassword = 64  #: The requested new password is not legal
    InvalidLoginAuthCode = 65  #: Account login denied due to auth code invalid
    AccountLogonDeniedNoMail = 66  #: Account login denied due to 2nd factor auth failure and no mail has been sent
    HardwareNotCapableOfIPT = 67
    IPTInitError = 68
    ParentalControlRestricted = 69  #: Operation failed due to parental control restrictions for current user
    FacebookQueryError = 70
    ExpiredLoginAuthCode = 71  #: Account login denied due to auth code expired
    IPLoginRestrictionFailed = 72
    AccountLockedDown = 73
    VerifiedEmailRequired = 74
    NoMatchingURL = 75
    BadResponse = 76  #: Parse failure, missing field, etc.
    RequirePasswordReEntry = 77  #: The user cannot complete the action until they re-enter their password
    ValueOutOfRange = 78  #: The value entered is outside the acceptable range
    UnexpectedError = 79  #: Something happened that we didn't expect to ever happen
    Disabled = 80  #: The requested service has been configured to be unavailable
    InvalidCEGSubmission = 81  #: The set of files submitted to the CEG server are not valid!
    RestrictedDevice = 82  #: The device being used is not allowed to perform this action
    RegionLocked = 83  #: The action could not be complete because it is region restricted
    RateLimitExceeded = 84  #: Temporary rate limit exceeded. different from k_EResultLimitExceeded
    LoginDeniedNeedTwoFactor = 85  #: Need two-factor code to login
    ItemDeleted = 86  #: The thing we're trying to access has been deleted
    AccountLoginDeniedThrottle = 87  #: Login attempt failed, try to throttle response to possible attacker
    TwoFactorCodeMismatch = 88  #: Two factor code mismatch
    TwoFactorActivationCodeMismatch = 89  #: Activation code for two-factor didn't match
    AccountAssociatedToMultiplePartners = 90  #: Account has been associated with multiple partners
    NotModified = 91  #: Data not modified
    NoMobileDevice = 92  #: The account does not have a mobile device associated with it
    TimeNotSynced = 93  #: The time presented is out of range or tolerance
    SMSCodeFailed = 94  #: SMS code failure (no match, none pending, etc.)
    AccountLimitExceeded = 95  #: Too many accounts access this resource
    AccountActivityLimitExceeded = 96  #: Too many changes to this account
    PhoneActivityLimitExceeded = 97  #: Too many changes to this phone
    RefundToWallet = 98  #: Cannot refund to payment method, must use wallet
    EmailSendFailure = 99  #: Cannot send an email
    NotSettled = 100  #: Can't perform operation till payment has settled
    NeedCaptcha = 101  #: Needs to provide a valid captcha
    GSLTDenied = 102  #: A game server login token owned by this token's owner has been banned
    GSOwnerDenied = 103  #: Game server owner is denied for other reason
    InvalidItemType = 104  #: The type of thing we were requested to act on is invalid
    IPBanned = 105  #: The ip address has been banned from taking this action
    GSLTExpired = 106  #: This token has expired from disuse; can be reset for use
    InsufficientFunds = 107  #: User doesn't have enough wallet funds to complete the action
    TooManyPending = 108  #: There are too many of this thing pending already
    NoSiteLicensesFound = 109  #: No site licenses found
    WGNetworkSendExceeded = 110  #: The WG couldn't send a response because we exceeded max network send size


class EUniverse(enum.IntEnum):
    Invalid = 0
    Public = 1
    Beta = 2
    Internal = 3
    Dev = 4
    Max = 6


class EType(enum.IntEnum):
    Invalid = 0
    Individual = 1  #: Single user account
    Multiseat = 2  #: Multiseat (e.g. cybercafe) account
    GameServer = 3  #: Game server account
    AnonGameServer = 4  #: Anonymous game server account
    Pending = 5
    ContentServer = 6  #: Content server
    Clan = 7
    Chat = 8
    ConsoleUser = 9  #: Fake SteamID for local PSN account on PS3 or Live account on 360, etc.
    AnonUser = 10
    Max = 11


class ETypeChar(enum.IntEnum):
    I = EType.Invalid
    U = EType.Individual
    M = EType.Multiseat
    G = EType.GameServer
    A = EType.AnonGameServer
    P = EType.Pending
    C = EType.ContentServer
    g = EType.Clan
    T = EType.Chat
    L = EType.Chat  # lobby chat, 'c' for clan chat
    c = EType.Chat  # clan chat
    a = EType.AnonUser

    def __str__(self):
        return self.name


class EInstanceFlag(enum.IntEnum):
    MMSLobby = 0x20000
    Lobby = 0x40000
    Clan = 0x80000


class EFriendRelationship(enum.IntEnum):
    NONE = 0
    Blocked = 1
    RequestRecipient = 2
    Friend = 3
    RequestInitiator = 4
    Ignored = 5
    IgnoredFriend = 6
    SuggestedFriend = 7
    Max = 8


class EPersonaState(enum.Enum):
    Offline = 0
    Online = 1
    Busy = 2
    Away = 3
    Snooze = 4
    LookingToTrade = 5
    LookingToPlay = 6
    Max = 7

    def __str__(self):
        return self.name


class EPersonaStateFlag(enum.IntEnum):
    NONE = 0
    HasRichPresence = 1
    InJoinableGame = 2
    HasGoldenProfile = 4
    ClientTypeWeb = 256
    ClientTypeMobile = 512
    ClientTypeTenfoot = 1024
    ClientTypeVR = 2048
    LaunchTypeGamepad = 4096

    def __str__(self):
        return self.name


class ECommunityVisibilityState(enum.IntEnum):
    NONE = 0
    Private = 1
    FriendsOnly = 2
    Public = 3


class EChatRoomEnterResponse(enum.IntEnum):
    Success = 1  #: Success
    DoesntExist = 2  #: Chat doesn't exist (probably closed)
    NotAllowed = 3  #: General Denied - You don't have the permissions needed to join the chat
    Full = 4  #: Chat room has reached its maximum size
    Error = 5  #: Unexpected Error
    Banned = 6  #: You are banned from this chat room and may not join
    Limited = 7  #: Joining this chat is not allowed because you are a limited user (no value on account)
    ClanDisabled = 8  #: Attempt to join a clan chat when the clan is locked or disabled
    CommunityBan = 9  #: Attempt to join a chat when the user has a community lock on their account
    MemberBlockedYou = 10  #: Join failed - some member in the chat has blocked you from joining
    YouBlockedMember = 11  #: Join failed - you have blocked some member already in the chat
    RatelimitExceeded = 15  #: Join failed - to many join attempts in a very short period of time


class ECurrencyCode(enum.IntEnum):
    Invalid = 0
    USD = 1
    GBP = 2
    EUR = 3
    CHF = 4
    RUB = 5
    PLN = 6
    BRL = 7
    JPY = 8
    NOK = 9
    IDR = 10
    MYR = 11
    PHP = 12
    SGD = 13
    THB = 14
    VND = 15
    KRW = 16
    TRY = 17
    UAH = 18
    MXN = 19
    CAD = 20
    AUD = 21
    NZD = 22
    CNY = 23
    INR = 24
    CLP = 25
    PEN = 26
    COP = 27
    ZAR = 28
    HKD = 29
    TWD = 30
    SAR = 31
    AED = 32
    SEK = 33
    ARS = 34
    ILS = 35
    BYN = 36
    KZT = 37
    KWD = 38
    QAR = 39
    CRC = 40
    UYU = 41
    Max = 42


class ETradeOfferState(enum.IntEnum):
    Invalid = 1
    Active = 2
    Accepted = 3
    Countered = 4
    Expired = 5
    Canceled = 6
    Declined = 7
    InvalidItems = 8
    ConfirmationNeed = 9
    CanceledBySecondaryFactor = 10
    StateInEscrow = 11


class EChatEntryType(enum.IntEnum):
    Invalid = 0
    ChatMsg = 1  #: Normal text message from another user
    Typing = 2  #: Another user is typing (not used in multi-user chat)
    InviteGame = 3  #: Invite from other user into that users current game
    LobbyGameStart = 5  #: lobby game is starting (dead - listen for LobbyGameCreated_t callback instead)
    LeftConversation = 6  #: user has left the conversation ( closed chat window )
    Entered = 7  #: User has entered the conversation (used in multi-user chat and group chat)
    WasKicked = 8  #: user was kicked (data: 64-bit steamid of actor performing the kick)
    WasBanned = 9  #: user was banned (data: 64-bit steamid of actor performing the ban)
    Disconnected = 10  #: user disconnected
    HistoricalChat = 11  #: a chat message from user's chat history or offline message
    LinkBlocked = 14  #: a link was removed by the chat filter.
