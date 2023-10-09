"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from .abc import PartialUser
from .app import PartialApp
from .clan import PartialClan
from .enums import EventType, Type, UserNewsType
from .id import ID
from .package import PartialPackage
from .types.id import PostID, PublishedFileID
from .utils import DateTime

if TYPE_CHECKING:
    from .achievement import UserNewsAchievement
    from .event import Announcement, Event
    from .friend import Friend
    from .post import Post
    from .protobufs import user_news
    from .published_file import PublishedFile
    from .review import Review
    from .state import ConnectionState


class UserNews:
    """Represents a news entry on the activity feed."""

    def __init__(
        self,
        state: ConnectionState,
        news: user_news.GetUserNewsResponse.Event,
        achievements: dict[str, UserNewsAchievement],
    ) -> None:
        self._state = state
        self.type: Final = UserNewsType.try_value(news.eventtype)
        """The type of news entry."""
        self.created_at = DateTime.from_timestamp(news.eventtime)
        """When the news entry was created."""
        target = ID(news.steamid_target)
        actor = ID(news.steamid_actor)
        self.target = cast(
            "Friend | PartialUser | PartialClan | None",
            (state._maybe_friend(target.id) if target.type is Type.Individual else PartialClan(state, target.id64))
            if news.steamid_target
            else None,
        )
        """The target of the news entry."""
        self.actor = cast(
            "Friend | PartialUser | PartialClan",
            state._maybe_friend(actor.id) if actor.type is Type.Individual else PartialClan(state, actor.id64),
        )
        """The actor of the news entry."""
        self.app = PartialApp(state, id=news.gameid) if news.gameid else None
        """The app this news entry is for."""
        self.package = PartialPackage(state, id=news.gameid) if news.gameid else None
        """The package this news entry is for."""
        self.apps = [PartialApp(state, id=id) for id in news.appids]
        """If :attr:`type` is :attr:`UserNewsType.ReceivedNewGame`, the apps unlocked by :attr:`package`.
        If :attr:`type` is :attr:`UserNewsType.AddedGameToWishlist`, the apps wishlisted by :attr:`actor`.
        """
        self.achievements = [achievements[name] for name in news.achievement_names]
        """The achievements unlocked. Only used for :attr:`UserNewsType.AchievementUnlocked`."""
        self.shortcut_id = news.shortcutid
        """The shortcut ID this news entry is for."""
        self.event_id = news.clan_eventid
        """The event ID this news entry is for. Only used for :attr:`UserNewsType.ScheduledEvent`."""
        self.announcement_id = news.clan_announcementid
        """The announcement ID this news entry is for. Only used for :attr:`UserNewsType.PostedAnnouncement`."""
        self.published_file_id = PublishedFileID(news.publishedfileid)
        """The published file ID this news entry is for."""
        self.post_id = PostID(news.steamid_target if self.type is UserNewsType.Post else 0)  # lol valve
        """The post ID this news entry is for. Only used for :attr:`UserNewsType.Post`."""
        if self.post_id:
            self.target = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.type!r} target={self.target!r} actor={self.actor!r}>"

    # ideally these would use self: UserNews[Literal[Type.Event]] etc but that doesn't work with pyright unfortunately
    # see microsoft/pyright#5706
    async def event(self) -> Event[EventType, PartialClan]:
        """Fetch the event this news entry is for."""
        if not self.event_id:
            raise ValueError("There's no associated Event for this news entry")
        assert isinstance(self.actor, PartialClan)
        return await self.actor.fetch_event(self.event_id)

    async def announcement(self) -> Announcement[PartialClan]:
        """Fetch the announcement this news entry is for."""
        if not self.announcement_id:
            raise ValueError("There's no associated Announcement for this news entry")
        assert isinstance(self.actor, PartialClan)
        return await self.actor.fetch_announcement(self.announcement_id)

    async def published_file(self) -> PublishedFile:
        """Fetch the published file this news entry is for."""
        if not self.published_file_id:
            raise ValueError("There's no associated PublishedFile for this news entry")
        assert isinstance(self.actor, PartialUser)
        file = await self.actor.fetch_published_file(self.published_file_id)
        assert file
        return file

    async def review(self) -> Review:
        """Fetch the review this news entry is for."""
        if self.type is not UserNewsType.Review:
            raise ValueError("There's no associated Review for this news entry")
        assert isinstance(self.actor, PartialUser)
        assert self.app
        return await self.actor.fetch_review(self.app)

    async def post(self) -> Post:
        """Fetch the post this news entry is for."""
        if self.type is not UserNewsType.Post:
            raise ValueError("There's no associated Post for this news entry")
        assert isinstance(self.actor, PartialUser)
        return await self.actor.fetch_post(self.post_id)

    # async def comment(self) -> Comment:
    #     """Fetch the comment this news entry is for."""  # TODO not sure how this works yet
    #     if self.type is UserNewsType.CommentByMe:
    #         return await self.actor.fetch_comment(self.target)
    #     elif self.type is UserNewsType.CommentOnMe:
    #         return await self._state.user.fetch_comment(self.target)
    #     raise ValueError("There's no associated Comment for this news entry")
