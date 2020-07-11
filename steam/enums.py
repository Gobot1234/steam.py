# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz
Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

EnumMeta from https://github.com/Rapptz/discord.py/blob/master/discord/enums.py
Enums from https://github.com/ValvePython/steam/blob/master/steam/enums/common.py
"""

from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Mapping, NoReturn, Tuple, TypeVar, Union

__all__ = (
    "Enum",
    "IntEnum",
    "EResult",
    "EUniverse",
    "EType",
    "ETypeChar",
    "EInstanceFlag",
    "EFriendRelationship",
    "EPersonaState",
    "EPersonaStateFlag",
    "ECommunityVisibilityState",
    "ETradeOfferState",
    "EChatEntryType",
    "EUIMode",
)

T = TypeVar("T", bound="EnumMeta")
EnumValues = Union["EnumMember", "IntEnumMember"]


def _is_descriptor(obj: Any) -> bool:
    return hasattr(obj, "__get__") or hasattr(obj, "__set__") or hasattr(obj, "__delete__")


class EnumMember:
    name: str
    value: Any

    def __new__(cls, **kwargs) -> "EnumMember":
        try:
            cls.name = kwargs["name"]
            cls.value = kwargs["value"]
        except KeyError:
            pass
        finally:
            return super().__new__(cls)

    def __str__(self):
        return f"{self._actual_enum_cls_.__name__}.{self.name}"

    def __repr__(self):
        return f"<{self._actual_enum_cls_.__name__}.{self.name}: {self.value!r}>"


class IntEnumMember(int, EnumMember):
    value: int

    def __new__(cls, **kwargs) -> "IntEnumMember":
        try:
            value = kwargs["value"]
            self = super().__new__(cls, value)
            self.name = kwargs["name"]
            self.value = value
            return self
        except KeyError:
            return super().__new__(cls)

    def __str__(self):
        return EnumMember.__str__(self)

    def __repr__(self):
        return EnumMember.__repr__(self)

    def __bool__(self):
        return True


class EnumMeta(type):
    def __new__(mcs: T, name: str, bases: Tuple[type, ...], attrs: Dict[str, Any]) -> "Enum":
        value_mapping: Dict[Any, EnumMember] = {}
        member_mapping: Dict[str, EnumMember] = {}
        member_names: List[str] = []

        try:
            value_cls = IntEnumMember if IntEnum in bases else EnumMember
        except NameError:
            value_cls = EnumMember

        for key, value in tuple(attrs.items()):
            is_descriptor = _is_descriptor(value)
            if key[0] == "_" and not is_descriptor:
                continue

            # special case for classmethods to pass through
            if isinstance(value, classmethod):
                continue

            if is_descriptor:
                setattr(value_cls, key, value)
                del attrs[key]
                continue

            try:
                new_value = value_mapping[value]
            except KeyError:
                new_value = value_cls(name=key, value=value)
                value_mapping[value] = new_value
                member_names.append(key)

            member_mapping[key] = new_value
            attrs[key] = new_value

        attrs["_enum_value_map_"] = value_mapping
        attrs["_enum_member_map_"] = member_mapping
        attrs["_enum_member_names_"] = member_names
        enum_class = super().__new__(mcs, name, bases, attrs)
        for value in value_mapping.values():  # edit each value to ensure it's correct
            value._actual_enum_cls_ = enum_class
        return enum_class

    def __call__(cls: T, value: Any) -> EnumValues:
        try:
            return cls._enum_value_map_[value]
        except (KeyError, TypeError):
            raise ValueError(f"{repr(value)} is not a valid {cls.__name__}")

    def __repr__(cls: T):
        return f"<enum {cls.__name__!r}>"

    def __iter__(cls: T) -> Iterable[EnumValues]:
        return (cls._enum_member_map_[name] for name in cls._enum_member_names_)

    def __reversed__(cls: T) -> Iterable[EnumValues]:
        return (cls._enum_member_map_[name] for name in reversed(cls._enum_member_names_))

    def __len__(cls: T):
        return len(cls._enum_member_names_)

    def __getitem__(cls: T, key: Any) -> EnumValues:
        return cls._enum_member_map_[key]

    def __setattr__(cls: T, name: str, value: Any) -> NoReturn:
        raise TypeError("Enums are immutable.")

    def __delattr__(cls: T, attr: Any) -> NoReturn:
        raise TypeError("Enums are immutable")

    def __instancecheck__(self, instance: Any):
        # isinstance(x, Y)
        # -> __instancecheck__(Y, x)
        try:
            cls = instance._actual_enum_cls_
            return cls is self or issubclass(cls, self)
        except AttributeError:
            return False

    @property
    def __members__(cls: T) -> Mapping[str, EnumValues]:
        return MappingProxyType(cls._enum_member_map_)


class Enum(metaclass=EnumMeta):
    """A general enumeration, emulates enum.Enum."""

    @classmethod
    def try_value(cls: T, value: Union["Enum", int, str]) -> Union[EnumValues, int, str]:
        try:
            return cls._enum_value_map_[value]
        except (KeyError, TypeError):
            return value


class IntEnum(Enum):
    """An enumeration where all the values are integers, emulates enum.IntEnum."""


# fmt: off

class EResult(IntEnum):
    Invalid: IntEnumMember                         = 0
    OK: IntEnumMember                              = 1  #: Success
    Fail: IntEnumMember                            = 2  #: Generic failure
    NoConnection: IntEnumMember                    = 3  #: No/failed network connection
    InvalidPassword: IntEnumMember                 = 5  #: Password/ticket is invalid
    LoggedInElsewhere: IntEnumMember               = 6  #: Same user logged in elsewhere
    InvalidProtocolVersion: IntEnumMember          = 7
    InvalidParameter: IntEnumMember                = 8
    FileNotFound: IntEnumMember                    = 9
    Busy: IntEnumMember                            = 10  #: Called method busy - action not taken
    InvalidState: IntEnumMember                    = 11  #: Called object was in an invalid state
    InvalidName: IntEnumMember                     = 12
    InvalidEmail: IntEnumMember                    = 13
    DuplicateName: IntEnumMember                   = 14
    AccessDenied: IntEnumMember                    = 15
    Timeout: IntEnumMember                         = 16
    Banned: IntEnumMember                          = 17  #: VAC2 banned
    AccountNotFound: IntEnumMember                 = 18
    InvalidSteamID: IntEnumMember                  = 19
    ServiceUnavailable: IntEnumMember              = 20  #: The requested service is currently unavailable
    NotLoggedOn: IntEnumMember                     = 21
    Pending: IntEnumMember                         = 22  #: Request is pending (may be in process, or waiting on third party)
    EncryptionFailure: IntEnumMember               = 23
    InsufficientPrivilege: IntEnumMember           = 24
    LimitExceeded: IntEnumMember                   = 25  #: Too much of a good thing
    Revoked: IntEnumMember                         = 26  #: Access has been revoked (used for revoked guest passes)
    Expired: IntEnumMember                         = 27  #: License/Guest pass the user is trying to access is expired
    AlreadyRedeemed: IntEnumMember                 = 28  #: Guest pass has already been redeemed by account, cannot be acked again
    DuplicateRequest: IntEnumMember                = 29
    AlreadyOwned: IntEnumMember                    = 30  #: All the games in guest pass redemption request are already owned by the user
    IPNotFound: IntEnumMember                      = 31
    PersistFailed: IntEnumMember                   = 32  #: Failed to write change to the data store
    LockingFailed: IntEnumMember                   = 33  #: Failed to acquire access lock for this operation
    LogonSessionReplaced: IntEnumMember            = 34
    ConnectFailed: IntEnumMember                   = 35
    HandshakeFailed: IntEnumMember                 = 36
    IOFailure: IntEnumMember                       = 37
    RemoteDisconnect: IntEnumMember                = 38
    ShoppingCartNotFound: IntEnumMember            = 39
    Blocked: IntEnumMember                         = 40
    Ignored: IntEnumMember                         = 41
    NoMatch: IntEnumMember                         = 42
    AccountDisabled: IntEnumMember                 = 43
    ServiceReadOnly: IntEnumMember                 = 44
    AccountNotFeatured: IntEnumMember              = 45  #: Account doesn't have value, so this feature isn't available
    AdministratorOK: IntEnumMember                 = 46  #: Allowed to take this action, but only because requester is admin
    ContentVersion: IntEnumMember                  = 47  #: A Version mismatch in content transmitted within the Steam protocol
    TryAnotherCM: IntEnumMember                    = 48  #: The current CM can't service the user making a request, should try another
    PasswordRequiredToKickSession: IntEnumMember   = 49  #: You are already logged in elsewhere, this cached credential login has failed
    AlreadyLoggedInElsewhere: IntEnumMember        = 50  #: You are already logged in elsewhere, you must wait
    Suspended: IntEnumMember                       = 51  #: Long running operation (content download) suspended/paused
    Cancelled: IntEnumMember                       = 52  #: Operation canceled (typically by user content download)
    DataCorruption: IntEnumMember                  = 53  #: Operation canceled because data is ill formed or unrecoverable
    DiskFull: IntEnumMember                        = 54  #: Operation canceled - not enough disk space.
    RemoteCallFailed: IntEnumMember                = 55  #: An remote call or IPC call failed
    ExternalAccountUnlinked: IntEnumMember         = 57  #: External account (PSN, Facebook...) is not linked to a Steam account
    PSNTicketInvalid: IntEnumMember                = 58  #: PSN ticket was invalid
    ExternalAccountAlreadyLinked: IntEnumMember    = 59  #: External account (PSN, Facebook...) is already linked to some other account
    RemoteFileConflict: IntEnumMember              = 60  #: The sync cannot resume due to a conflict between the local and remote files
    IllegalPassword: IntEnumMember                 = 61  #: The requested new password is not legal
    SameAsPreviousValue: IntEnumMember             = 62  #: New value is the same as the old one (secret question and answer)
    AccountLogonDenied: IntEnumMember              = 63  #: Account login denied due to 2nd factor authentication failure
    CannotUseOldPassword: IntEnumMember            = 64  #: The requested new password is not legal
    InvalidLoginAuthCode: IntEnumMember            = 65  #: Account login denied due to auth code invalid
    HardwareNotCapableOfIPT: IntEnumMember         = 67
    IPTInitError: IntEnumMember                    = 68
    ParentalControlRestricted: IntEnumMember       = 69  #: Operation failed due to parental control restrictions for current user
    FacebookQueryError: IntEnumMember              = 70
    ExpiredLoginAuthCode: IntEnumMember            = 71  #: Account login denied due to auth code expired
    IPLoginRestrictionFailed: IntEnumMember        = 72
    VerifiedEmailRequired: IntEnumMember           = 74
    NoMatchingURL: IntEnumMember                   = 75
    BadResponse: IntEnumMember                     = 76  #: Parse failure, missing field, etc.
    RequirePasswordReEntry: IntEnumMember          = 77  #: The user cannot complete the action until they re-enter their password
    ValueOutOfRange: IntEnumMember                 = 78  #: The value entered is outside the acceptable range
    UnexpectedError: IntEnumMember                 = 79  #: Something happened that we didn't expect to ever happen
    Disabled: IntEnumMember                        = 80  #: The requested service has been configured to be unavailable
    InvalidCEGSubmission: IntEnumMember            = 81  #: The set of files submitted to the CEG server are not valid!
    RestrictedDevice: IntEnumMember                = 82  #: The device being used is not allowed to perform this action
    RegionLocked: IntEnumMember                    = 83  #: The action could not be complete because it is region restricted
    RateLimitExceeded: IntEnumMember               = 84  #: Temporary rate limit exceeded. different from k_EResultLimitExceeded
    LoginDeniedNeedTwoFactor: IntEnumMember        = 85  #: Need two-factor code to login
    ItemDeleted: IntEnumMember                     = 86  #: The thing we're trying to access has been deleted
    AccountLoginDeniedThrottle: IntEnumMember      = 87  #: Login attempt failed, try to throttle response to possible attacker
    TwoFactorCodeMismatch: IntEnumMember           = 88  #: Two factor code mismatch
    TwoFactorActivationCodeMismatch: IntEnumMember = 89  #: Activation code for two-factor didn't match
    NotModified: IntEnumMember                     = 91  #: Data not modified
    TimeNotSynced: IntEnumMember                   = 93  #: The time presented is out of range or tolerance
    SMSCodeFailed: IntEnumMember                   = 94  #: SMS code failure (no match, none pending, etc.)
    AccountActivityLimitExceeded: IntEnumMember    = 96  #: Too many changes to this account
    PhoneActivityLimitExceeded: IntEnumMember      = 97  #: Too many changes to this phone
    RefundToWallet: IntEnumMember                  = 98  #: Cannot refund to payment method, must use wallet
    EmailSendFailure: IntEnumMember                = 99  #: Cannot send an email
    NotSettled: IntEnumMember                      = 100  #: Can't perform operation till payment has settled
    NeedCaptcha: IntEnumMember                     = 101  #: Needs to provide a valid captcha
    GSLTDenied: IntEnumMember                      = 102  #: A game server login token owned by this token's owner has been banned
    GSOwnerDenied: IntEnumMember                   = 103  #: Game server owner is denied for other reason
    InvalidItemType: IntEnumMember                 = 104  #: The type of thing we were requested to act on is invalid
    IPBanned: IntEnumMember                        = 105  #: The ip address has been banned from taking this action
    GSLTExpired: IntEnumMember                     = 106  #: This token has expired from disuse; can be reset for use
    InsufficientFunds: IntEnumMember               = 107  #: User doesn't have enough wallet funds to complete the action
    TooManyPending: IntEnumMember                  = 108  #: There are too many of this thing pending already
    NoSiteLicensesFound: IntEnumMember             = 109  #: No site licenses found
    WGNetworkSendExceeded: IntEnumMember           = 110  #: The WG couldn't send a response because we exceeded max network send size
    AccountNotFriends: IntEnumMember               = 111
    LimitedUserAccount: IntEnumMember              = 112
    CantRemoveItem: IntEnumMember                  = 113


class EUniverse(IntEnum):
    Invalid: IntEnumMember  = 0
    Public: IntEnumMember   = 1
    Beta: IntEnumMember     = 2
    Internal: IntEnumMember = 3
    Dev: IntEnumMember      = 4
    Max: IntEnumMember      = 6

    def __str__(self):
        return self.name


class EType(IntEnum):
    Invalid: IntEnumMember        = 0
    Individual: IntEnumMember     = 1  #: Single user account
    Multiseat: IntEnumMember      = 2  #: Multiseat (e.g. cybercafe) account
    GameServer: IntEnumMember     = 3  #: Game server account
    AnonGameServer: IntEnumMember = 4  #: Anonymous game server account
    Pending: IntEnumMember        = 5
    ContentServer: IntEnumMember  = 6  #: Content server
    Clan: IntEnumMember           = 7
    Chat: IntEnumMember           = 8
    ConsoleUser: IntEnumMember    = 9  #: Fake SteamID for local PSN account on PS3 or Live account on 360, etc.
    AnonUser: IntEnumMember       = 10
    Max: IntEnumMember            = 11

    def __str__(self):
        return self.name


class ETypeChar(IntEnum):
    I: IntEnumMember = EType.Invalid
    U: IntEnumMember = EType.Individual
    M: IntEnumMember = EType.Multiseat
    G: IntEnumMember = EType.GameServer
    A: IntEnumMember = EType.AnonGameServer
    P: IntEnumMember = EType.Pending
    C: IntEnumMember = EType.ContentServer
    g: IntEnumMember = EType.Clan
    T: IntEnumMember = EType.Chat
    L: IntEnumMember = EType.Chat  #: Lobby/group chat, 'c' for clan chat
    c: IntEnumMember = EType.Chat  #: Clan chat
    a: IntEnumMember = EType.AnonUser

    def __str__(self):
        return self.name


class EInstanceFlag(IntEnum):
    MMSLobby = 0x20000
    Lobby    = 0x40000
    Clan     = 0x80000


class EFriendRelationship(IntEnum):
    NONE: IntEnumMember             = 0
    Blocked: IntEnumMember          = 1
    RequestRecipient: IntEnumMember = 2
    Friend: IntEnumMember           = 3
    RequestInitiator: IntEnumMember = 4
    Ignored: IntEnumMember          = 5
    IgnoredFriend: IntEnumMember    = 6
    SuggestedFriend: IntEnumMember  = 7
    Max: IntEnumMember              = 8


class EPersonaState(IntEnum):
    Offline: IntEnumMember        = 0
    Online: IntEnumMember         = 1
    Busy: IntEnumMember           = 2
    Away: IntEnumMember           = 3
    Snooze: IntEnumMember         = 4
    LookingToTrade: IntEnumMember = 5
    LookingToPlay: IntEnumMember  = 6
    Max: IntEnumMember            = 7

    def __str__(self):
        return self.name


class EPersonaStateFlag(IntEnum):
    NONE: IntEnumMember                 = 0
    HasRichPresence: IntEnumMember      = 1
    InJoinableGame: IntEnumMember       = 2
    Golden: IntEnumMember               = 4
    RemotePlayTogether: IntEnumMember   = 8
    ClientTypeWeb: IntEnumMember        = 256
    ClientTypeMobile: IntEnumMember     = 512
    ClientTypeTenfoot: IntEnumMember    = 1024
    ClientTypeVR: IntEnumMember         = 2048
    LaunchTypeGamepad: IntEnumMember    = 4096
    LaunchTypeCompatTool: IntEnumMember = 8192

    def __str__(self):
        return self.name


class ECommunityVisibilityState(IntEnum):
    NONE: IntEnumMember        = 0
    Private: IntEnumMember     = 1
    FriendsOnly: IntEnumMember = 2
    Public: IntEnumMember      = 3


class ETradeOfferState(IntEnum):
    Invalid: IntEnumMember                   = 1
    Active: IntEnumMember                    = 2
    Accepted: IntEnumMember                  = 3
    Countered: IntEnumMember                 = 4
    Expired: IntEnumMember                   = 5
    Canceled: IntEnumMember                  = 6
    Declined: IntEnumMember                  = 7
    InvalidItems: IntEnumMember              = 8
    ConfirmationNeed: IntEnumMember          = 9
    CanceledBySecondaryFactor: IntEnumMember = 10
    StateInEscrow: IntEnumMember             = 11


class EChatEntryType(IntEnum):
    Invalid: IntEnumMember          = 0
    ChatMsg: IntEnumMember          = 1  #: Normal text message from another user
    Typing: IntEnumMember           = 2  #: Another user is typing (not used in multi-user chat)
    InviteGame: IntEnumMember       = 3  #: Invite from other user into that users current game
    LeftConversation: IntEnumMember = 6  #: user has left the conversation ( closed chat window )
    Entered: IntEnumMember          = 7  #: User has entered the conversation (used in multi-user chat and group chat)
    WasKicked: IntEnumMember        = 8  #: user was kicked (data: 64-bit steamid of actor performing the kick)
    WasBanned: IntEnumMember        = 9  #: user was banned (data: 64-bit steamid of actor performing the ban)
    Disconnected: IntEnumMember     = 10  #: user disconnected
    HistoricalChat: IntEnumMember   = 11  #: a chat message from user's chat history or offline message
    LinkBlocked: IntEnumMember      = 14  #: a link was removed by the chat filter.


class EUIMode(IntEnum):
    Desktop: IntEnumMember    = 0
    BigPicture: IntEnumMember = 1
    Mobile: IntEnumMember     = 2
    Web: IntEnumMember        = 3


class EUserBadge(IntEnum):
    Invalid: IntEnumMember                           = 0
    YearsOfService: IntEnumMember                    = 1
    Community: IntEnumMember                         = 2
    Portal2PotatoARG: IntEnumMember                  = 3
    TreasureHunt: IntEnumMember                      = 4
    SummerSale2011: IntEnumMember                    = 5
    WinterSale2011: IntEnumMember                    = 6
    SummerSale2012: IntEnumMember                    = 7
    WinterSale2012: IntEnumMember                    = 8
    CommunityTranslator: IntEnumMember               = 9
    CommunityModerator: IntEnumMember                = 10
    ValveEmployee: IntEnumMember                     = 11
    GameDeveloper: IntEnumMember                     = 12
    GameCollector: IntEnumMember                     = 13
    TradingCardBetaParticipant: IntEnumMember        = 14
    SteamBoxBeta: IntEnumMember                      = 15
    Summer2014RedTeam: IntEnumMember                 = 16
    Summer2014BlueTeam: IntEnumMember                = 17
    Summer2014PinkTeam: IntEnumMember                = 18
    Summer2014GreenTeam: IntEnumMember               = 19
    Summer2014PurpleTeam: IntEnumMember              = 20
    Auction2014: IntEnumMember                       = 21
    GoldenProfile2014: IntEnumMember                 = 22
    TowerAttackMiniGame: IntEnumMember               = 23
    Winter2015ARG_RedHerring: IntEnumMember          = 24
    SteamAwards2016Nominations: IntEnumMember        = 25
    StickerCompletionist2017: IntEnumMember          = 26
    SteamAwards2017Nominations: IntEnumMember        = 27
    SpringCleaning2018: IntEnumMember                = 28
    Salien: IntEnumMember                            = 29
    RetiredModerator: IntEnumMember                  = 30
    SteamAwards2018Nominations: IntEnumMember        = 31
    ValveModerator: IntEnumMember                    = 32
    WinterSale2018: IntEnumMember                    = 33
    LunarNewYearSale2019: IntEnumMember              = 34
    LunarNewYearSale2019GoldenProfile: IntEnumMember = 35
    SpringCleaning2019: IntEnumMember                = 36
    Summer2019: IntEnumMember                        = 37
    Summer2019TeamHare: IntEnumMember                = 38
    Summer2019TeamTortoise: IntEnumMember            = 39
    Summer2019TeamCorgi: IntEnumMember               = 40
    Summer2019TeamCockatiel: IntEnumMember           = 41
    Summer2019TeamPig: IntEnumMember                 = 42
    SteamAwards2019Nominations: IntEnumMember        = 43
    WinterSaleEvent2019: IntEnumMember               = 44
