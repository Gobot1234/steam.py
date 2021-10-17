"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz
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

EnumMeta originally from https://github.com/Rapptz/discord.py/blob/master/discord/enums.py
"""

from __future__ import annotations

import builtins
from collections.abc import Generator
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Callable, Generic, NoReturn, TypeVar

from typing_extensions import Literal

if TYPE_CHECKING:
    from _typeshed import Self


__all__ = (
    "Enum",
    "IntEnum",
    "Flags",
    "Result",
    "Universe",
    "Type",
    "TypeChar",
    "InstanceFlag",
    "FriendRelationship",
    "PersonaState",
    "PersonaStateFlag",
    "CommunityVisibilityState",
    "TradeOfferState",
    "ChatEntryType",
    "UIMode",
    "UserBadge",
    "ReviewType",
    "GameServerRegion",
    "ClanEvent",
    "ProfileItemType",
)

T = TypeVar("T")
E = TypeVar("E", bound="Enum")
IE = TypeVar("IE", bound="IntEnum")


def _is_descriptor(obj: Any) -> bool:
    """Returns True if obj is a descriptor, False otherwise."""
    return hasattr(obj, "__get__") or hasattr(obj, "__set__") or hasattr(obj, "__delete__")


class EnumMeta(type, Generic[E]):
    _value_map_: dict[Any, E]
    _member_map_: dict[str, E]

    def __new__(mcs, name: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> type[E]:
        set_attribute = super().__setattr__
        enum_class: type[E] = super().__new__(mcs, name, bases, attrs)  # type: ignore
        enum_class_new: Callable[[type[E], str, Any], E] = enum_class.__new__  #: type: ignore

        value_mapping: dict[Any, E] = {}
        member_mapping: dict[str, E] = {}

        for key, value in attrs.items():
            if key[0] == "_" or _is_descriptor(value):
                continue

            member = value_mapping.get(value)
            if member is None:
                member = enum_class_new(enum_class, name=key, value=value)
                value_mapping[value] = member

            member_mapping[key] = member
            set_attribute(enum_class, key, member)

        set_attribute(enum_class, "_value_map_", value_mapping)
        set_attribute(enum_class, "_member_map_", member_mapping)
        return enum_class

    def __call__(cls: type[E], value: Any) -> E:
        try:
            return cls._value_map_[value]
        except (KeyError, TypeError):
            raise ValueError(f"{value!r} is not a valid {cls.__name__}")

    def __repr__(cls) -> str:
        return f"<enum {cls.__name__!r}>"

    def __iter__(cls: type[E]) -> Generator[E, None, None]:
        yield from cls._member_map_.values()

    def __reversed__(cls: type[E]) -> Generator[E, None, None]:
        yield from reversed(tuple(cls._member_map_.values()))  # can remove tuple cast after 3.7

    def __len__(cls) -> int:
        return len(cls._member_map_)

    def __getitem__(cls: type[E], key: str) -> E:
        return cls._member_map_[key]

    def __setattr__(cls, name: str, value: Any) -> NoReturn:
        raise AttributeError(f"{cls.__name__}: cannot reassign Enum members.")

    def __delattr__(cls, name: str) -> NoReturn:
        raise AttributeError(f"{cls.__name__}: cannot delete Enum members.")

    def __contains__(cls, member: object) -> bool:
        if not isinstance(member, Enum):
            return NotImplemented
        return isinstance(member, cls) and member.name in cls._member_map_

    @property
    def __members__(cls: type[E]) -> MappingProxyType[str, E]:
        return MappingProxyType(cls._member_map_)


class Enum(metaclass=EnumMeta["Self"]):
    """A general enumeration, emulates `enum.Enum`."""

    name: str
    value: Any

    def __new__(cls: type[Self], *, name: str, value: Any) -> Self:
        # N.B. this method is not ever called after enum creation as it is shadowed by EnumMeta.__call__ and is just
        # for creating Enum members
        super_ = super()
        self = (
            super_.__new__(cls, value)
            if any(not issubclass(base, Enum) for base in cls.__mro__[:-1])  # is it is a mixin enum
            else super_.__new__(cls)
        )
        super_.__setattr__(self, "name", name)
        super_.__setattr__(self, "value", value)
        return self

    def __setattr__(self, key: str, value: Any) -> NoReturn:
        raise AttributeError(f"{self.__class__.__name__} Cannot reassign an Enum members attribute's.")

    def __delattr__(self, item: Any) -> NoReturn:
        raise AttributeError(f"{self.__class__.__name__} Cannot delete an Enum members attribute's.")

    def __bool__(self) -> Literal[True]:
        return True  # an enum member with a zero value would return False otherwise

    def __str__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}.{self.name}: {self.value!r}>"

    @classmethod
    def try_value(cls: type[Self], value: Any) -> Self:
        try:
            return cls._value_map_[value]
        except (KeyError, TypeError):
            return cls.__new__(cls, name=f"{cls.__name__}UnknownValue", value=value)


class IntEnum(Enum, int):
    """An enumeration where all the values are integers, emulates `enum.IntEnum`."""


Enum_ = Enum  # needed for game.Games
if TYPE_CHECKING or getattr(builtins, "__sphinx__", False):
    from enum import Enum as _Enum, IntEnum as _IntEnum

    class Enum(_Enum):
        @classmethod
        def try_value(cls: type[Self], value: Any) -> Self:
            ...

    class IntEnum(_IntEnum, Enum):
        pass

    # pretending these are enum.IntEnum subclasses makes things much nicer for linters as IntEnums have custom behaviour
    # I can't seem to replicate


class Flags(IntEnum):
    @classmethod
    def try_value(cls: type[E], value: int) -> E:
        flags = [enum for enum in cls if enum.value & value]
        if flags:
            returning_flag = flags[0]
            for flag in flags[1:]:
                returning_flag |= flag
            if returning_flag == value:
                return returning_flag
        return cls.__new__(cls, name=f"{cls.__name__}UnknownValue", value=value)

    def __or__(self: Self, other: Self | int) -> Self:
        cls = self.__class__
        return cls.__new__(cls, name=f"{self.name} | {other.name}", value=self.value | int(other))

    def __and__(self: Self, other: Self | int) -> Self:
        cls = self.__class__
        return cls.__new__(cls, name=f"{self.name} & {other.name}", value=self.value & int(other))


# fmt: off
class Result(IntEnum):
    # these are a combination of https://partner.steamgames.com/doc/api/steam_api#EResult and https://steamerrors.com
    Invalid                         = 0  #: Invalid Result.
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
    GSLTExpired                     = 106  #: This Game Server Login Token has expired from disuse; can be reset for use.
    InsufficientFunds               = 107  #: User doesn't have enough wallet funds to complete the action.
    TooManyPending                  = 108  #: There are too many of this thing pending already.
    NoSiteLicensesFound             = 109  #: No site licenses found.
    WGNetworkSendExceeded           = 110  #: The WG couldn't send a response because we exceeded max network send size.
    AccountNotFriends               = 111  #: Not friends with the relevant account.
    LimitedUserAccount              = 112  #: The account is limited and cannot perform this action.
    CantRemoveItem                  = 113  #: Cannot remove the item.
    AccountHasBeenDeleted           = 114  #: The relevant account has been deleted.
    AccountHasCancelledLicense      = 115  #: The user has a user cancelled license.
    DeniedDueToCommunityCooldown    = 116  #: The request was denied due to community cooldown.
    NoLauncherSpecified             = 117  #: No launcher was specified.
    MustAgreeToSSA                  = 118  #: User must agree to china SSA or global SSA before login.
    ClientNoLongerSupported         = 119  #: The specified launcher type is no longer supported.


class Universe(IntEnum):
    Invalid  = 0  #: Invalid.
    Public   = 1  #: The standard public universe.
    Beta     = 2  #: Beta universe used inside Valve.
    Internal = 3  #: Internal universe used inside Valve.
    Dev      = 4  #: Dev universe used inside Valve.
    Max      = 6  #: Total number of universes, used for sanity checks.


class Type(IntEnum):
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


class TypeChar(IntEnum):
    I = Type.Invalid         #: The character used for :class:`~steam.Type.Invalid`.
    U = Type.Individual      #: The character used for :class:`~steam.Type.Individual`.
    M = Type.Multiseat       #: The character used for :class:`~steam.Type.Multiseat`.
    G = Type.GameServer      #: The character used for :class:`~steam.Type.GameServer`.
    A = Type.AnonGameServer  #: The character used for :class:`~steam.Type.AnonGameServer`.
    P = Type.Pending         #: The character used for :class:`~steam.Type.Pending`.
    C = Type.ContentServer   #: The character used for :class:`~steam.Type.ContentServer`.
    g = Type.Clan            #: The character used for :class:`~steam.Type.Clan`.
    T = Type.Chat            #: The character used for :class:`~steam.Type.Chat` (Lobby/group chat).
    L = Type.Chat            #: The character used for :class:`~steam.Type.Chat` (Lobby/group chat).
    c = Type.Clan            #: The character used for :class:`~steam.Type.Clan`.
    a = Type.AnonUser        #: The character used for :class:`~steam.Type.Invalid`.


class InstanceFlag(Flags):
    MMSLobby = 0x20000  #: The Steam ID is for a MMS Lobby.
    Lobby    = 0x40000  #: The Steam ID is for a Lobby.
    Clan     = 0x80000  #: The Steam ID is for a Clan.


class FriendRelationship(IntEnum):
    NONE             = 0  #: The user has no relationship to you.
    Blocked          = 1  #: The user ignored the invite.
    RequestRecipient = 2  #: The user has requested to be you.
    Friend           = 3  #: The user is friends with you.
    RequestInitiator = 4  #: You have requested to be friends with the user.
    Ignored          = 5  #: You have explicitly blocked this other user from comments/chat/etc.
    IgnoredFriend    = 6  #: The user has ignored the current user.
    Max              = 8  #: The total number of friend relationships used for looping and verification.


class PersonaState(IntEnum):
    Offline        = 0  #: The user is not currently logged on.
    Online         = 1  #: The user is logged on.
    Busy           = 2  #: The user is on, but busy.
    Away           = 3  #: The user has been marked as AFK for a short period of time.
    Snooze         = 4  #: The user has been marked as AFK for a long period of time.
    LookingToTrade = 5  #: The user is online and wanting to trade.
    LookingToPlay  = 6  #: The user is online and wanting to play.
    Invisible      = 7  #: The user is invisible.
    Max            = 8  #: The total number of states. Only used for looping and validation.


class PersonaStateFlag(Flags):
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


class CommunityVisibilityState(IntEnum):
    NONE        = 0  #: The user has no community state.
    Private     = 1  #: The user has a private profile.
    FriendsOnly = 2  #: The user has a friends only profile.
    Public      = 3  #: The user has a public profile.


class TradeOfferState(IntEnum):
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

    @property
    def event_name(self) -> str | None:
        try:
            return {
                TradeOfferState.Accepted: "accept",
                TradeOfferState.Countered: "counter",
                TradeOfferState.Expired: "expire",
                TradeOfferState.Canceled: "cancel",
                TradeOfferState.Declined: "decline",
                TradeOfferState.CanceledBySecondaryFactor: "cancel",
            }[self]
        except KeyError:
            return None


class ChatEntryType(IntEnum):
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


class UIMode(IntEnum):
    Desktop    = 0  #: The UI mode for the desktop client.
    BigPicture = 1  #: The UI mode for big picture mode.
    Mobile     = 2  #: The UI mode for mobile.
    Web        = 3  #: The UI mode for the web client.


class UserBadge(IntEnum):
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
    WinterSale2019Steamville          = 45  #: The Winter sale Steamville badge for 2019.
    LunarNewYearSale2020              = 46  #: The lunar new years sale badge for 2020.
    SpringCleaning2020                = 47  #: The Spring cleaning badge for 2020.
    AwardsCommunityContributor        = 48  #: The Steam Awards Community Contributor badge.
    AwardsCommunityPatron             = 49  #: The Steam Awards Community Patron badge.
    SteamAwards2020Nominations        = 50  #: The Steam Awards Nominations badge for 2020.


class ReviewType(IntEnum):
    NONE                   = 0  #: No reviews.
    OverwhelminglyNegative = 1  #: 0 - 19% positive reviews and few of them.
    VeryNegative           = 2  #: 0 - 19% positive reviews.
    Negative               = 3  #: 0 - 39% positive reviews.
    MostlyNegative         = 4  #: 20 - 39% positive reviews but few of them.
    Mixed                  = 5  #: 40 - 69% positive reviews.
    MostlyPositive         = 6  #: 70 - 79% positive reviews.
    Positive               = 7  #: 80 - 100% positive reviews but few of them.
    VeryPositive           = 8  #: 94 - 80% positive reviews.
    OverwhelminglyPositive = 9  #: 95 - 100% positive reviews.


class GameServerRegion(IntEnum):
    NONE         = -1   #: No set game region.
    USEastCoast  = 0    #: A server on the USA's East Coast.
    USWestCoast  = 1    #: A server on the USA's West Coast.
    SouthAmerica = 2    #: A server in South America.
    Europe       = 3    #: A server in Europe.
    Asia         = 4    #: A server in Asia.
    Australia    = 5    #: A server in Australia.
    MiddleEast   = 6    #: A server in the Middle East.
    Africa       = 7    #: A server in Africa.
    World        = 255  #: A server somewhere in the world.


class ClanEvent(IntEnum):
    Other                  = 1  #: An unspecified event.
    Game                   = 2  #: A game event.
    Party                  = 3  #: A party event.
    Meeting                = 4  #: An important meeting.
    SpecialCause           = 5  #: An event for a special cause.
    MusicAndArts           = 6  #: A music or art event.
    Sports                 = 7  #: A sporting event.
    Trip                   = 8  #: A clan trip.
    Chat                   = 9  #: A chat event.
    GameRelease            = 10  #: A game release event.
    Broadcast              = 11  #: A broadcast event.
    SmallUpdate            = 12  #: A small update event.
    PreAnnounceMajorUpdate = 13  #: A pre-announcement for a major update event.
    MajorUpdate            = 14  #: A major update event.
    DLCRelease             = 15  #: A dlc release event.
    FutureRelease          = 16  #: A future release event.
    ESportTournamentStream = 17  #: An e-sport tournament stream event.
    DevStream              = 18  #: A developer stream event.
    FamousStream           = 19  #: A famous stream event.
    GameSales              = 20  #: A game sales event.
    GameItemSales          = 21  #: A game item sales event.
    InGameBonusXP          = 22  #: An in game bonus xp event.
    InGameLoot             = 23  #: An in game loot event.
    InGamePerks            = 24  #: An in game perks event.
    InGameChallenge        = 25  #: An in game challenge event.
    InGameContest          = 26  #: An in game contest event.
    IRL                    = 27  #: An in real life event.
    News                   = 28  #: A news event.
    BetaRelease            = 29  #: A beta release event.
    InGameContentRelease   = 30  #: An in game content release event.
    FreeTrial              = 31  #: A free trial event.
    SeasonRelease          = 32  #: A season release event.
    SeasonUpdate           = 33  #: A season update event.
    Crosspost              = 34  #: A cross post event.
    InGameGeneral          = 35  #: An in game general event.


class ProfileItemType(IntEnum):
    Invalid                   = 0   #: An invalid item type.
    RareAchievementShowcase   = 1   #: A rare achievements showcase.
    GameCollector             = 2   #: A game collector section.
    ItemShowcase              = 3   #: An item showcase.
    TradeShowcase             = 4   #: A trade info showcase.
    Badges                    = 5   #: A badges showcase.
    FavoriteGame              = 6   #: A favourite game section.
    ScreenshotShowcase        = 7   #: A screenshot showcase.
    CustomText                = 8   #: A custom text section.
    FavoriteGroup             = 9   #: A favourite game showcase.
    Recommendation            = 10  #: A review showcase.
    WorkshopItem              = 11  #: A workshop item showcase.
    MyWorkshop                = 12  #: A showcase of a workshop item made by profile's owner.
    ArtworkShowcase           = 13  #: An artwork showcase.
    VideoShowcase             = 14  #: A video showcase.
    Guides                    = 15  #: A guide showcase.
    MyGuides                  = 16  #: A showcase of the profile's owner's guides.
    Achievements              = 17  #: The owner's profile's achievements.
    Greenlight                = 18  #: A greenlight showcase.
    MyGreenlight              = 19  #: A showcase of a greenlighted game the profiles' owner has made.
    Salien                    = 20  #: A salien showcase.
    LoyaltyRewardReactions    = 21  #: A loyalty reward showcase.
    SingleArtworkShowcase     = 22  #: A single artwork showcase.
    AchievementsCompletionist = 23  #: An achievements completeionist showcase.
# fmt: on


# shim for old enum names
def __getattr__(name: str) -> Any:
    if name[0] == "E" and name[1:] in __all__:
        import warnings

        warnings.warn('Enums with "E" prefix are depreciated and scheduled for removal in V.1', DeprecationWarning)
        return globals()[name[1:]]

    raise AttributeError(name)
