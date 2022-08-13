"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, cast

from typing_extensions import Final, Protocol
from yarl import URL

from .game import StatefulGame
from .models import _IOMixin
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


@dataclass
class _Reaction:
    __slots__ = tuple(ReactionProtocol.__annotations__)
    __annotations__ = ReactionProtocol.__annotations__


BASE_REACTION_URL: Final = "https://store.cloudflare.steamstatic.com/public/images/loyalty/reactions/{type}/{id}.png"
BASE_ECONOMY_URL: Final = URL("https://community.akamai.steamstatic.com/economy")
AWARD_ID_TO_NAME: Final = cast("Mapping[int, str]", {
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


@dataclass
class PartialMessageReaction:
    """Represents a partial reaction to a message."""

    _state: ConnectionState
    message: Message
    """The message the reaction applies to. """
    emoticon: Emoticon | None
    """The emoticon that was reacted with."""
    sticker: Sticker | None
    """The sticker that was reacted with."""


@dataclass
class MessageReaction(PartialMessageReaction):
    """Represents a reaction to a message."""

    user: Authors
    """The user that reacted to the message."""
    created_at: datetime | None = None
    """The time the reaction was added to the message."""
    ordinal: int | None = None
    """The ordinal of the the message."""

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented

        return (
            self.message == other.message
            and self.emoticon == other.emoticon
            and self.sticker == other.sticker
            and self.user == other.user
        )


class BaseEmoticon(_IOMixin):
    __slots__ = ("_state", "name")
    url: str

    def __init__(self, state: ConnectionState, name: str):
        self._state = state
        self.name = name.strip(":")  # :emoji_name:

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


class Emoticon(BaseEmoticon):
    """Represents an emoticon in chat.

    .. container:: operations

        .. describe:: str(x)

            The string to send this emoticon in chat.

    Attributes
    ----------
    name
        The name of this emoticon.
    """

    __slots__ = ()

    def __str__(self):
        return f":{self.name}:"

    @property
    def url(self) -> str:
        """The URL for this emoticon."""
        return str(BASE_ECONOMY_URL / "emoticonlarge" / self.name)

    async def game(self) -> StatefulGame:
        """Fetches this emoticon's associated game.

        Note
        ----
        This game has its :attr:`~Game.name` set unlike :meth:`Sticker.game`.
        """
        data = await self._state.http.get(BASE_ECONOMY_URL / "emoticonhoverjson" / self.name)
        return StatefulGame(self._state, id=data["appid"], name=data["app_name"])


class Sticker(BaseEmoticon):
    """Represents a sticker in chat.

    .. container:: operations

        .. describe:: str(x)

            The way to send this sticker in chat.

    Note
    ----
    Unlike :class:`Emoticon` this can only be sent in a message by itself.

    Attributes
    ----------
    name
        The name of this sticker.
    """

    __slots__ = ()

    def __str__(self) -> str:
        return f"/sticker {self.name}"

    @property
    def url(self) -> str:
        """The URL for this sticker."""
        return str(BASE_ECONOMY_URL / "sticker" / self.name)

    async def game(self) -> StatefulGame:
        """Fetches this sticker's associated game."""
        data = await self._state.http.get(BASE_ECONOMY_URL / "stickerjson" / self.name)
        return StatefulGame(self._state, id=data["appid"])


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

    async def game(self) -> StatefulGame:
        return StatefulGame(self._state, id=self._app_id)  # no point fetching
