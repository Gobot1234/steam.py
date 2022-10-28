"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Final, Protocol, cast, overload

from yarl import URL

from .app import PartialApp
from .models import _IOMixin
from .protobufs.chat import EChatRoomMessageReactionType
from .protobufs.friend_messages import EMessageReactionType
from .utils import DateTime

if TYPE_CHECKING:
    from .message import Authors, Message
    from .protobufs.friends import (
        CMsgClientEmoticonListEffect as ClientEffectProto,
        CMsgClientEmoticonListEmoticon as ClientEmoticonProto,
        CMsgClientEmoticonListSticker as ClientStickerProto,
    )
    from .state import ConnectionState


__all__ = (
    "Award",
    "AwardReaction",
    "PartialMessageReaction",
    "MessageReaction",
    "Emoticon",
    "Sticker",
    "ClientEmoticon",
    "ClientSticker",
)


class ReactionProtocol(Protocol):
    reactionid: int
    count: int


@dataclass(slots=True)
class _Reaction:
    reactionid: int
    count: int


BASE_REACTION_URL: Final = "https://store.cloudflare.steamstatic.com/public/images/loyalty/reactions/{type}/{id}.png"
BASE_ECONOMY_URL: Final = URL("https://community.akamai.steamstatic.com/economy")
AWARD_ID_TO_NAME: Final = cast(Mapping[int, str], {
    1: "Deep Thoughts",
    2: "Heartwarming",
    3: "Hilarious",
    4: "Hot Take",
    5: "Poetry",
    6: "Extra Helpful",
    7: "Gotta Have It",
    8: "Michelangelo",
    9: "Treasure",
    10: "Mind Blown",
    11: "Golden Unicorn",
    12: "Mad Scientist",
    13: "Clever",
    14: "Warm Blanket",
    15: "Saucy",
    16: "Slow Clap",
    17: "Take My Points",
    18: "Wholesome",
    19: "Jester",
    20: "Fancy Pants",
    21: "Whoa",
    22: "Super Star",
    23: "Wild",
})  # fmt: skip


class Award(_IOMixin):
    """Represents an award.

    Attributes
    ----------
    id
        The ID of the award.
    name
        The english localised name of the award.
    """

    def __init__(self, state: ConnectionState, id: int):
        self._state = state
        self.id = id
        self.name = AWARD_ID_TO_NAME.get(self.id, f"Unknown Award {self.id}")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id}>"

    @property
    def url(self) -> str:
        """The reaction's icon URL."""
        return BASE_REACTION_URL.format(type="still", id=self.id)

    @property
    def animated_url(self) -> str:
        """The reaction's icon animated URL."""
        return BASE_REACTION_URL.format(type="animated", id=self.id)

    @asynccontextmanager
    async def open(self, *, animated: bool = False) -> AsyncGenerator[BytesIO, None]:
        async with self._state.http._session.get(self.animated_url if animated else self.url) as r:
            yield BytesIO(await r.read())


class AwardReaction:
    """Represents an award on user generated content.

    Attributes
    ----------
    award
        The award given to the user generated content.
    count
        The reactions count on the post.
    """

    def __init__(self, state: ConnectionState, proto: ReactionProtocol):
        self._state = state
        self.award = Award(state, proto.reactionid)
        self.count = proto.count

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} award={self.award!r} count={self.count}>"


@dataclass(slots=True)
class PartialMessageReaction:
    """Represents a partial reaction to a message."""

    _state: ConnectionState
    message: Message
    """The message the reaction applies to. """
    emoticon: Emoticon | None
    """The emoticon that was reacted with."""
    sticker: Sticker | None
    """The sticker that was reacted with."""

    if TYPE_CHECKING:

        @overload
        def __init__(self, _state: ConnectionState, message: Message, emoticon: Emoticon, sticker: None) -> None:  # type: ignore
            ...

        @overload
        def __init__(self, _state: ConnectionState, message: Message, emoticon: None, sticker: Sticker) -> None:
            ...

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} message={self.message!r} emoticon={self.emoticon!r} sticker={self.sticker!r}>"
        )


@dataclass(slots=True, eq=False, repr=False)
class MessageReaction(PartialMessageReaction):
    """Represents a reaction to a message."""

    user: Authors
    """The user that reacted to the message."""
    created_at: datetime | None = None
    """The time the reaction was added to the message."""
    ordinal: int | None = None
    """The ordinal of the the message."""

    if TYPE_CHECKING:

        @overload
        def __init__(  # type: ignore
            self,
            _state: ConnectionState,
            message: Message,
            emoticon: Emoticon,
            sticker: None,
            user: Authors,
            created_at: datetime | None = None,
            ordinal: int | None = None,
        ) -> None:
            ...

        @overload
        def __init__(
            self,
            _state: ConnectionState,
            message: Message,
            emoticon: None,
            sticker: Sticker,
            user: Authors,
            created_at: datetime | None = None,
            ordinal: int | None = None,
        ) -> None:
            ...

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented

        return (
            self.message == other.message
            and self.emoticon == other.emoticon
            and self.sticker == other.sticker
            and self.user == other.user
        )

    def __hash__(self) -> int:
        return hash((self.message, self.emoticon, self.sticker, self.user))

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} message={self.message!r} emoticon={self.emoticon!r} sticker={self.sticker!r} user={self.user!r}>"


class BaseEmoticon(_IOMixin):
    __slots__ = ("_state", "name")
    url: str

    def __init__(self, state: ConnectionState, name: str):
        self._state = state
        self.name = name.removeprefix(":").removesuffix(":")  # :emoji_name:

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEmoticon):
            return NotImplemented
        if (isinstance(self, Emoticon) and isinstance(other, Emoticon)) or (
            isinstance(self, Sticker) and isinstance(other, Sticker)
        ):
            return self.name == other.name

        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.name)


EMOTICON_TYPE = EChatRoomMessageReactionType.Emoticon
STICKER_TYPE = EChatRoomMessageReactionType.Sticker

if TYPE_CHECKING:  # until actual intersection types are added this will have to do
    assert isinstance(EMOTICON_TYPE, EMessageReactionType)
    assert isinstance(STICKER_TYPE, EMessageReactionType)


class Emoticon(BaseEmoticon):
    """Represents an emoticon in chat.

    .. container:: operations

        .. describe:: x == y

            Checks if two emoticons are equal.

        .. describe:: str(x)

            The string to send this emoticon in chat.

        .. describe:: hash(x)

            Returns the emoticon's hash.


    Attributes
    ----------
    name
        The name of this emoticon.
    """

    __slots__ = ()
    _TYPE: Final = EMOTICON_TYPE

    def __str__(self):
        return f":{self.name}:"

    @property
    def url(self) -> str:
        """The URL for this emoticon."""
        return str(BASE_ECONOMY_URL / "emoticonlarge" / self.name)

    async def app(self) -> PartialApp:
        """Fetches this emoticon's associated app.

        Note
        ----
        This app has its :attr:`~App.name` set unlike :meth:`Sticker.app`.
        """
        data = await self._state.http.get(BASE_ECONOMY_URL / "emoticonhoverjson" / self.name)
        return PartialApp(self._state, id=data["appid"], name=data["app_name"])


class Sticker(BaseEmoticon):
    """Represents a sticker in chat.

    .. container:: operations

        .. describe:: x == y

            Checks if two stickers are equal.

        .. describe:: str(x)

            The way to send this sticker in chat.

        .. describe:: hash(x)

            Returns the stickers's hash.

    Note
    ----
    Unlike :class:`Emoticon` this can only be sent in a message by itself.

    Attributes
    ----------
    name
        The name of this sticker.
    """

    __slots__ = ()
    _TYPE: Final = STICKER_TYPE

    def __str__(self) -> str:
        return f"/sticker {self.name}"

    @property
    def url(self) -> str:
        """The URL for this sticker."""
        return str(BASE_ECONOMY_URL / "sticker" / self.name)

    async def app(self) -> PartialApp:
        """Fetches this sticker's associated app."""
        data = await self._state.http.get(BASE_ECONOMY_URL / "stickerjson" / self.name)
        return PartialApp(self._state, id=data["appid"])


class BaseClientEmoticon(BaseEmoticon):
    __slots__ = ("count", "use_count", "last_used", "received_at")

    def __init__(self, state: ConnectionState, proto: ClientEmoticonProto | ClientStickerProto):
        super().__init__(state, proto.name)
        self.count = proto.count
        self.use_count = proto.use_count
        self.last_used = DateTime.from_timestamp(proto.time_last_used)
        self.received_at = DateTime.from_timestamp(proto.time_received)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} count={self.count!r} use_count={self.use_count!r}>"


class ClientEmoticon(BaseClientEmoticon, Emoticon):
    """Represents an :class:`Emoticon` the :class:`ClientUser` owns."""

    __slots__ = ()


class ClientSticker(BaseClientEmoticon, Sticker):
    """Represents a :class:`Sticker` the :class:`ClientUser` owns."""

    __slots__ = ("_app_id",)

    def __init__(self, state: ConnectionState, proto: ClientStickerProto):
        super().__init__(state, proto)
        self._app_id = proto.appid

    async def app(self) -> PartialApp:
        return PartialApp(self._state, id=self._app_id)  # no point fetching
