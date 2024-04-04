"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from enum import Enum as _Enum, EnumMeta as _EnumMeta
from functools import reduce
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Generic, Literal, SupportsInt, TypeVar, cast

from ._const import DOCS_BUILDING

if TYPE_CHECKING:
    from typing_extensions import Never, Self

__all__ = (
    "Enum",
    "IntEnum",
    "Flags",
    "Intents",
    "Result",
    "Language",
    "Currency",
    "Realm",
    "PurchaseResult",
    "Universe",
    "Type",
    "TypeChar",
    "Instance",
    "FriendRelationship",
    "PersonaState",
    "PersonaStateFlag",
    "CommunityVisibilityState",
    "TradeOfferState",
    "ChatMemberRank",
    "ChatMemberJoinState",
    "ChatEntryType",
    "ClanAccountFlags",
    "UIMode",
    "ReviewType",
    "GameServerRegion",
    "EventType",
    "ProfileItemType",
    "ProfileCustomisationStyle",
    "CommunityItemClass",
    "ProfileItemEquippedFlag",
    "DepotFileFlag",
    "AppType",
    "LicenseFlag",
    "LicenseType",
    "BillingType",
    "PaymentMethod",
    "PackageStatus",
    "PublishedFileRevision",
    "PublishedFileType",
    "PublishedFileVisibility",
    "PublishedFileQueryType",
    "PublishedFileQueryFileType",
    "LeaderboardUploadScoreMethod",
    "LeaderboardSortMethod",
    "LeaderboardDisplayType",
    "LeaderboardDataRequest",
    "CommunityDefinitionItemType",
    "AuthSessionResponse",
    "ContentDescriptor",
    "UserNewsType",
)

T = TypeVar("T")

T_co = TypeVar("T_co", covariant=True)
TT = TypeVar("TT", bound="type[Any]")


class classproperty(Generic[TT, T_co]):
    def __init__(self, func: Callable[[TT], T_co]):
        self.__func__ = func

    def __get__(self, instance: Any, type: TT) -> T_co:
        return self.__func__(type)


def _is_descriptor(obj: object, /) -> bool:
    """Returns True if obj is a descriptor, False otherwise."""
    return hasattr(obj, "__get__") or hasattr(obj, "__set__") or hasattr(obj, "__delete__")


class EnumDict(dict[str, Any]):
    """Required to detect the difference between:

    class MyEnum(steam.Enum):
        A = 1
        B = 2
        C = A  # this is an alias for A and not a new member
        D = 2  # this is a distinct member
    """

    def __init__(self):
        self.aliases: set[str] = set()

    def __getitem__(self, key: str) -> Any:
        self.aliases.add(key)
        return super().__getitem__(key)


class EnumType(_EnumMeta if TYPE_CHECKING else type):
    _value_map_: Mapping[Any, Enum]
    _member_map_: Mapping[str, Enum]  # type: ignore

    @classmethod
    def __prepare__(mcs, name: str, bases: tuple[type, ...]) -> EnumDict:  # type: ignore
        return EnumDict()

    def __new__(mcs, name: str, bases: tuple[type, ...], namespace: EnumDict) -> type[Enum]:
        value_map: dict[Any, Enum] = {}
        member_map: dict[str, Enum] = {}

        new_mcs: type[Self] = type(
            f"{name}Type",
            tuple(
                dict.fromkeys([base.__class__ for base in bases if base.__class__ is not type] + [EnumType, type])
            ),  # reorder the bases so EnumType and type are last to avoid conflicts
            {"_value_map_": value_map, "_member_map_": member_map},
        )  # type: ignore

        members = {name: value for name, value in namespace.items() if not _is_descriptor(value) and name[0] != "_"}

        cls = cast(
            "type[Enum]",
            type.__new__(new_mcs, name, bases, {key: value for key, value in namespace.items() if key not in members}),
        )  # this allows us to disallow member access from other members as members become proper class variables

        for name, value in members.items():
            if (member := value_map.get(value)) is None or member.name not in namespace.aliases:
                member = cls._new_member(name=name, value=value)
                value_map[value] = member

            member_map[name] = member
            type.__setattr__(new_mcs, name, member)

        return cls

    if not TYPE_CHECKING:

        def __iter__(cls) -> Generator[Enum, None, None]:
            yield from cls._member_map_.values()

        def __reversed__(cls) -> Generator[Enum, None, None]:
            yield from reversed(cls._member_map_.values())

        def __getitem__(cls, key: str) -> Enum:
            return cls._member_map_[key]

        @property
        def __members__(cls) -> MappingProxyType[str, Enum]:
            return MappingProxyType(cls._member_map_)

    def __repr__(cls) -> str:
        return f"<enum {cls.__name__!r}>"

    def __len__(cls) -> int:
        return len(cls._member_map_)

    def __setattr__(cls, name: str, value: Any) -> Never:
        if name.startswith("__") and name.endswith("__"):
            return super().__setattr__(name, value)  # type: ignore
        raise AttributeError(f"{cls.__name__}: cannot reassign Enum members.")

    def __delattr__(cls, name: str) -> Never:
        raise AttributeError(f"{cls.__name__}: cannot delete Enum members.")

    def __contains__(cls, member: object) -> bool:
        return isinstance(member, Enum) and isinstance(member, cls) and member.name in cls._member_map_

    def __dir__(self) -> list[str]:
        return super().__dir__() + list(self._member_map_)


# pretending these are enum subclasses makes things much nicer for linters as enums have custom behaviour you can't
# replicate in the current type system
class Enum(_Enum if TYPE_CHECKING else object, metaclass=EnumType):
    """A general enumeration, emulates `enum.Enum`."""

    _member_map_: Mapping[str, Self]
    _value_map_: Mapping[Any, Self]

    def __new__(cls, value: Any) -> Self:
        try:
            return cls._value_map_[value]
        except (KeyError, TypeError):
            raise ValueError(f"{value!r} is not a valid {cls.__name__}") from None

    @classmethod
    def _new_member(cls, *, name: str, value: Any) -> Self:
        self = (
            super().__new__(cls, value)
            if any(not issubclass(base, Enum) for base in cls.__mro__[:-1])  # is it is a mixin enum
            else super().__new__(cls)  # type: ignore
        )
        super().__setattr__(self, "name", name)
        super().__setattr__(self, "value", value)

        return self

    if not DOCS_BUILDING:

        def __setattr__(self, key: str, value: Any) -> Never:
            raise AttributeError(f"Cannot reassign {self.__class__.__name__} members attribute's.")

        def __delattr__(self, item: Any) -> Never:
            raise AttributeError(f"Cannot delete {self.__class__.__name__} attribute's.")

    def __bool__(self) -> Literal[True]:
        return True  # an enum member with a zero value would return False otherwise

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}.{self.name}"

    @classmethod
    def try_value(cls, value: Any, /) -> Self:
        try:
            return cls._value_map_[value]
        except (KeyError, TypeError):
            return cls._new_member(name=f"{cls.__name__}UnknownValue", value=value)


class IntEnum(Enum, int):
    """An enumeration where all the values are integers, emulates `enum.IntEnum`."""

    if TYPE_CHECKING:

        def __new__(cls, value: int) -> Self: ...

        @classmethod
        def try_value(cls, value: int) -> Self: ...


class Flags(IntEnum):
    @classmethod
    def try_value(cls, value: int) -> Self:
        if value == 0:
            # causes flags to be iter(cls) does |= on every value (which is not 0) it always returns UnknownValue
            return super().try_value(value)
        flags: Generator[Self, None, None] = (enum for enum in cls if enum.value & value)  # type: ignore
        returning_flag = next(flags, None)
        if returning_flag is not None:
            for flag in flags:
                returning_flag |= flag
            if returning_flag == value:
                return returning_flag
        return cls._new_member(name=f"{cls.__name__}UnknownValue", value=value)

    def __or__(self, other: SupportsInt) -> Self:
        cls = self.__class__
        value = self.value | int(other)
        try:
            return cls._value_map_[value]
        except KeyError:
            return cls._new_member(name=f"{self.name} | {getattr(other, 'name', other)}", value=value)

    def __and__(self, other: SupportsInt) -> Self:
        cls = self.__class__
        value = self.value & int(other)
        try:
            return cls._value_map_[value]
        except KeyError:
            return cls._new_member(name=f"{self.name} & {getattr(other, 'name', other)}", value=value)

    def __invert__(self) -> Self:
        member = self.try_value(~-self.value)
        if member.name.endswith("UnknownValue"):
            object.__setattr__(member, "name", f"~{self.name}")
        return member

    __ror__ = __or__
    __rand__ = __and__


# fmt: off
class Intents(Flags):
    """Flags that control what features the client will interact with."""
    NONE        = 0
    """Very little interaction happens from our end of the connection."""
    Users       = 1 << 0
    """Users and members are cached."""
    TradeOffers = 1 << 1
    """TradeOffers are fetched and processed automatically"""
    Messages    = 1 << 2
    """Messages are cached, cannot be enabled without :attr:`Chat`."""
    Chat        = 1 << 3
    """Chats/Channels are cached."""
    ChatGroups  = 1 << 4
    """Groups/Clans are cached."""
    Market      = 1 << 5
    """Market interactions are enabled.

    Warning
    -------
    Using this comes could lead to your account being banned, much more so than with any other library operations.
    """

    @classproperty
    def All(cls: type[Self]) -> Self:  # type: ignore
        """Returns all the intents.

        Warning
        -------
        This will return unsafe intents. Use at your own risk!

        See also
        --------
        :attr:`Safe` as a safe alternative to this function which is less likely to get you banned.
        """
        return reduce(cls.__or__, cls._value_map_.values())

    @classproperty
    def Safe(cls: type[Self]) -> Self:  # type: ignore
        """Returns all the intents without the unsafe ones."""
        return cls.All & ~cls.Market


class Result(IntEnum):
    """The result of a Steam API call. Read more on :works:`steamworks <api/steam_api#EResult>`."""
    # these are a combination of https://partner.steamgames.com/doc/api/steam_api#EResult and https://steamerrors.com
    Invalid                         = 0
    """Invalid Result."""
    OK                              = 1
    """Success."""
    Fail                            = 2
    """Generic failure."""
    NoConnection                    = 3
    """Your Steam client doesn't have a connection to the back-end."""
    InvalidPassword                 = 5
    """Password/ticket is invalid."""
    LoggedInElsewhere               = 6
    """Same user logged in elsewhere."""
    InvalidProtocolVersion          = 7
    """Protocol version is incorrect."""
    InvalidParameter                = 8
    """A parameter is incorrect."""
    FileNotFound                    = 9
    """File was not found."""
    Busy                            = 10
    """Called method busy - action not taken."""
    InvalidState                    = 11
    """Called object was in an invalid state."""
    InvalidName                     = 12
    """The name was invalid."""
    InvalidEmail                    = 13
    """The email was invalid."""
    DuplicateName                   = 14
    """The name is not unique."""
    AccessDenied                    = 15
    """Access is denied."""
    Timeout                         = 16
    """Operation timed out."""
    Banned                          = 17
    """VAC2 banned."""
    AccountNotFound                 = 18
    """Account not found."""
    InvalidSteamID                  = 19
    """The Steam ID was invalid."""
    ServiceUnavailable              = 20
    """The requested service is currently unavailable."""
    NotLoggedOn                     = 21
    """The user is not logged on."""
    Pending                         = 22
    """Request is pending (may be in process, or waiting on third party)."""
    EncryptionFailure               = 23
    """Encryption or decryption failed."""
    InsufficientPrivilege           = 24
    """Insufficient privilege."""
    LimitExceeded                   = 25
    """Too much of a good thing."""
    Revoked                         = 26
    """Access has been revoked (used for revoked guest passes)."""
    Expired                         = 27
    """License/Guest pass the user is trying to access is expired."""
    AlreadyRedeemed                 = 28
    """Guest pass has already been redeemed by account, cannot be acknowledged again."""
    DuplicateRequest                = 29
    """The request is a duplicate, ignored this time."""
    AlreadyOwned                    = 30
    """All the games in guest pass redemption request are already owned by the user."""
    IPNotFound                      = 31
    """IP address not found."""
    PersistFailed                   = 32
    """Failed to write change to the data store."""
    LockingFailed                   = 33
    """Failed to acquire access lock for this operation."""
    LogonSessionReplaced            = 34
    """The logon session has been replaced."""
    ConnectFailed                   = 35
    """Failed to connect."""
    HandshakeFailed                 = 36
    """The authentication handshake has failed."""
    IOFailure                       = 37
    """Generic IO failure."""
    RemoteDisconnect                = 38
    """The remote server has disconnected."""
    ShoppingCartNotFound            = 39
    """Failed to find the shopping cart requested."""
    Blocked                         = 40
    """A user blocked the action."""
    Ignored                         = 41
    """The target is ignoring sender."""
    NoMatch                         = 42
    """Nothing matching the request found."""
    AccountDisabled                 = 43
    """The account is disabled."""
    ServiceReadOnly                 = 44
    """This service is not accepting content changes right now."""
    AccountNotFeatured              = 45
    """Account doesn't have value, so this feature isn't available."""
    AdministratorOK                 = 46
    """Allowed to take this action, but only because requester is admin."""
    ContentVersion                  = 47
    """A Version mismatch in content transmitted within the Steam protocol."""
    TryAnotherCM                    = 48
    """The current CM can't service the user making a request, should try another."""
    PasswordRequiredToKickSession   = 49
    """You are already logged in elsewhere, this cached credential login has failed."""
    AlreadyLoggedInElsewhere        = 50
    """You are already logged in elsewhere, you must wait."""
    Suspended                       = 51
    """Long running operation (content download) suspended/paused."""
    Cancelled                       = 52
    """Operation canceled (typically by user content download)."""
    DataCorruption                  = 53
    """Operation canceled because data is malformed or unrecoverable."""
    DiskFull                        = 54
    """Operation canceled - not enough disk space."""
    RemoteCallFailed                = 55
    """An remote call or IPC call failed."""
    ExternalAccountUnlinked         = 57
    """External account is not linked to a Steam account."""
    PSNTicketInvalid                = 58
    """PSN ticket was invalid."""
    ExternalAccountAlreadyLinked    = 59
    """External account is already linked to some other account."""
    RemoteFileConflict              = 60
    """The sync cannot resume due to a conflict between the local and remote files."""
    IllegalPassword                 = 61
    """The requested new password is not legal."""
    SameAsPreviousValue             = 62
    """New value is the same as the old one (secret question and answer)."""
    AccountLogonDenied              = 63
    """Account login denied due to 2nd factor authentication failure."""
    CannotUseOldPassword            = 64
    """The requested new password is not legal."""
    InvalidLoginAuthCode            = 65
    """Account login denied due to auth code invalid."""
    AccountLogonDeniedNoMail        = 66
    """Account login denied due to 2nd factor authentication failure."""
    HardwareNotCapableOfIPT         = 67
    """The user's hardware does not support Intel's identity protection technology."""
    IPTInitError                    = 68
    """Intel's Identity Protection Technology has failed to initialize."""
    ParentalControlRestricted       = 69
    """Operation failed due to parental control restrictions for current user."""
    FacebookQueryError              = 70
    """Facebook query returned an error."""
    ExpiredLoginAuthCode            = 71
    """Account login denied due to auth code expired."""
    IPLoginRestrictionFailed        = 72
    """The login failed due to an IP restriction."""
    AccountLockedDown               = 73
    """The current users account is currently locked for use."""
    VerifiedEmailRequired           = 74
    """The logon failed because the accounts email is not verified."""
    NoMatchingURL                   = 75
    """There is no url matching the provided values."""
    BadResponse                     = 76
    """Parse failure, missing field, etc."""
    RequirePasswordReEntry          = 77
    """The user cannot complete the action until they re-enter their password."""
    ValueOutOfRange                 = 78
    """The value entered is outside the acceptable range."""
    UnexpectedError                 = 79
    """Something happened that we didn't expect to ever happen."""
    Disabled                        = 80
    """The requested service has been configured to be unavailable."""
    InvalidCEGSubmission            = 81
    """The set of files submitted to the CEG server are not valid."""
    RestrictedDevice                = 82
    """The device being used is not allowed to perform this action."""
    RegionLocked                    = 83
    """The action could not be complete because it is region restricted."""
    RateLimitExceeded               = 84
    """Temporary rate limit exceeded. Different from :attr:`LimitExceeded`."""
    LoginDeniedNeedTwoFactor        = 85
    """Need two-factor code to log in."""
    ItemDeleted                     = 86
    """The thing we're trying to access has been deleted."""
    AccountLoginDeniedThrottle      = 87
    """Login attempt failed, try to throttle response to possible attacker."""
    TwoFactorCodeMismatch           = 88
    """Two-factor code mismatch."""
    TwoFactorActivationCodeMismatch = 89
    """Activation code for two-factor didn't match."""
    NotModified                     = 91
    """Data not modified."""
    TimeNotSynced                   = 93
    """The time presented is out of range or tolerance."""
    SMSCodeFailed                   = 94
    """SMS code failure (no match, none pending, etc.)."""
    AccountActivityLimitExceeded    = 96
    """Too many changes to this account."""
    PhoneActivityLimitExceeded      = 97
    """Too many changes to this phone."""
    RefundToWallet                  = 98
    """Cannot refund to payment method, must use wallet."""
    EmailSendFailure                = 99
    """Cannot send an email."""
    NotSettled                      = 100
    """Can't perform operation till payment has settled."""
    NeedCaptcha                     = 101
    """Needs to provide a valid captcha."""
    GSLTDenied                      = 102
    """A game server login token owned by this token's owner has been banned."""
    GSOwnerDenied                   = 103
    """Game server owner is denied for other reason."""
    InvalidItemType                 = 104
    """The type of thing we were requested to act on is invalid."""
    IPBanned                        = 105
    """The IP address has been banned from taking this action."""
    GSLTExpired                     = 106
    """This Game Server Login Token has expired from disuse; can be reset for use."""
    InsufficientFunds               = 107
    """User doesn't have enough wallet funds to complete the action."""
    TooManyPending                  = 108
    """There are too many of this thing pending already."""
    NoSiteLicensesFound             = 109
    """No site licenses found."""
    WGNetworkSendExceeded           = 110
    """The WG couldn't send a response because we exceeded max network send size."""
    AccountNotFriends               = 111
    """Not friends with the relevant account."""
    LimitedUserAccount              = 112
    """The account is limited and cannot perform this action."""
    CantRemoveItem                  = 113
    """Cannot remove the item."""
    AccountHasBeenDeleted           = 114
    """The relevant account has been deleted."""
    AccountHasCancelledLicense      = 115
    """The user has a user cancelled license."""
    DeniedDueToCommunityCooldown    = 116
    """The request was denied due to community cooldown."""
    NoLauncherSpecified             = 117
    """No launcher was specified."""
    MustAgreeToSSA                  = 118
    """User must agree to China SSA or global SSA before login."""
    LauncherMigrated                = 119
    """The specified launcher type is no longer supported."""
    SteamRealmMismatch              = 120
    """The user's realm does not match the realm of the requested resource."""
    InvalidSignature                = 121
    """Signature check did not match."""
    ParseFailure                    = 122
    """Failed to parse input."""
    NoVerifiedPhone                 = 123
    """Account does not have a verified phone number."""
    InsufficientBatteryCharge       = 124
    """The device battery is too low to complete the action."""


class Language(IntEnum):
    """The language for a request."""
    NONE                        = -1
    """No language specified."""
    English                     = 0
    """English."""
    German                      = 1
    """German."""
    French                      = 2
    """French."""
    Italian                     = 3
    """Italian."""
    Korean                      = 4
    """Korean."""
    Spanish                     = 5
    """Spanish."""
    SimplifiedChinese           = 6
    """Simplified Chinese."""
    TraditionalChinese          = 7
    """Traditional Chinese."""
    Russian                     = 8
    """Russian."""
    Thai                        = 9
    """Thai."""
    Japanese                    = 10
    """Japanese."""
    Portuguese                  = 11
    """Portuguese."""
    Polish                      = 12
    """Polish."""
    Danish                      = 13
    """Danish."""
    Dutch                       = 14
    """Dutch."""
    Finnish                     = 15
    """Finnish."""
    Norwegian                   = 16
    """Norwegian."""
    Swedish                     = 17
    """Swedish."""
    Romanian                    = 18
    """Romanian."""
    Turkish                     = 19
    """Turkish."""
    Hungarian                   = 20
    """Hungarian."""
    Czech                       = 21
    """Czech."""
    PortugueseBrazil            = 22
    """Brazilian Portuguese."""
    Bulgarian                   = 23
    """Bulgarian."""
    Greek                       = 24
    """Greek."""
    Arabic                      = 25
    """Arabic."""
    Ukrainian                   = 26
    """Ukrainian."""
    SpanishLatinAmerican        = 27
    """Latin American Spanish."""
    Vietnamese                  = 28
    """Vietnamese."""
    # SteamChinaSimplifiedChinese = 29  # not including until this appears on Steamworks

    @classproperty
    def NATIVE_NAME_MAP(cls: type[Language]) -> Mapping[Language, str]:  # type: ignore
        """A mapping of every language's native name."""
        return {
            cls.Arabic:               "العربية",
            cls.Bulgarian:            "езбългарски езикик",
            cls.SimplifiedChinese:    "简体中文",
            cls.TraditionalChinese:   "繁體中文",
            cls.Czech:                "čeština",
            cls.Danish:               "Dansk",
            cls.Dutch:                "Nederlands",
            cls.English:              "English",
            cls.Finnish:              "Suomi",
            cls.French:               "Français",
            cls.German:               "Deutsch",
            cls.Greek:                "Ελληνικά",
            cls.Hungarian:            "Magyar",
            cls.Italian:              "Italiano",
            cls.Japanese:             "日本語",
            cls.Korean:               "한국어",
            cls.Norwegian:            "Norsk",
            cls.Polish:               "Polski",
            cls.Portuguese:           "Português",
            cls.PortugueseBrazil:     "Português-Brasil",
            cls.Romanian:             "Română",
            cls.Russian:              "Русский",
            cls.Spanish:              "Español-España",
            cls.SpanishLatinAmerican: "Español-Latinoamérica",
            cls.Swedish:              "Svenska",
            cls.Thai:                 "ไทย",
            cls.Turkish:              "Türkçe",
            cls.Ukrainian:            "Українська",
            cls.Vietnamese:           "Tiếng Việt",
        }

    @classproperty
    def API_LANGUAGE_MAP(cls: type[Language]) -> Mapping[Language, str]:  # type: ignore
        """A mapping of every language's name from the Steamworks API."""
        return {
            cls.Arabic:               "arabic",
            cls.Bulgarian:            "bulgarian",
            cls.SimplifiedChinese:    "schinese",
            cls.TraditionalChinese:   "tchinese",
            cls.Czech:                "czech",
            cls.Danish:               "danish",
            cls.Dutch:                "dutch",
            cls.English:              "english",
            cls.Finnish:              "finnish",
            cls.French:               "french",
            cls.German:               "german",
            cls.Greek:                "greek",
            cls.Hungarian:            "hungarian",
            cls.Italian:              "italian",
            cls.Japanese:             "japanese",
            cls.Korean:               "koreana",
            cls.Norwegian:            "norwegian",
            cls.Polish:               "polish",
            cls.Portuguese:           "portuguese",
            cls.PortugueseBrazil:     "brazilian",
            cls.Romanian:             "romanian",
            cls.Russian:              "russian",
            cls.Spanish:              "spanish",
            cls.SpanishLatinAmerican: "latam",
            cls.Swedish:              "swedish",
            cls.Thai:                 "thai",
            cls.Turkish:              "turkish",
            cls.Ukrainian:            "ukrainian",
            cls.Vietnamese:           "vietnamese",
        }

    @classproperty
    def WEB_API_MAP(cls: type[Language]) -> Mapping[Language, str]:  # type: ignore
        """A mapping of every language's name from the Web API."""
        return {
            cls.Arabic:               "ar",
            cls.Bulgarian:            "bg",
            cls.SimplifiedChinese:    "zh-CN",
            cls.TraditionalChinese:   "zh-TW",
            cls.Czech:                "cs",
            cls.Danish:               "da",
            cls.Dutch:                "nl",
            cls.English:              "en",
            cls.Finnish:              "fi",
            cls.French:               "fr",
            cls.German:               "de",
            cls.Greek:                "el",
            cls.Hungarian:            "hu",
            cls.Italian:              "it",
            cls.Japanese:             "ja",
            cls.Korean:               "ko",
            cls.Norwegian:            "no",
            cls.Polish:               "pl",
            cls.Portuguese:           "pt",
            cls.PortugueseBrazil:     "pt-BR",
            cls.Romanian:             "ro",
            cls.Russian:              "ru",
            cls.Spanish:              "es",
            cls.SpanishLatinAmerican: "es-419",
            cls.Swedish:              "sv",
            cls.Thai:                 "th",
            cls.Turkish:              "tr",
            cls.Ukrainian:            "uk",
            cls.Vietnamese:           "vn",
        }

    @property
    def native_name(self) -> str:
        """This language's native name."""
        return self.NATIVE_NAME_MAP[self]

    @property
    def api_name(self) -> str:
        """This language's Steamworks name."""
        return self.API_LANGUAGE_MAP[self]

    @property
    def web_api_name(self) -> str:
        """This language's Web API name."""
        return self.WEB_API_MAP[self]

    @classmethod
    def from_str(cls, string: str, /) -> Language:
        try:
            return _REVERSE_API_LANGUAGE_MAP[string.lower()]
        except KeyError:
            return cls._new_member(name=string.title(), value=hash(string.title()))

    @classmethod
    def from_web_api_str(cls, string: str, /) -> Language:
        try:
            return _REVERSE_WEB_API_MAP[string]
        except KeyError:
            return cls._new_member(name=string, value=hash(string))


_REVERSE_API_LANGUAGE_MAP: Final = cast(
    Mapping[str, Language], {value: key for key, value in Language.API_LANGUAGE_MAP.items()}
)
_REVERSE_WEB_API_MAP: Final = cast(
    Mapping[str, Language], {value: key for key, value in Language.WEB_API_MAP.items()}
)


class Currency(IntEnum):
    """All currencies currently supported by Steam."""
    USD = 1
    """The United States Dollar."""
    GBP = 2
    """The British Pound."""
    EUR = 3
    """The Euro."""
    CHF = 4
    """The Swiss Franc."""
    RUB = 5
    """The Russian Ruble."""
    PLN = 6
    """The Polish Zloty."""
    BRL = 7
    """The Brazilian Real."""
    JPY = 8
    """The Japanese Yen."""
    NOK = 9
    """The Norwegian Krone."""
    IDR = 10
    """The Indonesian Rupiah."""
    MYR = 11
    """The Malaysian Ringgit."""
    PHP = 12
    """The Philippine Peso."""
    SGD = 13
    """The Singapore Dollar."""
    THB = 14
    """The Thai Baht."""
    VND = 15
    """The Vietnamese Dong."""
    KRW = 16
    """The South Korean Won."""
    TRY = 17
    """The Turkish Lira."""
    UAH = 18
    """The Ukrainian Hryvnia."""
    MXN = 19
    """The Mexican Peso."""
    CAD = 20
    """The Canadian Dollar."""
    AUD = 21
    """The Australian Dollar."""
    NZD = 22
    """The New Zealand Dollar."""
    CNY = 23
    """The Chinese Yuan."""
    INR = 24
    """The Indian Rupee."""
    CLP = 25
    """The Chilean Peso."""
    PEN = 26
    """The Peruvian Sol."""
    COP = 27
    """The Columbian Peso."""
    ZAR = 28
    """The South African Rand."""
    HKD = 29
    """The Hong Kong Dollar."""
    TWD = 30
    """The Taiwanese New Taiwan Dollar."""
    SAR = 31
    """The Saudi Arabian Saudi Riyal."""
    AED = 32
    """The United Arab Emirates Dirham."""
    SEK = 33
    """The Swedish Krona."""
    ARS = 34
    """The Argentinian Argentine Peso."""
    ILS = 35
    """The Israeli New Shekel."""
    BYN = 36
    """The Belarusian Ruble."""
    KZT = 37
    """The Kazakhstani Tenge."""
    KWD = 38
    """The Kuwaiti Dinar."""
    QAR = 39
    """The Qatari Riyal."""
    CRC = 40
    """The Costa Rican Colón."""
    UYU = 41
    """The Uruguayan Peso."""
    BGN = 42
    """The Bulgarian Lev."""
    HRK = 43
    """The Croatian Kuna."""
    CZK = 44
    """The Czech Koruna."""
    DKK = 45
    """The Danish Krone."""
    HUF = 46
    """The Hungarian Forint."""
    RON = 47
    """The Romanian Leu."""

    @classmethod
    def try_name(cls, name: str, /) -> Self:
        try:
            return cls._member_map_[name]
        except (KeyError, TypeError):
            return cls._new_member(name=name, value=hash(name))


class Realm(IntEnum):
    Unknown = 0
    """Unknown."""
    Global  = 1
    """Global realm."""
    China   = 2
    """China realm."""


class PurchaseResult(IntEnum):
    NoDetail = 0
    AVSFailure = 1
    InsufficientFunds = 2
    ContactSupport = 3
    Timeout = 4
    InvalidPackage = 5
    InvalidPaymentMethod = 6
    InvalidData = 7
    OthersInProgress = 8
    AlreadyPurchased = 9
    WrongPrice = 10
    FraudCheckFailed = 11
    CancelledByUser = 12
    RestrictedCountry = 13
    BadActivationCode = 14
    DuplicateActivationCode = 15
    UseOtherPaymentMethod = 16
    UseOtherFunctionSource = 17
    InvalidShippingAddress = 18
    RegionNotSupported = 19
    AcctIsBlocked = 20
    AcctNotVerified = 21
    InvalidAccount = 22
    StoreBillingCountryMismatch = 23
    DoesNotOwnRequiredApp = 24
    CanceledByNewTransaction = 25
    ForceCanceledPending = 26
    FailCurrencyTransProvider = 27
    FailedCyberCafe = 28
    NeedsPreApproval = 29
    PreApprovalDenied = 30
    WalletCurrencyMismatch = 31
    EmailNotValidated = 32
    ExpiredCard = 33
    TransactionExpired = 34
    WouldExceedMaxWallet = 35
    MustLoginPS3AppForPurchase = 36
    CannotShipToPOBox = 37
    InsufficientInventory = 38
    CannotGiftShippedGoods = 39
    CannotShipInternationally = 40
    BillingAgreementCancelled = 41
    InvalidCoupon = 42
    ExpiredCoupon = 43
    AccountLocked = 44
    OtherAbortableInProgress = 45
    ExceededSteamLimit = 46
    OverlappingPackagesInCart = 47
    NoWallet = 48
    NoCachedPaymentMethod = 49
    CannotRedeemCodeFromClient = 50
    PurchaseAmountNoSupportedByProvider = 51
    OverlappingPackagesInPendingTransaction = 52
    RateLimited = 53
    OwnsExcludedApp = 54
    CreditCardBinMismatchesType = 55
    CartValueTooHigh = 56
    BillingAgreementAlreadyExists = 57
    POSACodeNotActivated = 58
    CannotShipToCountry = 59
    HungTransactionCancelled = 60
    PaypalInternalError = 61
    UnknownGlobalCollectError = 62
    InvalidTaxAddress = 63
    PhysicalProductLimitExceeded = 64
    PurchaseCannotBeReplayed = 65
    DelayedCompletion = 66
    BundleTypeCannotBeGifted = 67
    BlockedByUSGov = 68
    ItemsReservedForCommercialUse = 69
    GiftAlreadyOwned = 70
    GiftInvalidForRecipientRegion = 71
    GiftPricingImbalance = 72
    GiftRecipientNotSpecified = 73
    ItemsNotAllowedForCommercialUse = 74
    BusinessStoreCountryCodeMismatch = 75
    UserAssociatedWithManyCafes = 76
    UserNotAssociatedWithCafe = 77
    AddressInvalid = 78
    CreditCardNumberInvalid = 79
    CannotShipToMilitaryPostOffice = 80
    BillingNameInvalidResemblesCreditCard = 81
    PaymentMethodTemporarilyUnavailable = 82
    PaymentMethodNotSupportedForProduct = 83


class Universe(IntEnum):
    """Steam universes. Each universe is a self-contained Steam instance."""
    Invalid  = 0
    """Invalid."""
    Public   = 1
    """The standard public universe."""
    Beta     = 2
    """Beta universe used inside Valve."""
    Internal = 3
    """Internal universe used inside Valve."""
    Dev      = 4
    """Dev universe used inside Valve."""


class Type(IntEnum):
    """Steam account types."""
    Invalid        = 0
    """Used for invalid Steam IDs."""
    Individual     = 1
    """Single user account."""
    Multiseat      = 2
    """Multiseat (e.g. cybercafe) account."""
    GameServer     = 3
    """Game server account."""
    AnonGameServer = 4
    """Anonymous game server account."""
    Pending        = 5
    """Pending."""
    ContentServer  = 6
    """Valve internal content server account."""
    Clan           = 7
    """Steam clan."""
    Chat           = 8
    """Steam group chat or lobby."""
    ConsoleUser    = 9
    """Fake SteamID for local PSN account on PS3 or Live account on 360, etc."""
    AnonUser       = 10
    """Anonymous user account. (Used to create an account or reset a password)"""


class TypeChar(IntEnum):
    """Steam account type characters."""
    I = Type.Invalid
    """The character used for :class:`~steam.Type.Invalid`."""
    U = Type.Individual
    """The character used for :class:`~steam.Type.Individual`."""
    M = Type.Multiseat
    """The character used for :class:`~steam.Type.Multiseat`."""
    G = Type.GameServer
    """The character used for :class:`~steam.Type.GameServer`."""
    A = Type.AnonGameServer
    """The character used for :class:`~steam.Type.AnonGameServer`."""
    P = Type.Pending
    """The character used for :class:`~steam.Type.Pending`."""
    C = Type.ContentServer
    """The character used for :class:`~steam.Type.ContentServer`."""
    g = Type.Clan
    """The character used for :class:`~steam.Type.Clan`."""
    T = Type.Chat
    """The character used for :class:`~steam.Type.Chat`."""
    L = Type.Chat
    """The character used for :class:`~steam.Type.Chat` (Chat lobby)."""
    c = Type.Chat
    """The character used for :class:`~steam.Type.Clan` (Chat group)."""
    a = Type.AnonUser
    """The character used for :class:`~steam.Type.AnonUser`."""


class Instance(Flags):
    """Steam account instance flags."""
    All          = 0
    """The Instance for all Steam IDs"""
    Desktop      = 1 << 0
    """The Instance for desktop Steam IDs"""
    Console      = 1 << 1
    """The Instance for console  Steam IDs"""
    Web          = 1 << 2
    """The Instance for web Steam IDs"""
    # I have observed these flags for game servers, but I don't know what they are
    Unknown1     = 1 << 3
    Unknown2     = 1 << 4
    Unknown3     = 1 << 5
    Unknown4     = 1 << 6
    Unknown5     = 1 << 7
    Unknown6     = 1 << 8
    Unknown7     = 1 << 9
    Unknown8     = 1 << 10
    Unknown9     = 1 << 11
    Unknown10    = 1 << 12
    Unknown11    = 1 << 13
    Unknown12    = 1 << 14
    # Unknown13    = 1 << 15
    # Unknown14    = 1 << 16
    # 20474 ->   | 2 |   | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048 | 16384
    # 20475 -> 1 | 2 |   | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048 | 16384
    # 20476 ->   |   | 4 | 8 | 16 | 32 | 64 | 128 | 256 | 512 | 1024 | 2048 | 16384
    # Type.Chat exclusive flags
    ChatMMSLobby = 1 << 17
    """The Steam ID is for an MMS Lobby."""
    ChatLobby    = 1 << 18
    """The Steam ID is for a Lobby."""
    ChatClan     = 1 << 19
    """The Steam ID is for a Clan."""


class FriendRelationship(IntEnum):
    """The relationship between a user and another user."""
    NONE             = 0
    """The user has no relationship to you."""
    Blocked          = 1
    """The user has been blocked."""
    RequestRecipient = 2
    """The user has requested to be friends with you."""
    Friend           = 3
    """The user is friends with you."""
    RequestInitiator = 4
    """You have requested to be friends with the user."""
    Ignored          = 5
    """You have explicitly blocked this other user from comments/chat/etc."""
    IgnoredFriend    = 6
    """The user has ignored the current user."""


class PersonaState(IntEnum):
    """The status of a user."""
    Offline        = 0
    """The user is not currently logged on."""
    Online         = 1
    """The user is logged on."""
    Busy           = 2
    """The user is on, but busy."""
    Away           = 3
    """The user has been marked as AFK for a short period of time."""
    Snooze         = 4
    """The user has been marked as AFK for a long period of time."""
    LookingToTrade = 5
    """The user is online and wanting to trade."""
    LookingToPlay  = 6
    """The user is online and wanting to play."""
    Invisible      = 7
    """The user is invisible."""


class PersonaStateFlag(Flags):
    """The persona state flags for a user."""
    NONE                 = 0
    """The user has no persona state flags."""
    HasRichPresence      = 1 << 0
    """The user has a rich presence string."""
    InJoinableGame       = 1 << 1
    """The user is in a game and the game has a joinable lobby."""
    Golden               = 1 << 2
    """The user has a golden username and "avatar frame" (this was before avatar frames)."""
    RemotePlayTogether   = 1 << 3
    """The user is playing a game that supports remote play together."""
    ClientTypeWeb        = 1 << 4
    """The user is using the Steam Web App."""
    ClientTypeMobile     = 1 << 8
    """The user is using the Steam Mobile App."""
    ClientTypeTenfoot    = 1 << 10
    """The user is using Steam Big Picture."""
    ClientTypeVR         = 1 << 11
    """The user is using the Steam VR App."""
    LaunchTypeGamepad    = 1 << 12
    """The user is using a gamepad."""
    LaunchTypeCompatTool = 1 << 13
    """The user is using a compatibility tool."""


class CommunityVisibilityState(IntEnum):
    """The visibility of a user's community profile."""
    NONE        = 0
    """The user has no community state."""
    Private     = 1
    """The user has a private profile."""
    FriendsOnly = 2
    """The user has a friends only profile."""
    Public      = 3
    """The user has a public profile."""


class TradeOfferState(IntEnum):
    """The state of a trade offer."""
    Invalid                   = 1
    """The trade offer's state is invalid."""
    Active                    = 2
    """The trade offer is active."""
    Accepted                  = 3
    """The trade offer has been accepted."""
    Countered                 = 4
    """The trade offer has been countered."""
    Expired                   = 5
    """The trade offer has expired."""
    Canceled                  = 6
    """The trade offer has been cancelled."""
    Declined                  = 7
    """The trade offer has be declined by the partner."""
    InvalidItems              = 8
    """The trade offer has invalid items and has been cancelled."""
    ConfirmationNeed          = 9
    """The trade offer needs confirmation."""
    CanceledBySecondaryFactor = 10
    """The trade offer was cancelled by second factor."""
    StateInEscrow             = 11
    """The trade offer is in escrow."""


class ChatMemberRank(IntEnum):
    """The rank of a chat member."""
    Default = 0
    """Default rank for a chat member."""
    Viewer = 10
    """Viewer rank for a chat member."""
    Guest = 15
    """Guest rank for a chat member."""
    Member = 20
    """Member rank for a chat member."""
    Moderator = 30
    """Moderator rank for a chat member."""
    Officer = 40
    """Officer rank for a chat member."""
    Owner = 50
    """Owner rank for a chat member."""

class ChatMemberJoinState(IntEnum):
    """The join state of a chat member."""
    Default = 0
    NONE = 1
    Joined = 2


class ChatEntryType(IntEnum):
    """The type of chat entry."""
    Invalid          = 0
    """An Invalid Chat entry."""
    Text             = 1
    """A Normal text message from another user."""
    Typing           = 2
    """Another user is typing (not used in multi-user chat)."""
    InviteGame       = 3
    """An Invite from other user into that users current game."""
    LeftConversation = 6
    """A user has left the conversation."""
    Entered          = 7
    """A user has entered the conversation (used in multi-user chat and group chat)."""
    WasKicked        = 8
    """A user was kicked."""
    WasBanned        = 9
    """A user was banned."""
    Disconnected     = 10
    """A user disconnected."""
    HistoricalChat   = 11
    """A chat message from user's chat history or offline message."""
    LinkBlocked      = 14
    """A link was removed by the chat filter."""


class ClanAccountFlags(Flags):
    """Represents """
    Public   = 1 << 0
    """A public clan."""
    Large    = 1 << 1
    """A large clan."""
    Locked   = 1 << 2
    """The clan is locked."""
    Disabled = 1 << 3
    """The clan is disabled."""
    OGG      = 1 << 4
    """An "Official Game Group" (an app clan)."""


class UIMode(IntEnum):
    """The UI mode for a client."""
    Desktop    = 0
    """The UI mode for the desktop client."""
    BigPicture = 1
    """The UI mode for big picture mode."""
    Mobile     = 2
    """The UI mode for mobile."""
    Web        = 3
    """The UI mode for the web client."""


class ReviewType(IntEnum):
    """The type of review."""
    NONE                   = 0
    """No reviews."""
    OverwhelminglyNegative = 1
    """0 - 19% positive reviews and few of them."""
    VeryNegative           = 2
    """0 - 19% positive reviews."""
    Negative               = 3
    """0 - 39% positive reviews."""
    MostlyNegative         = 4
    """20 - 39% positive reviews but few of them."""
    Mixed                  = 5
    """40 - 69% positive reviews."""
    MostlyPositive         = 6
    """70 - 79% positive reviews."""
    Positive               = 7
    """80 - 100% positive reviews but few of them."""
    VeryPositive           = 8
    """94 - 80% positive reviews."""
    OverwhelminglyPositive = 9
    """95 - 100% positive reviews."""


class GameServerRegion(IntEnum):
    """The region of a game server."""
    NONE         = -1
    """No set game region."""
    USEastCoast  = 0
    """A server on the USA's East Coast."""
    USWestCoast  = 1
    """A server on the USA's West Coast."""
    SouthAmerica = 2
    """A server in South America."""
    Europe       = 3
    """A server in Europe."""
    Asia         = 4
    """A server in Asia."""
    Australia    = 5
    """A server in Australia."""
    MiddleEast   = 6
    """A server in the Middle East."""
    Africa       = 7
    """A server in Africa."""
    World        = 255
    """A server somewhere in the world."""


class EventType(IntEnum):
    """The type of an event."""
    Other                  = 1
    """An unspecified event."""
    Game                   = 2
    """A game event."""
    Party                  = 3
    """A party event."""
    Meeting                = 4
    """An important meeting."""
    SpecialCause           = 5
    """An event for a special cause."""
    MusicAndArts           = 6
    """A music or art event."""
    Sports                 = 7
    """A sporting event."""
    Trip                   = 8
    """A clan trip."""
    Chat                   = 9
    """A chat event."""
    GameRelease            = 10
    """A game release event."""
    Broadcast              = 11
    """A broadcast event."""
    SmallUpdate            = 12
    """A small update event."""
    PreAnnounceMajorUpdate = 13
    """A pre-announcement for a major update event."""
    MajorUpdate            = 14
    """A major update event."""
    DLCRelease             = 15
    """A dlc release event."""
    FutureRelease          = 16
    """A future release event."""
    ESportTournamentStream = 17
    """An e-sport tournament stream event."""
    DevStream              = 18
    """A developer stream event."""
    FamousStream           = 19
    """A famous stream event."""
    GameSales              = 20
    """A game sales event."""
    GameItemSales          = 21
    """A game item sales event."""
    InGameBonusXP          = 22
    """An in game bonus xp event."""
    InGameLoot             = 23
    """An in game loot event."""
    InGamePerks            = 24
    """An in game perks event."""
    InGameChallenge        = 25
    """An in game challenge event."""
    InGameContest          = 26
    """An in game contest event."""
    IRL                    = 27
    """An in real life event."""
    News                   = 28
    """A news event."""
    BetaRelease            = 29
    """A beta release event."""
    InGameContentRelease   = 30
    """An in game content release event."""
    FreeTrial              = 31
    """A free trial event."""
    SeasonRelease          = 32
    """A season release event."""
    SeasonUpdate           = 33
    """A season update event."""
    Crosspost              = 34
    """A cross post event."""
    InGameGeneral          = 35
    """An in game general event."""


class ProfileItemType(IntEnum):
    """The type of profile item."""
    Invalid                   = 0
    """An invalid item type."""
    RareAchievementShowcase   = 1
    """A rare achievements showcase."""
    GameCollector             = 2
    """A game collector section."""
    ItemShowcase              = 3
    """An item showcase."""
    TradeShowcase             = 4
    """A trade info showcase."""
    Badges                    = 5
    """A badges showcase."""
    FavouriteGame             = 6
    """A favourite game section."""
    ScreenshotShowcase        = 7
    """A screenshot showcase."""
    CustomText                = 8
    """A custom text section."""
    FavouriteGroup            = 9
    """A favourite game showcase."""
    Recommendation            = 10
    """A review showcase."""
    WorkshopItem              = 11
    """A workshop item showcase."""
    MyWorkshop                = 12
    """A showcase of a workshop item made by profile's owner."""
    ArtworkShowcase           = 13
    """An artwork showcase."""
    VideoShowcase             = 14
    """A video showcase."""
    Guides                    = 15
    """A guide showcase."""
    MyGuides                  = 16
    """A showcase of the profile's owner's guides."""
    Achievements              = 17
    """The owner's profile's achievements."""
    Greenlight                = 18
    """A greenlight showcase."""
    MyGreenlight              = 19
    """A showcase of a greenlight game the profiles' owner has made."""
    Salien                    = 20
    """A salien showcase."""
    LoyaltyRewardReactions    = 21
    """A loyalty reward showcase."""
    SingleArtworkShowcase     = 22
    """A single artwork showcase."""
    AchievementsCompletionist = 23
    """An achievements completeionist showcase."""
    Replay = 24
    """A Steam Replay showcase."""


class ProfileCustomisationStyle(IntEnum):
    Default      = 0
    Selected     = 1
    Rarest       = 2
    MostRecent   = 3
    Random       = 4
    HighestRated = 5


class CommunityItemClass(IntEnum):
    """An item class."""
    Invalid               = 0
    """An invalid item class."""
    Badge                 = 1
    """A badge."""
    GameCard              = 2
    """A game card."""
    ProfileBackground     = 3
    """A profile background."""
    Emoticon              = 4
    """An emoticon."""
    BoosterPack           = 5
    """A booster pack."""
    Consumable            = 6
    """A consumable."""
    GameGoo               = 7
    """Game goo."""
    ProfileModifier       = 8
    """A profile modifier."""
    Scene                 = 9
    """A scene."""
    SalienItem            = 10
    """A salien item."""
    Sticker               = 11
    """A sticker."""
    ChatEffect            = 12
    """A chat effect."""
    MiniProfileBackground = 13
    """A mini profile background."""
    AvatarFrame           = 14
    """An avatar frame."""
    AnimatedAvatar        = 15
    """An animated avatar."""
    SteamDeckKeyboardSkin = 16
    """A Steam Deck keyboard skin."""


class ProfileItemEquippedFlag(Flags):
    """Flags for a profile item."""
    FullScreen = 1
    """The item is equipped in full screen mode."""


class DepotFileFlag(Flags):
    """Flags for a depot file."""
    File                = 0
    """A file."""
    UserConfig          = 1 << 0
    """A user configuration file."""
    VersionedUserConfig = 1 << 1
    """A versioned user configuration file."""
    Encrypted           = 1 << 2
    """An encrypted file."""
    ReadOnly            = 1 << 3
    """A read only file."""
    Hidden              = 1 << 4
    """A hidden file."""
    Executable          = 1 << 5
    """An executable file."""
    Directory           = 1 << 6
    """A directory."""
    CustomExecutable    = 1 << 7
    """A custom executable file."""
    InstallScript       = 1 << 8
    """An install script file."""
    Symlink             = 1 << 9
    """A symlink file."""


TYPE_TRANSFORM_MAP: Final = cast(Mapping[str, str], {
    "Dlc": "DLC",
})


class AppType(Flags):
    """App type."""
    Game        = 1 << 0
    """A playable game, default type."""
    Application = 1 << 1
    """A software application."""
    Tool        = 1 << 2
    """An SDK, editor or dedicated server."""
    Demo        = 1 << 3
    """A game demo."""
    DLC         = 1 << 5
    """A piece of downloadable content."""
    Guide       = 1 << 6
    """A game guide or PDF etc."""
    Driver      = 1 << 7
    """A hardware driver updater (ATI, Razor etc.)"""
    Config      = 1 << 8
    """A hidden app used to config Steam features (backpack, sales, etc.)."""
    Hardware    = 1 << 9
    """A hardware device (Steam Machine, Steam Controller, Steam Link, etc.)."""
    Franchise   = 1 << 10
    """A hub for collections of multiple apps, e.g. films, series, games.."""
    Video       = 1 << 11
    """A video component of either a Film or TVSeries (may be the feature, an episode, preview, making-of, etc.)"""
    Plugin      = 1 << 12
    """A plug-in type for another App."""
    Music       = 1 << 13
    """A piece of music."""
    Series      = 1 << 14
    """A container app for video series."""
    Comic       = 1 << 15
    """A comic."""
    Beta        = 1 << 16
    """A beta for a game."""
    Media = 1 << 17
    """Legacy Media"""

    Shortcut    = 1 << 30
    """A shortcut to another app, client side only."""
    DepotOnly   = -1 << 31
    """A placeholder since depots and apps share the same namespace."""

    @classmethod
    def from_str(cls, name: str, /) -> AppType:
        types = iter(name.split(","))
        type = next(types).strip().title()
        self = cls[TYPE_TRANSFORM_MAP.get(type, type)]
        for type in types:
            type = type.strip().title()
            self |= cls[TYPE_TRANSFORM_MAP.get(type, type)]
        return self


class LicenseFlag(Flags):
    """Flags for a license."""
    NONE                         = 0
    """No flags."""
    Renew                        = 1 << 0
    """License needs renewing."""
    RenewalFailed                = 1 << 1
    """License renewal failed."""
    Pending                      = 1 << 2
    """Owns license, but transaction is still pending. Can't install or play yet."""
    Expired                      = 1 << 3
    """License is expired."""
    CancelledByUser              = 1 << 4
    """License is cancelled by user."""
    CancelledByAdmin             = 1 << 5
    """License is cancelled by an admin."""
    LowViolenceContent           = 1 << 6
    """License is only for a low violence version."""
    ImportedFromSteam2           = 1 << 7
    """License was imported from Steam 2."""
    ForceRunRestriction          = 1 << 8
    """License has a force run restriction."""
    RegionRestrictionExpired     = 1 << 9
    """License has a region restriction that has expired."""
    CancelledByFriendlyFraudLock = 1 << 10
    """License is cancelled by a friendly fraud lock."""
    NotActivated                 = 1 << 11
    """License is not activated."""


class LicenseType(IntEnum):
    """Types of licenses."""
    NoLicense                             = 0
    """No license."""
    SinglePurchase                        = 1
    """A single purchase license."""
    SinglePurchaseLimitedUse              = 2
    """A single purchase limited use license."""
    RecurringCharge                       = 3
    """A subscription based license."""
    RecurringChargeLimitedUse             = 4
    """A subscription based limited use license."""
    RecurringChargeLimitedUseWithOverAges = 5
    """A subscription based limited use license with over ages."""
    RecurringOption                       = 6
    """A subscription based option license."""
    LimitedUseDelayedActivation           = 7
    """A limited use delayed activation license."""


class BillingType(IntEnum):
    """Types of billing ."""
    NoCost                 = 0
    """No cost."""
    BillOnceOnly           = 1
    """Bill once only."""
    BillMonthly            = 2
    """Bill monthly."""
    ProofOfPrepurchaseOnly = 3
    """Proof of pre-purchase only."""
    GuestPass              = 4
    """Guest pass."""
    HardwarePromo          = 5
    """Hardware promotion."""
    Gift                   = 6
    """Gift."""
    AutoGrant              = 7
    """Automatic grant."""
    OEMTicket              = 8
    """Original Equipment Manufacturer ticket."""
    RecurringOption        = 9
    """Recurring option."""
    BillOnceOrCDKey        = 10
    """Bill once or CD key."""
    Repurchasable          = 11
    """Re-purchasable."""
    FreeOnDemand           = 12
    """Free on demand."""
    Rental                 = 13
    """Rental."""
    CommercialLicense      = 14
    """Commercial license."""
    FreeCommercialLicense  = 15
    """Free commercial license."""
    NumBillingTypes        = 16
    """Number of billing types."""


class PaymentMethod(IntEnum):
    """The payment method used for a purchase."""
    NONE                   = 0
    """No payment method."""
    ActivationCode         = 1
    """Activation code."""
    CreditCard             = 2
    """Credit card."""
    Giropay                = 3
    """Giropay."""
    PayPal                 = 4
    """PayPal."""
    Ideal                  = 5
    """iDEAL."""
    PaySafeCard            = 6
    """PaySafeCard."""
    Sofort                 = 7
    """Sofort."""
    GuestPass              = 8
    """Guest pass."""
    WebMoney               = 9
    """WebMoney."""
    MoneyBookers           = 10
    """MoneyBookers."""
    AliPay                 = 11
    """AliPay."""
    Yandex                 = 12
    """Yandex."""
    Kiosk                  = 13
    """Kiosk."""
    Qiwi                   = 14
    """Qiwi."""
    GameStop               = 15
    """GameStop."""
    HardwarePromo          = 16
    """Hardware promotion."""
    MoPay                  = 17
    """MoPay."""
    BoletoBancario         = 18
    """Boleto Bancario."""
    BoaCompraGold          = 19
    """BoaCompra Gold."""
    BancoDoBrasilOnline    = 20
    """Banco do Brasil Online."""
    ItauOnline             = 21
    """Itau Online."""
    BradescoOnline         = 22
    """Bradesco Online."""
    Pagseguro              = 23
    """Pagseguro."""
    VisaBrazil             = 24
    """Visa Brazil."""
    AmexBrazil             = 25
    """American Express Brazil."""
    Aura                   = 26
    """Aura."""
    Hipercard              = 27
    """Hipercard."""
    MastercardBrazil       = 28
    """Mastercard Brazil."""
    DinersCardBrazil       = 29
    """Diners Card Brazil."""
    AuthorizedDevice       = 30
    """Authorized device."""
    MOLPoints              = 31
    """MOLPoints."""
    ClickAndBuy            = 32
    """Click and Buy."""
    Beeline                = 33
    """Beeline."""
    Konbini                = 34
    """Konbini."""
    EClubPoints            = 35
    """E-Club Points."""
    CreditCardJapan        = 36
    """Credit card Japan."""
    BankTransferJapan      = 37
    """Bank transfer Japan."""
    PayEasy                = 38
    """PayEasy."""
    Zong                   = 39
    """Zong."""
    CultureVoucher         = 40
    """Culture voucher."""
    BookVoucher            = 41
    """Book voucher."""
    HappymoneyVoucher      = 42
    """Happy money voucher."""
    ConvenientStoreVoucher = 43
    """Convenient store voucher."""
    GameVoucher            = 44
    """Game voucher."""
    Multibanco             = 45
    """Multibanco."""
    Payshop                = 46
    """Payshop."""
    MaestroBoaCompra       = 47
    """Maestro BoaCompra."""
    OXXO                   = 48
    """OXXO."""
    ToditoCash             = 49
    """Todito Cash."""
    Carnet                 = 50
    """Carnet."""
    SPEI                   = 51
    """SPEI."""
    ThreePay               = 52
    """Three Pay."""
    IsBank                 = 53
    """Is Bank."""
    Garanti                = 54
    """Garanti."""
    Akbank                 = 55
    """Akbank."""
    YapiKredi              = 56
    """Yapi"""
    Halkbank               = 57
    """Halkbank."""
    BankAsya               = 58
    """Bank Asya."""
    Finansbank             = 59
    """Finansbank."""
    DenizBank              = 60
    """DenizBank."""
    PTT                    = 61
    """PTT."""
    CashU                  = 62
    """CashU."""
    AutoGrant              = 64
    """Automatic grant."""
    WebMoneyJapan          = 65
    """WebMoney Japan."""
    OneCard                = 66
    """OneCard."""
    PSE                    = 67
    """PSE."""
    Exito                  = 68
    """Exito."""
    Efecty                 = 69
    """Efecty."""
    Paloto                 = 70
    """Paloto."""
    PinValidda             = 71
    """Pin Validda."""
    MangirKart             = 72
    """Mangir Kart."""
    BancoCreditoDePeru     = 73
    """Banco Credito de Peru."""
    BBVAContinental        = 74
    """BBVA Continental."""
    SafetyPay              = 75
    """SafetyPay."""
    PagoEfectivo           = 76
    """Pago Efectivo."""
    Trustly                = 77
    """Trustly."""
    UnionPay               = 78
    """UnionPay."""
    BitCoin                = 79
    """BitCoin."""
    Wallet                 = 128
    """Wallet."""
    Valve                  = 129
    """Valve."""
    MasterComp             = 130
    """Master Comp."""
    Promotional            = 131
    """Promotional."""
    MasterSubscription     = 134
    """Master Subscription."""
    Payco                  = 135
    """Payco."""
    MobileWalletJapan      = 136
    """Mobile Wallet Japan."""
    OEMTicket              = 256
    """Original Equipment Manufacturer Ticket."""
    Split                  = 512
    """Split."""
    Complimentary          = 1024
    """Complimentary."""


class PackageStatus(IntEnum):
    """Package status."""
    Available   = 0
    """Available."""
    Preorder    = 1
    """Pre-order."""
    Unavailable = 2
    """Unavailable."""
    Invalid     = 3
    """Invalid."""


class PublishedFileRevision(IntEnum):
    """Published file revisions."""
    Default               = 0
    """The default revision."""
    Latest                = 1
    """The latest revision."""
    ApprovedSnapshot      = 2
    """The approved snapshot."""
    ApprovedSnapshotChina = 3
    """The approved snapshot for China."""
    RejectedSnapshot      = 4
    """The rejected snapshot."""
    RejectedSnapshotChina = 5
    """The rejected snapshot for China."""


class PublishedFileQueryType(IntEnum):
    """Ways you can query for UGC items (published files)."""
    RankedByVote                                  = 0
    """Ranked by vote."""
    RankedByPublicationDate                       = 1
    """Ranked by publication date."""
    AcceptedForGameRankedByAcceptanceDate         = 2
    """Accepted for game ranked by acceptance date."""
    RankedByTrend                                 = 3
    """Ranked by trend."""
    FavouritedByFriendsRankedByPublicationDate    = 4
    """Favourited by friends ranked by publication date."""
    CreatedByFriendsRankedByPublicationDate       = 5
    """Created by friends ranked by publication date."""
    RankedByNumTimesReported                      = 6
    """Ranked by number of times reported."""
    CreatedByFollowedUsersRankedByPublicationDate = 7
    """Created by followed users ranked by publication date."""
    NotYetRated                                   = 8
    """Not yet rated."""
    RankedByTotalUniqueSubscriptions              = 9
    """Ranked by total unique subscriptions."""
    RankedByTotalVotesAsc                         = 10
    """Ranked by total votes ascending."""
    RankedByVotesUp                               = 11
    """Ranked by votes up."""
    RankedByTextSearch                            = 12
    """Ranked by text search."""
    RankedByPlaytimeTrend                         = 13
    """Ranked by playtime trend."""
    RankedByTotalPlaytime                         = 14
    """Ranked by total playtime."""
    RankedByAveragePlaytimeTrend                  = 15
    """Ranked by average playtime trend."""
    RankedByLifetimeAveragePlaytime               = 16
    """Ranked by lifetime average playtime."""
    RankedByPlaytimeSessionsTrend                 = 17
    """Ranked by playtime sessions trend."""
    RankedByLifetimePlaytimeSessions              = 18
    """Ranked by lifetime playtime sessions."""
    RankedByInappropriateContentRating            = 19
    """Ranked by inappropriate content rating."""
    RankedByBanContentCheck                       = 20
    """Ranked by ban content check."""
    RankedByLastUpdatedDate                       = 21
    """Ranked by last updated date."""


class PublishedFileType(IntEnum):
    """Published file types."""
    Community              = 0
    """Normal Workshop item that can be subscribed to"""
    Microtransaction       = 1
    """Workshop item that is meant to be voted on for the purpose of selling in-game"""
    Collection             = 2
    """A collection of Workshop or Greenlight items"""
    Art                    = 3
    """Artwork"""
    Video                  = 4
    """External video"""
    Screenshot             = 5
    """Screenshot"""
    Game                   = 6
    """Greenlight game entry"""
    Software               = 7
    """Greenlight software entry"""
    Concept                = 8
    """Greenlight concept"""
    WebGuide               = 9
    """Steam web guide"""
    IntegratedGuide        = 10
    """Application integrated guide"""
    Merch                  = 11
    """Workshop merchandise meant to be voted on for the purpose of being sold"""
    ControllerBinding      = 12
    """Steam Controller bindings"""
    SteamworksAccessInvite = 13
    """Internal"""
    SteamVideo             = 14
    """Steam video"""
    GameManagedItem        = 15
    """Managed completely by the game, not the user, and not shown on the web"""


class PublishedFileVisibility(IntEnum):
    """Published file visibility."""
    Public      = 0
    """Public."""
    FriendsOnly = 1
    """Friends only."""
    Private     = 2
    """Private."""
    Unlisted    = 3
    """Unlisted."""


class PublishedFileQueryFileType(IntEnum):
    """The way that a shared file can be queried by QueryFile."""
    Items                   = 0
    """Items."""
    Collections             = 1
    """A collection of Workshop items."""
    Art                     = 2
    """Artwork."""
    Videos                  = 3
    """Videos."""
    Screenshots             = 4
    """Screenshots."""
    CollectionEligible      = 5
    """Items that can be put inside a collection."""
    Games                   = 6
    """Unused."""
    Software                = 7
    """Unused."""
    Concepts                = 8
    """Unused."""
    GreenlightItems         = 9
    """Unused."""
    AllGuides               = 10
    """Guides."""
    WebGuides               = 11
    """Steam web guide."""
    IntegratedGuides        = 12
    """Application integrated guide."""
    UsableInGame            = 13
    """Workshop items that can be used right away by the user."""
    Merch                   = 14
    """Workshop merchandise meant to be voted on for the purpose of being sold."""
    ControllerBindings      = 15
    """Steam Controller bindings."""
    SteamworksAccessInvites = 16
    """Used internally."""
    ForSaleInGame           = 17
    """Workshop items that can be sold in-game."""
    ReadyToUseItems         = 18
    """Workshop items that can be used right away by the user."""
    WorkshopShowcases       = 19
    """Workshop showcases."""
    GameManagedItems        = 20
    """Managed completely by the game, not the user, and not shown on the web."""


class LeaderboardDataRequest(IntEnum):
    """The way that a leaderboard can be queried."""
    Global = 0
    """Global leaderboard."""
    GlobalAroundUser = 1
    """Global leaderboard around user."""
    Friends = 2
    """Friends leaderboard."""
    Users = 3
    """Users leaderboard."""


class LeaderboardSortMethod(IntEnum):
    """The way that a leaderboard can be sorted."""
    NONE = 0
    """Default sort method."""
    Ascending = 1
    """Ascending sort method."""
    Descending = 2
    """Descending sort method."""


class LeaderboardDisplayType(IntEnum):
    """The way that a leaderboard can be displayed."""
    NONE = 0
    """Default display type."""
    Numeric = 1
    """Numeric display type."""
    TimeSeconds = 2
    """Time in seconds display type."""
    TimeMilliseconds = 3
    """Time in milliseconds display type."""


class LeaderboardUploadScoreMethod(IntEnum):
    """The way that a leaderboard can be uploaded to."""
    NONE = 0
    """Default upload method."""
    KeepBest = 1
    """Keep best upload method."""
    ForceUpdate = 2
    """Force update upload method."""


class CommunityDefinitionItemType(IntEnum):
    """The type of a community item."""
    NONE = 0


class AuthSessionResponse(IntEnum):
    """The response from an app ticket authentication."""
    NotSent                      = -1
    """Not sent. Not a valid response from Steam."""
    OK                           = 0
    UserNotConnectedToSteam      = 1
    NoLicenseOrExpired           = 2
    VACBanned                    = 3
    LoggedInElseWhere            = 4
    VACCheckTimedOut             = 5
    AuthTicketCanceled           = 6
    AuthTicketInvalidAlreadyUsed = 7
    AuthTicketInvalid            = 8
    PublisherIssuedBan           = 9


class ContentDescriptor(IntEnum):
    NudityOrSexualContent = 1
    FrequentNudityOrSexualContent = 1
    FrequentViolenceOrGore = 2
    AdultOnlySexualContent = 3
    StrongSexualContent = 3
    GratuitousSexualContent = 4
    AnyMatureContent = 5


class has_associated_flag(int):
    flag: int
    def __new__(cls, value: int, flag: int) -> Self:
        self = super().__new__(cls, value)
        super().__setattr__(self, "flag", flag)
        return self


class UserNewsType(IntEnum):
    FriendAdded                       = has_associated_flag(1,    1 << 0)
    AchievementUnlocked               = has_associated_flag(2,    1 << 1)
    ReceivedNewGame                   = has_associated_flag(3,    1 << 2)
    JoinedGroup                       = has_associated_flag(4,    1 << 3)
    CommentByMe                       = has_associated_flag(5,    0)
    FriendRemoved                     = has_associated_flag(6,    0)
    GroupCreated                      = has_associated_flag(7,    0)
    CommentOnMe                       = has_associated_flag(8,    0)
    AddedGameToWishlist               = has_associated_flag(9,    1 << 7)
    Review                            = has_associated_flag(10,   1 << 8)
    FilePublishedScreenshot           = has_associated_flag(13,   1 << 9)
    FilePublishedVideo                = has_associated_flag(14,   1 << 10)
    FilePublishedWorkshopItem         = has_associated_flag(15,   1 << 11)
    Post                              = has_associated_flag(16,   1 << 12)
    FilePublishedCollection           = has_associated_flag(17,   1 << 13)
    FilePublishedGreenlightGame       = has_associated_flag(18,   0)
    FilePublishedWorkshopAnnouncement = has_associated_flag(19,   0)
    FilePublishedWebGuide             = has_associated_flag(20,   1 << 13)
    FilePublishedScreenshotTagged     = has_associated_flag(21,   0)
    FilePublishedArt                  = has_associated_flag(22,   1 << 13)
    FileFavourited                    = has_associated_flag(23,   1 << 14)
    PlayedGameFirstTime               = has_associated_flag(30,   1 << 2)

    ClanAchievement                   = has_associated_flag(1001, 1 << 16)
    PostedAnnouncement                = has_associated_flag(1002, 1 << 17)
    ScheduledEvent                    = has_associated_flag(1003, 1 << 18)
    SelectedNewPOTW                   = has_associated_flag(1004, 1 << 19)
    PromotedNewAdmin                  = has_associated_flag(1005, 1 << 20)
    MessageOnClanPage                 = has_associated_flag(1006, 1 << 21)
    CuratorReview                     = has_associated_flag(1007, 1 << 22)

    @property
    def flag(self) -> int:
        return self.value.flag

    def __or__(self, other: SupportsInt) -> Self:
        cls = self.__class__
        value = self.flag | int(other) if not isinstance(other, cls) else self.flag | other.flag
        return cls._new_member(name=f"{self.name} | {getattr(other, 'name', other)}", value=has_associated_flag(-1, value))

    def __and__(self, other: SupportsInt) -> Self:
        cls = self.__class__
        value = self.flag & int(other) if not isinstance(other, cls) else self.flag & other.flag
        return cls._new_member(name=f"{self.name} & {getattr(other, 'name', other)}", value=has_associated_flag(-1, value))

    @classproperty
    def App(cls: type[Self]) -> UserNewsType:  # type: ignore
        """Mimics the Steam Client's feed when an app is selected."""
        return (
            cls.AchievementUnlocked
            | cls.FilePublishedScreenshot
            | cls.FilePublishedVideo
            | cls.Post
            | cls.Review
            | cls.CuratorReview
            | cls.AddedGameToWishlist
            | cls.PlayedGameFirstTime
        )

    @classproperty
    def Friend(cls: type[Self]) -> UserNewsType:  # type: ignore
        """Mimics the Steam Client's feed when in the friend activity tab."""
        return cls.FriendAdded | cls.App

    @classproperty
    def All(cls: type[Self]) -> UserNewsType:  # type: ignore
        """Returns a member with every flag set."""
        return reduce(cls.__or__, (member for member in cls if member.flag != 0))

# fmt: on


if __debug__:
    _ENUM_NAMES = {enum.__name__ for enum in Enum.__subclasses__() + IntEnum.__subclasses__() + Flags.__subclasses__()}
    assert _ENUM_NAMES.issubset(__all__), f"__all__ is not complete, missing {_ENUM_NAMES - set(__all__)}"
