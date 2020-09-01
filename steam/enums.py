# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz
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
"""

from types import MappingProxyType
from typing import Any, Dict, List, Tuple

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
    "EUserBadge",
)


def _is_descriptor(obj: object) -> bool:
    """Returns True if obj is a descriptor, False otherwise."""
    return hasattr(obj, "__get__") or hasattr(obj, "__set__") or hasattr(obj, "__delete__")


def _is_dunder(name: str) -> bool:
    """Returns True if a __dunder__ name, False otherwise."""
    return len(name) > 4 and name[:2] == name[-2:] == "__" and name[2] != "_" and name[-3] != "_"


class EnumMember:
    _enum_cls_: "Enum"
    name: str
    value: Any

    def __new__(cls, *, name, value) -> "EnumMember":
        self = super().__new__(cls)
        self.name = name
        self.value = value
        return self

    def __repr__(self):
        return f"<{self._enum_cls_.__name__}.{self.name}: {self.value!r}>"

    def __str__(self):
        return f"{self._enum_cls_.__name__}.{self.name}"

    def __hash__(self):
        return hash((self.name, self.value))


class IntEnumMember(EnumMember, int):
    _enum_cls_: "IntEnum"
    value: int

    def __new__(cls, *, name, value) -> "IntEnumMember":
        self = int.__new__(cls, value)
        self.name = name
        self.value = value
        return self

    def __bool__(self):
        return True


class EnumMeta(type):
    def __new__(mcs, name: str, bases: Tuple[type, ...], attrs: Dict[str, Any]) -> "Enum":
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

        attrs["_value_map_"] = value_mapping
        attrs["_member_map_"] = member_mapping
        attrs["_member_names_"] = member_names
        enum_class: "Enum" = super().__new__(mcs, name, bases, attrs)
        for member in value_mapping.values():  # edit each value to ensure it's correct
            member._enum_cls_ = enum_class
        return enum_class

    def __call__(cls, value):
        if isinstance(value, cls):
            return value
        try:
            return cls._value_map_[value]
        except (KeyError, TypeError):
            raise ValueError(f"{value!r} is not a valid {cls.__name__}")

    def __repr__(cls):
        return f"<enum {cls.__name__!r}>"

    def __iter__(cls):
        return (cls._member_map_[name] for name in cls._member_names_)

    def __reversed__(cls):
        return (cls._member_map_[name] for name in reversed(cls._member_names_))

    def __len__(cls):
        return len(cls._member_names_)

    def __getitem__(cls, key):
        return cls._member_map_[key]

    def __setattr__(cls, name, value):
        if name in cls._member_names_:
            raise AttributeError(f"{cls.__name__}: cannot reassign Enum members.")
        if _is_dunder(name):
            for value in cls._member_map_:
                setattr(value, name, value)
        super().__setattr__(name, value)

    def __delattr__(cls, name):
        if name in cls._member_names_:
            raise AttributeError(f"{cls.__name__}: cannot delete Enum members.")
        if _is_dunder(name):
            for value in cls._member_map_:
                delattr(value, name)
        super().__delattr__(name)

    def __instancecheck__(self, instance):
        # isinstance(x, Y) -> __instancecheck__(Y, x)
        try:
            cls = instance._enum_cls_
            return cls is self or issubclass(cls, self)
        except AttributeError:
            return False

    def __dir__(cls):
        return ["__class__", "__doc__", "__members__", "__module__"] + cls._member_names_

    def __contains__(cls, member):
        if not isinstance(member, EnumMember):
            raise TypeError(
                "unsupported operand type(s) for 'in':"
                f" '{member.__class__.__qualname__}' and '{cls.__class__.__qualname__}'"
            )
        return member.name in cls._member_map_

    def __bool__(self):
        return True

    @property
    def __members__(cls):
        return MappingProxyType(cls._member_map_)


class Enum(metaclass=EnumMeta):
    """A general enumeration, emulates enum.Enum."""

    @classmethod
    def try_value(cls, value):
        try:
            return cls._value_map_[value]
        except (KeyError, TypeError):
            return value


class IntEnum(int, Enum):
    """An enumeration where all the values are integers, emulates enum.IntEnum."""


# fmt: off
class EResult(IntEnum):
    Invalid                         = 0  #: Invalid EResult.
    OK                              = 1  #: Success.
    Fail                            = 2  #: Generic failure.
    NoConnection                    = 3  #: Your Steam client doesn't have a connection to the back-end.
    InvalidPassword                 = 5  #: Password/ticket is invalid.
    LoggedInElsewhere               = 6  #: Same user logged in elsewhere.
    InvalidProtocolVersion          = 7  #: Protocol version is incorrect.
    InvalidParameter                = 8  #: A parameter is incorrect.
    FileNotFound                    = 9  #: File was not found.
    Busy                            = 10  #: Called method busy - action not taken.
    InvalidState                    = 11  #: Called object was in an invalid state.
    InvalidName                     = 12  #: The name was invalid.
    InvalidEmail                    = 13  #: The email was invalid.
    DuplicateName                   = 14  #: The name is not unique.
    AccessDenied                    = 15  #: Access is denied.
    Timeout                         = 16  #: Operation timed out.
    Banned                          = 17  #: VAC2 banned.
    AccountNotFound                 = 18  #: Account not found.
    InvalidSteamID                  = 19  #: The Steam ID was invalid.
    ServiceUnavailable              = 20  #: The requested service is currently unavailable.
    NotLoggedOn                     = 21  #: The user is not logged on.
    Pending                         = 22  #: Request is pending (may be in process, or waiting on third party).
    EncryptionFailure               = 23  #: Encryption or decryption failed.
    InsufficientPrivilege           = 24  #: Insufficient privilege.
    LimitExceeded                   = 25  #: Too much of a good thing.
    Revoked                         = 26  #: Access has been revoked (used for revoked guest passes).
    Expired                         = 27  #: License/Guest pass the user is trying to access is expired.
    AlreadyRedeemed                 = 28  #: Guest pass has already been redeemed by account, cannot be acknowledged again.
    DuplicateRequest                = 29  #: The request is a duplicate, ignored this time.
    AlreadyOwned                    = 30  #: All the games in guest pass redemption request are already owned by the user.
    IPNotFound                      = 31  #: IP address not found.
    PersistFailed                   = 32  #: Failed to write change to the data store.
    LockingFailed                   = 33  #: Failed to acquire access lock for this operation.
    LogonSessionReplaced            = 34  #: The logon session has been replaced.
    ConnectFailed                   = 35  #: Failed to connect.
    HandshakeFailed                 = 36  #: The authentication handshake has failed.
    IOFailure                       = 37  #: Generic IO failure.
    RemoteDisconnect                = 38  #: The remote server has disconnected.
    ShoppingCartNotFound            = 39  #: Failed to find the shopping cart requested.
    Blocked                         = 40  #: A user blocked the action.
    Ignored                         = 41  #: The target is ignoring sender.
    NoMatch                         = 42  #: Nothing matching the request found.
    AccountDisabled                 = 43  #: The account is disabled.
    ServiceReadOnly                 = 44  #: This service is not accepting content changes right now.
    AccountNotFeatured              = 45  #: Account doesn't have value, so this feature isn't available.
    AdministratorOK                 = 46  #: Allowed to take this action, but only because requester is admin.
    ContentVersion                  = 47  #: A Version mismatch in content transmitted within the Steam protocol.
    TryAnotherCM                    = 48  #: The current CM can't service the user making a request, should try another.
    PasswordRequiredToKickSession   = 49  #: You are already logged in elsewhere, this cached credential login has failed.
    AlreadyLoggedInElsewhere        = 50  #: You are already logged in elsewhere, you must wait.
    Suspended                       = 51  #: Long running operation (content download) suspended/paused.
    Cancelled                       = 52  #: Operation canceled (typically by user content download).
    DataCorruption                  = 53  #: Operation canceled because data is malformed or unrecoverable.
    DiskFull                        = 54  #: Operation canceled - not enough disk space.
    RemoteCallFailed                = 55  #: An remote call or IPC call failed.
    ExternalAccountUnlinked         = 57  #: External account is not linked to a Steam account.
    PSNTicketInvalid                = 58  #: PSN ticket was invalid.
    ExternalAccountAlreadyLinked    = 59  #: External account is already linked to some other account.
    RemoteFileConflict              = 60  #: The sync cannot resume due to a conflict between the local and remote files.
    IllegalPassword                 = 61  #: The requested new password is not legal.
    SameAsPreviousValue             = 62  #: New value is the same as the old one (secret question and answer).
    AccountLogonDenied              = 63  #: Account login denied due to 2nd factor authentication failure.
    CannotUseOldPassword            = 64  #: The requested new password is not legal.
    InvalidLoginAuthCode            = 65  #: Account login denied due to auth code invalid.
    AccountLogonDeniedNoMail        = 66  #: Account login denied due to 2nd factor authentication failure.
    HardwareNotCapableOfIPT         = 67  #: The users hardware does not support Intel's identity protection technology.
    IPTInitError                    = 68  #: Intel's Identity Protection Technology has failed to initialize.
    ParentalControlRestricted       = 69  #: Operation failed due to parental control restrictions for current user.
    FacebookQueryError              = 70  #: Facebook query returned an error.
    ExpiredLoginAuthCode            = 71  #: Account login denied due to auth code expired.
    IPLoginRestrictionFailed        = 72  #: The login failed due to an IP restriction.
    AccountLockedDown               = 73  #: The current users account is currently locked for use.
    VerifiedEmailRequired           = 74  #: The logon failed because the accounts email is not verified.
    NoMatchingURL                   = 75  #: There is no url matching the provided values.
    BadResponse                     = 76  #: Parse failure, missing field, etc.
    RequirePasswordReEntry          = 77  #: The user cannot complete the action until they re-enter their password.
    ValueOutOfRange                 = 78  #: The value entered is outside the acceptable range.
    UnexpectedError                 = 79  #: Something happened that we didn't expect to ever happen.
    Disabled                        = 80  #: The requested service has been configured to be unavailable.
    InvalidCEGSubmission            = 81  #: The set of files submitted to the CEG server are not valid.
    RestrictedDevice                = 82  #: The device being used is not allowed to perform this action.
    RegionLocked                    = 83  #: The action could not be complete because it is region restricted.
    RateLimitExceeded               = 84  #: Temporary rate limit exceeded. Different from :attr:`LimitExceeded`.
    LoginDeniedNeedTwoFactor        = 85  #: Need two-factor code to login.
    ItemDeleted                     = 86  #: The thing we're trying to access has been deleted.
    AccountLoginDeniedThrottle      = 87  #: Login attempt failed, try to throttle response to possible attacker.
    TwoFactorCodeMismatch           = 88  #: Two factor code mismatch.
    TwoFactorActivationCodeMismatch = 89  #: Activation code for two-factor didn't match.
    NotModified                     = 91  #: Data not modified.
    TimeNotSynced                   = 93  #: The time presented is out of range or tolerance.
    SMSCodeFailed                   = 94  #: SMS code failure (no match, none pending, etc.).
    AccountActivityLimitExceeded    = 96  #: Too many changes to this account.
    PhoneActivityLimitExceeded      = 97  #: Too many changes to this phone.
    RefundToWallet                  = 98  #: Cannot refund to payment method, must use wallet.
    EmailSendFailure                = 99  #: Cannot send an email.
    NotSettled                      = 100  #: Can't perform operation till payment has settled.
    NeedCaptcha                     = 101  #: Needs to provide a valid captcha.
    GSLTDenied                      = 102  #: A game server login token owned by this token's owner has been banned.
    GSOwnerDenied                   = 103  #: Game server owner is denied for other reason.
    InvalidItemType                 = 104  #: The type of thing we were requested to act on is invalid.
    IPBanned                        = 105  #: The IP address has been banned from taking this action.
    GSLTExpired                     = 106  #: This token has expired from disuse; can be reset for use.
    InsufficientFunds               = 107  #: User doesn't have enough wallet funds to complete the action.
    TooManyPending                  = 108  #: There are too many of this thing pending already.
    NoSiteLicensesFound             = 109  #: No site licenses found.
    WGNetworkSendExceeded           = 110  #: The WG couldn't send a response because we exceeded max network send size.
    AccountNotFriends               = 111  #: Not friends with the relevant account.
    LimitedUserAccount              = 112  #: The account is limited and cannot perform this action.
    CantRemoveItem                  = 113  #: Cannot remove the item.
    AccountHasBeenDeleted           = 114  #: The relevant account has been deleted.
    AccountHasCancelledLicense      = 115  #: The user has a user cancelled license.


class EUniverse(IntEnum):
    Invalid  = 0  #: Invalid.
    Public   = 1  #: The standard public universe.
    Beta     = 2  #: Beta universe used inside Valve.
    Internal = 3  #: Internal universe used inside Valve.
    Dev      = 4  #: Dev universe used inside Valve.
    Max      = 6  #: Total number of universes, used for sanity checks.


class EType(IntEnum):
    Invalid        = 0   #: Used for invalid Steam IDs.
    Individual     = 1   #: Single user account.
    Multiseat      = 2   #: Multiseat (e.g. cybercafe) account.
    GameServer     = 3   #: Game server account.
    AnonGameServer = 4   #: Anonymous game server account.
    Pending        = 5   #: Pending.
    ContentServer  = 6   #: Valve internal content server account.
    Clan           = 7   #: Steam clan.
    Chat           = 8   #: Steam group chat or lobby.
    ConsoleUser    = 9   #: Fake SteamID for local PSN account on PS3 or Live account on 360, etc.
    AnonUser       = 10  #: Anonymous user account. (Used to create an account or reset a password)
    Max            = 11  #: Max of 16 items in this field


class ETypeChar(IntEnum):
    I = EType.Invalid         #: The character used for :class:`~steam.EType.Invalid`.
    U = EType.Individual      #: The character used for :class:`~steam.EType.Individual`.
    M = EType.Multiseat       #: The character used for :class:`~steam.EType.Multiseat`.
    G = EType.GameServer      #: The character used for :class:`~steam.EType.GameServer`.
    A = EType.AnonGameServer  #: The character used for :class:`~steam.EType.AnonGameServer`.
    P = EType.Pending         #: The character used for :class:`~steam.EType.Pending`.
    C = EType.ContentServer   #: The character used for :class:`~steam.EType.ContentServer`.
    g = EType.Clan            #: The character used for :class:`~steam.EType.Clan`.
    T = EType.Chat            #: The character used for :class:`~steam.EType.Chat`.
    L = EType.Chat            #: The character used for :class:`~steam.EType.Chat` (Lobby/group chat).
    c = EType.Clan            #: The character used for :class:`~steam.EType.Clan`.
    a = EType.AnonUser        #: The character used for :class:`~steam.EType.Invalid`.


class EInstanceFlag(IntEnum):
    MMSLobby = 0x20000  #: The Steam ID is for a MMS Lobby.
    Lobby    = 0x40000  #: The Steam ID is for a Lobby.
    Clan     = 0x80000  #: The Steam ID is for a Clan.


class EFriendRelationship(IntEnum):  # TODO verify these
    NONE             = 0  #: The user has no relationship to you.
    Blocked          = 1  #: The user ignored the invite.
    RequestRecipient = 2  #: The user has requested to be you.
    Friend           = 3  #: The user is friends with you.
    RequestInitiator = 4  #: You have requested to be friends with the user.
    Ignored          = 5  #: You have explicitly blocked this other user from comments/chat/etc.
    IgnoredFriend    = 6  #: The user has ignored the current user.
    Max              = 8  #: The total number of friend relationships used for looping and verification.


class EPersonaState(IntEnum):
    Offline        = 0  #: The user is not currently logged on.
    Online         = 1  #: The user is logged on.
    Busy           = 2  #: The user is on, but busy.
    Away           = 3  #: The user has been marked as AFK for a short period of time.
    Snooze         = 4  #: The user has been marked as AFK for a long period of time.
    LookingToTrade = 5  #: The user is online and wanting to trade.
    LookingToPlay  = 6  #: The user is online and wanting to play.
    Invisible      = 7  #: The user is invisible.
    Max            = 8  #: The total number of states. Only used for looping and validation.


class EPersonaStateFlag(IntEnum):
    NONE                 = 0
    HasRichPresence      = 1
    InJoinableGame       = 2
    Golden               = 4
    RemotePlayTogether   = 8
    ClientTypeWeb        = 256
    ClientTypeMobile     = 512
    ClientTypeTenfoot    = 1024
    ClientTypeVR         = 2048
    LaunchTypeGamepad    = 4096
    LaunchTypeCompatTool = 8192

    @classmethod
    def components(cls, flag):
        """A helper function to breakdown a flag into its component parts.

        Parameters
        ----------
        flag: :class:`int`
            The flag to break down.

        Returns
        -------
        List[:class:`EPersonaStateFlag`]
            The resolved flags.
        """
        flags = [enum for value, enum in cls._value_map_.items() if value & flag]
        value = 0
        for f in flags:
            value |= f
        return flags if value == flag else []


class ECommunityVisibilityState(IntEnum):
    NONE        = 0  #: The user has no community state.
    Private     = 1  #: The user has a private profile.
    FriendsOnly = 2  #: The user has a friends only profile.
    Public      = 3  #: The user has a public profile.


class ETradeOfferState(IntEnum):
    Invalid                   = 1   #: The trade offer's state is invalid.
    Active                    = 2   #: The trade offer is active.
    Accepted                  = 3   #: The trade offer has been accepted.
    Countered                 = 4   #: The trade offer has been countered.
    Expired                   = 5   #: The trade offer has expired.
    Canceled                  = 6   #: The trade offer has been cancelled.
    Declined                  = 7   #: The trade offer has be declined by the partner.
    InvalidItems              = 8   #: The trade offer has invalid items and has been cancelled.
    ConfirmationNeed          = 9   #: The trade offer needs confirmation.
    CanceledBySecondaryFactor = 10  #: The trade offer was cancelled by second factor.
    StateInEscrow             = 11  #: The trade offer is in escrow.


class EChatEntryType(IntEnum):
    Invalid          = 0   #: An Invalid Chat entry.
    Text             = 1   #: A Normal text message from another user.
    Typing           = 2   #: Another user is typing (not used in multi-user chat).
    InviteGame       = 3   #: An Invite from other user into that users current game.
    LeftConversation = 6   #: A user has left the conversation.
    Entered          = 7   #: A user has entered the conversation (used in multi-user chat and group chat).
    WasKicked        = 8   #: A user was kicked.
    WasBanned        = 9   #: A user was banned.
    Disconnected     = 10  #: A user disconnected.
    HistoricalChat   = 11  #: A chat message from user's chat history or offline message.
    LinkBlocked      = 14  #: A link was removed by the chat filter.


class EUIMode(IntEnum):
    Desktop    = 0  #: The UI mode for the desktop client.
    BigPicture = 1  #: The UI mode for big picture mode.
    Mobile     = 2  #: The UI mode for mobile.
    Web        = 3  #: The UI mode for the web client.


class EUserBadge(IntEnum):
    Invalid                           = 0  #: Invalid Badge.
    YearsOfService                    = 1  #: The years of service badge.
    Community                         = 2  #: The pillar of the community badge.
    Portal2PotatoARG                  = 3  #: The portal to potato badge.
    TreasureHunt                      = 4  #: The treasure hunter badge.
    SummerSale2011                    = 5  #: The Summer sale badge for 2011.
    WinterSale2011                    = 6  #: The Winter sale badge for 2011.
    SummerSale2012                    = 7  #: The Summer sale badge for 2012.
    WinterSale2012                    = 8  #: The Winter sale badge for 2012.
    CommunityTranslator               = 9  #: The community translator badge.
    CommunityModerator                = 10  #: The community moderator badge.
    ValveEmployee                     = 11  #: The Valve employee badge.
    GameDeveloper                     = 12  #: The game developer badge.
    GameCollector                     = 13  #: The game collector badge.
    TradingCardBetaParticipant        = 14  #: The trading card beta participant badge.
    SteamBoxBeta                      = 15  #: The Steam box beta badge.
    Summer2014RedTeam                 = 16  #: The Summer sale badge for 2014 for the red team.
    Summer2014BlueTeam                = 17  #: The Summer sale badge for 2014 for the blue team.
    Summer2014PinkTeam                = 18  #: The Summer sale badge for 2014 for the pink team.
    Summer2014GreenTeam               = 19  #: The Summer sale badge for 2014 for the green team.
    Summer2014PurpleTeam              = 20  #: The Summer sale badge for 2014 for the purple team.
    Auction2014                       = 21  #: The auction badge for 2014.
    GoldenProfile2014                 = 22  #: The golden profile for 2014.
    TowerAttackMiniGame               = 23  #: The tower attack mini-game badge.
    Winter2015ARGRedHerring           = 24  #: The Winter ARG red herring badge for 2015.
    SteamAwards2016Nominations        = 25  #: The Steam Awards Nominations badge for 2016.
    StickerCompletionist2017          = 26  #: The sticker completionist badge for 2017.
    SteamAwards2017Nominations        = 27  #: The Steam Awards Nominations badge for 2017.
    SpringCleaning2018                = 28  #: The Spring cleaning badge for 2018.
    Salien                            = 29  #: The Salien badge.
    RetiredModerator                  = 30  #: The retired moderator badge.
    SteamAwards2018Nominations        = 31  #: The Steam Awards Nominations badge for 2018.
    ValveModerator                    = 32  #: The Valve moderator badge.
    WinterSale2018                    = 33  #: The Winter sale badge for 2018.
    LunarNewYearSale2019              = 34  #: The lunar new years sale badge for 2019.
    LunarNewYearSale2019GoldenProfile = 35  #: The lunar new year golden profile sale badge for 2019.
    SpringCleaning2019                = 36  #: The Spring cleaning badge for 2019.
    Summer2019                        = 37  #: The Summer sale badge for 2019.
    Summer2019TeamHare                = 38  #: The Summer sale badge for 2014 for team hare.
    Summer2019TeamTortoise            = 39  #: The Summer sale badge for 2014 for team tortoise.
    Summer2019TeamCorgi               = 40  #: The Summer sale badge for 2014 for team corgi.
    Summer2019TeamCockatiel           = 41  #: The Summer sale badge for 2014 for team cockatiel.
    Summer2019TeamPig                 = 42  #: The Summer sale badge for 2014 for team pig.
    SteamAwards2019Nominations        = 43  #: The Steam Awards Nominations badge for 2019.
    WinterSaleEvent2019               = 44  #: The Winter sale badge for 2019.
