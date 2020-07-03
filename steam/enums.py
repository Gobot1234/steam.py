# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz
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

EnumMeta and Enum from https://github.com/Rapptz/discord.py/blob/master/discord/enums.py
Enums from https://github.com/ValvePython/steam/blob/master/steam/enums/common.py
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Tuple,
    TypeVar,
    Union,
)

__all__ = (
    'Enum',
    'IntEnum',
    'EResult',
    'EUniverse',
    'EType',
    'ETypeChar',
    'EInstanceFlag',
    'EFriendRelationship',
    'EPersonaState',
    'EPersonaStateFlag',
    'ECommunityVisibilityState',
    'ETradeOfferState',
    'EChatEntryType',
    'EUIMode',
)

T = TypeVar('T', bound='Enum')
EnumValues = Union['EnumValue', 'IntEnumValue']


def _is_descriptor(obj: Any) -> bool:
    return hasattr(obj, '__get__') or hasattr(obj, '__set__') or hasattr(obj, '__delete__')


@dataclass()
class EnumValue:
    name: str
    value: Any

    def __repr__(self: T):
        return f'<{self._actual_enum_cls_.__name__}.{self.name}: {repr(self.value)}>'

    def __str__(self: T):
        return f'{self._actual_enum_cls_.__name__}.{self.name}'

    def __hash__(self):
        return hash((self.name, self.value))

    def __eq__(self, other: Any):
        if isinstance(other, self.__class__):
            return self.name == other.name and self.value == other.value
        return NotImplemented

    def __ne__(self, other: Any):
        return not self == other


@dataclass(repr=False)
class IntEnumValue(EnumValue):
    value: int

    def __hash__(self):
        return super().__hash__()  # Guido mean

    def __eq__(self, other: Any):
        if isinstance(other, int):
            return self.value == other
        return super().__eq__(other)

    def __lt__(self, x: Any):
        return int(self) < int(x)

    def __le__(self, x: Any):
        return self < x or self == x

    def __gt__(self, x: Any):
        return int(self) > int(x)

    def __ge__(self, x: Any):
        return self > x or self == x

    def __int__(self):
        if type(self.value) is IntEnumValue:  # return the most base value
            ret = int(self.value)
            while type(ret) is IntEnumValue:
                ret = int(ret.value)
            return ret
        return self.value


class EnumMeta(type):
    def __new__(mcs: T, name: str, bases: Tuple[type, ...], attrs: Dict[str, Any]):
        value_mapping: Dict[Any, EnumValue] = {}
        member_mapping: Dict[str, EnumValue] = {}
        member_names: List[str] = []

        try:
            value_cls = IntEnumValue if IntEnum in bases else EnumValue
        except NameError:
            value_cls = EnumValue

        for key, value in list(attrs.items()):
            is_descriptor = _is_descriptor(value)
            if key[0] == '_' and not is_descriptor:
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

        attrs['_enum_value_map_'] = value_mapping
        attrs['_enum_member_map_'] = member_mapping
        attrs['_enum_member_names_'] = member_names
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
        return f'<enum {cls.__name__!r}>'

    def __iter__(cls: T) -> Iterable[EnumValues]:
        return (cls._enum_member_map_[name] for name in cls._enum_member_names_)

    def __reversed__(cls: T) -> Iterable[EnumValues]:
        return (cls._enum_member_map_[name] for name in reversed(cls._enum_member_names_))

    def __len__(cls: T):
        return len(cls._enum_member_names_)

    def __getitem__(cls: T, key: Any) -> EnumValues:
        return cls._enum_member_map_[key]

    def __setattr__(cls: T, name: str, value: Any) -> None:
        raise TypeError('Enums are immutable.')

    def __delattr__(cls: T, attr: Any) -> None:
        raise TypeError('Enums are immutable')

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
    def try_value(cls: T, value: Union['Enum', int, str]) -> Union[EnumValues, int, str]:
        try:
            return cls._enum_value_map_[value]
        except (KeyError, TypeError):
            return value


class IntEnum(int, Enum):
    """An enumeration where all the values are integers, emulates enum.IntEnum."""


class EResult(IntEnum):
    Invalid: IntEnumValue                         = 0
    OK: IntEnumValue                              = 1  #: Success
    Fail: IntEnumValue                            = 2  #: Generic failure
    NoConnection: IntEnumValue                    = 3  #: No/failed network connection
    InvalidPassword: IntEnumValue                 = 5  #: Password/ticket is invalid
    LoggedInElsewhere: IntEnumValue               = 6  #: Same user logged in elsewhere
    InvalidProtocolVersion: IntEnumValue          = 7
    InvalidParameter: IntEnumValue                = 8
    FileNotFound: IntEnumValue                    = 9
    Busy: IntEnumValue                            = 10  #: Called method busy - action not taken
    InvalidState: IntEnumValue                    = 11  #: Called object was in an invalid state
    InvalidName: IntEnumValue                     = 12
    InvalidEmail: IntEnumValue                    = 13
    DuplicateName: IntEnumValue                   = 14
    AccessDenied: IntEnumValue                    = 15
    Timeout: IntEnumValue                         = 16
    Banned: IntEnumValue                          = 17  #: VAC2 banned
    AccountNotFound: IntEnumValue                 = 18
    InvalidSteamID: IntEnumValue                  = 19
    ServiceUnavailable: IntEnumValue              = 20  #: The requested service is currently unavailable
    NotLoggedOn: IntEnumValue                     = 21
    Pending: IntEnumValue                         = 22  #: Request is pending (may be in process, or waiting on third party)
    EncryptionFailure: IntEnumValue               = 23
    InsufficientPrivilege: IntEnumValue           = 24
    LimitExceeded: IntEnumValue                   = 25  #: Too much of a good thing
    Revoked: IntEnumValue                         = 26  #: Access has been revoked (used for revoked guest passes)
    Expired: IntEnumValue                         = 27  #: License/Guest pass the user is trying to access is expired
    AlreadyRedeemed: IntEnumValue                 = 28  #: Guest pass has already been redeemed by account, cannot be acked again
    DuplicateRequest: IntEnumValue                = 29
    AlreadyOwned: IntEnumValue                    = 30  #: All the games in guest pass redemption request are already owned by the user
    IPNotFound: IntEnumValue                      = 31
    PersistFailed: IntEnumValue                   = 32  #: Failed to write change to the data store
    LockingFailed: IntEnumValue                   = 33  #: Failed to acquire access lock for this operation
    LogonSessionReplaced: IntEnumValue            = 34
    ConnectFailed: IntEnumValue                   = 35
    HandshakeFailed: IntEnumValue                 = 36
    IOFailure: IntEnumValue                       = 37
    RemoteDisconnect: IntEnumValue                = 38
    ShoppingCartNotFound: IntEnumValue            = 39
    Blocked: IntEnumValue                         = 40
    Ignored: IntEnumValue                         = 41
    NoMatch: IntEnumValue                         = 42
    AccountDisabled: IntEnumValue                 = 43
    ServiceReadOnly: IntEnumValue                 = 44
    AccountNotFeatured: IntEnumValue              = 45  #: Account doesn't have value, so this feature isn't available
    AdministratorOK: IntEnumValue                 = 46  #: Allowed to take this action, but only because requester is admin
    ContentVersion: IntEnumValue                  = 47  #: A Version mismatch in content transmitted within the Steam protocol
    TryAnotherCM: IntEnumValue                    = 48  #: The current CM can't service the user making a request, should try another
    PasswordRequiredToKickSession: IntEnumValue   = 49  #: You are already logged in elsewhere, this cached credential login has failed
    AlreadyLoggedInElsewhere: IntEnumValue        = 50  #: You are already logged in elsewhere, you must wait
    Suspended: IntEnumValue                       = 51  #: Long running operation (content download) suspended/paused
    Cancelled: IntEnumValue                       = 52  #: Operation canceled (typically by user content download)
    DataCorruption: IntEnumValue                  = 53  #: Operation canceled because data is ill formed or unrecoverable
    DiskFull: IntEnumValue                        = 54  #: Operation canceled - not enough disk space.
    RemoteCallFailed: IntEnumValue                = 55  #: An remote call or IPC call failed
    ExternalAccountUnlinked: IntEnumValue         = 57  #: External account (PSN, Facebook...) is not linked to a Steam account
    PSNTicketInvalid: IntEnumValue                = 58  #: PSN ticket was invalid
    ExternalAccountAlreadyLinked: IntEnumValue    = 59  #: External account (PSN, Facebook...) is already linked to some other account
    RemoteFileConflict: IntEnumValue              = 60  #: The sync cannot resume due to a conflict between the local and remote files
    IllegalPassword: IntEnumValue                 = 61  #: The requested new password is not legal
    SameAsPreviousValue: IntEnumValue             = 62  #: New value is the same as the old one (secret question and answer)
    AccountLogonDenied: IntEnumValue              = 63  #: Account login denied due to 2nd factor authentication failure
    CannotUseOldPassword: IntEnumValue            = 64  #: The requested new password is not legal
    InvalidLoginAuthCode: IntEnumValue            = 65  #: Account login denied due to auth code invalid
    HardwareNotCapableOfIPT: IntEnumValue         = 67
    IPTInitError: IntEnumValue                    = 68
    ParentalControlRestricted: IntEnumValue       = 69  #: Operation failed due to parental control restrictions for current user
    FacebookQueryError: IntEnumValue              = 70
    ExpiredLoginAuthCode: IntEnumValue            = 71  #: Account login denied due to auth code expired
    IPLoginRestrictionFailed: IntEnumValue        = 72
    VerifiedEmailRequired: IntEnumValue           = 74
    NoMatchingURL: IntEnumValue                   = 75
    BadResponse: IntEnumValue                     = 76  #: Parse failure, missing field, etc.
    RequirePasswordReEntry: IntEnumValue          = 77  #: The user cannot complete the action until they re-enter their password
    ValueOutOfRange: IntEnumValue                 = 78  #: The value entered is outside the acceptable range
    UnexpectedError: IntEnumValue                 = 79  #: Something happened that we didn't expect to ever happen
    Disabled: IntEnumValue                        = 80  #: The requested service has been configured to be unavailable
    InvalidCEGSubmission: IntEnumValue            = 81  #: The set of files submitted to the CEG server are not valid!
    RestrictedDevice: IntEnumValue                = 82  #: The device being used is not allowed to perform this action
    RegionLocked: IntEnumValue                    = 83  #: The action could not be complete because it is region restricted
    RateLimitExceeded: IntEnumValue               = 84  #: Temporary rate limit exceeded. different from k_EResultLimitExceeded
    LoginDeniedNeedTwoFactor: IntEnumValue        = 85  #: Need two-factor code to login
    ItemDeleted: IntEnumValue                     = 86  #: The thing we're trying to access has been deleted
    AccountLoginDeniedThrottle: IntEnumValue      = 87  #: Login attempt failed, try to throttle response to possible attacker
    TwoFactorCodeMismatch: IntEnumValue           = 88  #: Two factor code mismatch
    TwoFactorActivationCodeMismatch: IntEnumValue = 89  #: Activation code for two-factor didn't match
    NotModified: IntEnumValue                     = 91  #: Data not modified
    TimeNotSynced: IntEnumValue                   = 93  #: The time presented is out of range or tolerance
    SMSCodeFailed: IntEnumValue                   = 94  #: SMS code failure (no match, none pending, etc.)
    AccountActivityLimitExceeded: IntEnumValue    = 96  #: Too many changes to this account
    PhoneActivityLimitExceeded: IntEnumValue      = 97  #: Too many changes to this phone
    RefundToWallet: IntEnumValue                  = 98  #: Cannot refund to payment method, must use wallet
    EmailSendFailure: IntEnumValue                = 99  #: Cannot send an email
    NotSettled: IntEnumValue                      = 100  #: Can't perform operation till payment has settled
    NeedCaptcha: IntEnumValue                     = 101  #: Needs to provide a valid captcha
    GSLTDenied: IntEnumValue                      = 102  #: A game server login token owned by this token's owner has been banned
    GSOwnerDenied: IntEnumValue                   = 103  #: Game server owner is denied for other reason
    InvalidItemType: IntEnumValue                 = 104  #: The type of thing we were requested to act on is invalid
    IPBanned: IntEnumValue                        = 105  #: The ip address has been banned from taking this action
    GSLTExpired: IntEnumValue                     = 106  #: This token has expired from disuse; can be reset for use
    InsufficientFunds: IntEnumValue               = 107  #: User doesn't have enough wallet funds to complete the action
    TooManyPending: IntEnumValue                  = 108  #: There are too many of this thing pending already
    NoSiteLicensesFound: IntEnumValue             = 109  #: No site licenses found
    WGNetworkSendExceeded: IntEnumValue           = 110  #: The WG couldn't send a response because we exceeded max network send size
    AccountNotFriends: IntEnumValue               = 111
    LimitedUserAccount: IntEnumValue              = 112
    CantRemoveItem: IntEnumValue                  = 113


class EUniverse(IntEnum):
    Invalid: IntEnumValue  = 0
    Public: IntEnumValue   = 1
    Beta: IntEnumValue     = 2
    Internal: IntEnumValue = 3
    Dev: IntEnumValue      = 4
    Max: IntEnumValue      = 6

    def __str__(self):
        return self.name


class EType(IntEnum):
    Invalid: IntEnumValue        = 0
    Individual: IntEnumValue     = 1  #: Single user account
    Multiseat: IntEnumValue      = 2  #: Multiseat (e.g. cybercafe) account
    GameServer: IntEnumValue     = 3  #: Game server account
    AnonGameServer: IntEnumValue = 4  #: Anonymous game server account
    Pending: IntEnumValue        = 5
    ContentServer: IntEnumValue  = 6  #: Content server
    Clan: IntEnumValue           = 7
    Chat: IntEnumValue           = 8
    ConsoleUser: IntEnumValue    = 9  #: Fake SteamID for local PSN account on PS3 or Live account on 360, etc.
    AnonUser: IntEnumValue       = 10
    Max: IntEnumValue            = 11

    def __str__(self):
        return self.name


class ETypeChar(IntEnum):
    I: IntEnumValue = EType.Invalid
    U: IntEnumValue = EType.Individual
    M: IntEnumValue = EType.Multiseat
    G: IntEnumValue = EType.GameServer
    A: IntEnumValue = EType.AnonGameServer
    P: IntEnumValue = EType.Pending
    C: IntEnumValue = EType.ContentServer
    g: IntEnumValue = EType.Clan
    T: IntEnumValue = EType.Chat
    L: IntEnumValue = EType.Chat  #: Lobby/group chat, 'c' for clan chat
    c: IntEnumValue = EType.Chat  #: Clan chat
    a: IntEnumValue = EType.AnonUser

    def __str__(self):
        return self.name


class EInstanceFlag(IntEnum):
    MMSLobby = 0x20000
    Lobby    = 0x40000
    Clan     = 0x80000


class EFriendRelationship(IntEnum):
    NONE: IntEnumValue             = 0
    Blocked: IntEnumValue          = 1
    RequestRecipient: IntEnumValue = 2
    Friend: IntEnumValue           = 3
    RequestInitiator: IntEnumValue = 4
    Ignored: IntEnumValue          = 5
    IgnoredFriend: IntEnumValue    = 6
    SuggestedFriend: IntEnumValue  = 7
    Max: IntEnumValue              = 8


class EPersonaState(IntEnum):
    Offline: IntEnumValue        = 0
    Online: IntEnumValue         = 1
    Busy: IntEnumValue           = 2
    Away: IntEnumValue           = 3
    Snooze: IntEnumValue         = 4
    LookingToTrade: IntEnumValue = 5
    LookingToPlay: IntEnumValue  = 6
    Max: IntEnumValue            = 7

    def __str__(self):
        return self.name


class EPersonaStateFlag(IntEnum):
    NONE: IntEnumValue                 = 0
    HasRichPresence: IntEnumValue      = 1
    InJoinableGame: IntEnumValue       = 2
    Golden: IntEnumValue               = 4
    RemotePlayTogether: IntEnumValue   = 8
    ClientTypeWeb: IntEnumValue        = 256
    ClientTypeMobile: IntEnumValue     = 512
    ClientTypeTenfoot: IntEnumValue    = 1024
    ClientTypeVR: IntEnumValue         = 2048
    LaunchTypeGamepad: IntEnumValue    = 4096
    LaunchTypeCompatTool: IntEnumValue = 8192

    def __str__(self):
        return self.name


class ECommunityVisibilityState(IntEnum):
    NONE: IntEnumValue        = 0
    Private: IntEnumValue     = 1
    FriendsOnly: IntEnumValue = 2
    Public: IntEnumValue      = 3


class ETradeOfferState(IntEnum):
    Invalid: IntEnumValue                   = 1
    Active: IntEnumValue                    = 2
    Accepted: IntEnumValue                  = 3
    Countered: IntEnumValue                 = 4
    Expired: IntEnumValue                   = 5
    Canceled: IntEnumValue                  = 6
    Declined: IntEnumValue                  = 7
    InvalidItems: IntEnumValue              = 8
    ConfirmationNeed: IntEnumValue          = 9
    CanceledBySecondaryFactor: IntEnumValue = 10
    StateInEscrow: IntEnumValue             = 11


class EChatEntryType(IntEnum):
    Invalid: IntEnumValue          = 0
    ChatMsg: IntEnumValue          = 1  #: Normal text message from another user
    Typing: IntEnumValue           = 2  #: Another user is typing (not used in multi-user chat)
    InviteGame: IntEnumValue       = 3  #: Invite from other user into that users current game
    LeftConversation: IntEnumValue = 6  #: user has left the conversation ( closed chat window )
    Entered: IntEnumValue          = 7  #: User has entered the conversation (used in multi-user chat and group chat)
    WasKicked: IntEnumValue        = 8  #: user was kicked (data: 64-bit steamid of actor performing the kick)
    WasBanned: IntEnumValue        = 9  #: user was banned (data: 64-bit steamid of actor performing the ban)
    Disconnected: IntEnumValue     = 10  #: user disconnected
    HistoricalChat: IntEnumValue   = 11  #: a chat message from user's chat history or offline message
    LinkBlocked: IntEnumValue      = 14  #: a link was removed by the chat filter.


class EUIMode(IntEnum):
    Desktop: IntEnumValue    = 0
    BigPicture: IntEnumValue = 1
    Mobile: IntEnumValue     = 2
    Web: IntEnumValue        = 3


class EUserBadge(IntEnum):
    Invalid: IntEnumValue                           = 0
    YearsOfService: IntEnumValue                    = 1
    Community: IntEnumValue                         = 2
    Portal2PotatoARG: IntEnumValue                  = 3
    TreasureHunt: IntEnumValue                      = 4
    SummerSale2011: IntEnumValue                    = 5
    WinterSale2011: IntEnumValue                    = 6
    SummerSale2012: IntEnumValue                    = 7
    WinterSale2012: IntEnumValue                    = 8
    CommunityTranslator: IntEnumValue               = 9
    CommunityModerator: IntEnumValue                = 10
    ValveEmployee: IntEnumValue                     = 11
    GameDeveloper: IntEnumValue                     = 12
    GameCollector: IntEnumValue                     = 13
    TradingCardBetaParticipant: IntEnumValue        = 14
    SteamBoxBeta: IntEnumValue                      = 15
    Summer2014RedTeam: IntEnumValue                 = 16
    Summer2014BlueTeam: IntEnumValue                = 17
    Summer2014PinkTeam: IntEnumValue                = 18
    Summer2014GreenTeam: IntEnumValue               = 19
    Summer2014PurpleTeam: IntEnumValue              = 20
    Auction2014: IntEnumValue                       = 21
    GoldenProfile2014: IntEnumValue                 = 22
    TowerAttackMiniGame: IntEnumValue               = 23
    Winter2015ARG_RedHerring: IntEnumValue          = 24
    SteamAwards2016Nominations: IntEnumValue        = 25
    StickerCompletionist2017: IntEnumValue          = 26
    SteamAwards2017Nominations: IntEnumValue        = 27
    SpringCleaning2018: IntEnumValue                = 28
    Salien: IntEnumValue                            = 29
    RetiredModerator: IntEnumValue                  = 30
    SteamAwards2018Nominations: IntEnumValue        = 31
    ValveModerator: IntEnumValue                    = 32
    WinterSale2018: IntEnumValue                    = 33
    LunarNewYearSale2019: IntEnumValue              = 34
    LunarNewYearSale2019GoldenProfile: IntEnumValue = 35
    SpringCleaning2019: IntEnumValue                = 36
    Summer2019: IntEnumValue                        = 37
    Summer2019TeamHare: IntEnumValue                = 38
    Summer2019TeamTortoise: IntEnumValue            = 39
    Summer2019TeamCorgi: IntEnumValue               = 40
    Summer2019TeamCockatiel: IntEnumValue           = 41
    Summer2019TeamPig: IntEnumValue                 = 42
    SteamAwards2019Nominations: IntEnumValue        = 43
    WinterSaleEvent2019: IntEnumValue               = 44
