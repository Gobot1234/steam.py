"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING, Sequence

from yarl import URL as URL_

from .abc import Awardable, Commentable, _CommentableKwargs
from .enums import Language, PublishedFileRevision, PublishedFileType, PublishedFileVisibility
from .game import StatefulGame
from .models import URL, _IOMixin
from .reaction import AwardReaction
from .utils import DateTime

if TYPE_CHECKING:
    from .manifest import Manifest
    from .message import Authors
    from .protobufs.published_file import PublishedFileDetails
    from .state import ConnectionState


__all__ = (
    "PublishedFile",
    "DetailsPreview",
    "PreviewInfo",
    "PublishedFileChild",
    "PublishedFileChange",
)


@dataclass
class DetailsPreview(_IOMixin):
    _state: ConnectionState
    id: int
    position: int
    url: str
    size: int
    filename: str
    type: int

    @property
    def ugc_id(self) -> int:
        return int(URL_(self.url).parts[2])


@dataclass
class PreviewInfo(_IOMixin):
    _state: ConnectionState
    ugc_id: int
    size: int
    url: str


@dataclass
class PublishedFileChild:
    _state: ConnectionState
    id: int
    position: int
    type: int
    parent: PublishedFile

    async def fetch(
        self,
        *,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
    ) -> PublishedFile:
        """Resolves this child into a full file.

        Parameters
        ----------
        revision
            The revision of the file to fetch.
        language
            The language to fetch the file in. If ``None``, the current language is used.
        """
        (file,) = await self._state.fetch_published_files((self.id,), revision, language)
        assert file
        return file

    async def manifest(self) -> Manifest:
        """Fetch the manifest for this child."""
        resolved = await self.fetch()
        return await resolved.manifest()


@dataclass
class PublishedFileChange:
    __slots__ = ("description", "created_at")
    description: str
    created_at: datetime


class PublishedFile(Commentable, Awardable):
    """Represents a published file on SteamPipe."""

    _AWARDABLE_TYPE = 2
    __slots__ = (
        "_state",
        "id",
        "name",
        "author",
        "game",
        "created_with",
        "created_at",
        "updated_at",
        "url",
        "manifest_id",
        "revision",
        "available_revisions",
        "change_number",
        "type",
        "views",
        "youtube_id",
        "description",
        "visibility",
        "flags",
        "accepted",
        "show_subscribe_all",
        "number_of_developer_comments",
        "number_of_public_comments",
        "spoiler",
        "children",
        "filename",
        "size",
        "cdn_url",
        "preview",
        "previews",
        "banned",
        "ban_reason",
        "banner",
        "ban_text_check_result",
        "can_be_deleted",
        "incompatible",
        "can_subscribe",
        "subscriptions",
        "time_subscribed",
        "favourited",
        "followers",
        "lifetime_subscriptions",
        "lifetime_favourited",
        "lifetime_followers",
        "lifetime_playtime",
        "lifetime_playtime_sessions",
        "image_width",
        "image_height",
        "image_url",
        "shortcut_id",
        "shortcut_name",
        "consumer_shortcut_id",
        "tags",
        "kv_tags",
        "reports",
        "upvotes",
        "downvotes",
        "score",
        "playtime_stats",
        "for_sale_data",
        "metadata",
        "language",
        "maybe_inappropriate_sex",
        "maybe_inappropriate_violence",
        "reactions",
    )

    # TODO needs
    # Client.create_published_file() -> PublishedFile
    # although this needs steammessages_cloud.proto to be compiled and an api around that

    def __init__(self, state: ConnectionState, proto: PublishedFileDetails, author: Authors):
        self._state = state
        self.id = proto.publishedfileid
        """The file's id."""
        self.name = proto.title
        """The file's name."""
        self.author = author
        """The file's author."""
        self.game = StatefulGame(state, id=proto.consumer_appid, name=proto.app_name)
        """The file's game."""
        self.created_with = StatefulGame(state, id=proto.creator_appid)
        """The file's created_with."""
        self.created_at = DateTime.from_timestamp(proto.time_created)
        """The time the file was created at."""
        self.updated_at = DateTime.from_timestamp(proto.time_updated)
        """The time the file was last updated at."""
        self.url = str(
            URL.COMMUNITY / "sharedfiles/filedetails" % {"id": self.id}
        )  # proto.url is seemingly always empty
        """The file's url."""
        self.manifest_id = proto.hcontent_file
        """The file's manifest id."""
        self.revision = PublishedFileRevision.try_value(proto.revision)
        """The file's revision."""
        self.available_revisions = [PublishedFileRevision.try_value(revision) for revision in proto.available_revisions]
        """The file's available_revisions."""
        self.change_number = proto.revision_change_number
        """This revision's change number."""
        self.type = PublishedFileType.try_value(proto.file_type)
        """The file's type."""
        self.views = proto.views
        """The file's views."""
        self.youtube_id = proto.youtubevideoid
        """The file's youtube_id."""
        self.description = proto.file_description
        """The file's description."""
        self.visibility = PublishedFileVisibility.try_value(proto.visibility)
        """The file's visibility."""
        self.flags = proto.flags  # TODO figure out what these are
        """The file's flags."""
        self.accepted = proto.workshop_accepted
        """Whether the file has been accepted."""
        self.show_subscribe_all = proto.show_subscribe_all
        """The file's show_subscribe_all."""
        self.number_of_developer_comments = proto.num_comments_developer
        """The file's number of comments from the developer."""
        self.number_of_public_comments = proto.num_comments_public
        """The file's number of public comments."""
        self.spoiler = proto.spoiler_tag
        """Whether the file is marked as a spoiler."""
        self.children = [
            PublishedFileChild(state, p.publishedfileid, p.sortorder, PublishedFileType.try_value(p.file_type), self)
            for p in proto.children
        ]
        """The file's children."""

        self.filename = proto.filename
        """The file's filename."""
        self.size = proto.file_size
        """The file's size."""
        self.cdn_url = proto.file_url
        """The file's cdn_url."""

        self.preview = PreviewInfo(state, proto.hcontent_preview, proto.preview_file_size, proto.preview_url)
        """The file's preview."""
        self.previews = [
            DetailsPreview(state, p.previewid, p.sortorder, p.url, p.size, p.filename, p.preview_type)
            for p in proto.previews
        ]
        """All the file's previews."""
        self.banned = proto.banned
        """Whether the file is banned."""
        self.ban_reason = proto.ban_reason if self.banned else None
        """The file's ban_reason."""
        self.banner = proto.banner if self.banned else None
        """The file's banner."""
        self.ban_text_check_result = proto.ban_text_check_result
        """The file's ban_text_check_result."""

        self.can_be_deleted = proto.can_be_deleted
        """The file's can_be_deleted."""
        self.incompatible = proto.incompatible
        """The file's incompatible."""

        self.can_subscribe = proto.can_subscribe
        """The file's can_subscribe."""
        self.subscriptions = proto.subscriptions
        """The file's subscriptions."""
        self.time_subscribed = proto.time_subscribed
        """The file's time_subscribed."""

        self.favourited = proto.favorited
        """The current number of people that have favourited the file."""
        self.followers = proto.followers
        """The current number of followers the file has."""
        self.lifetime_subscriptions = proto.lifetime_subscriptions
        """The file's lifetime subscriptions."""
        self.lifetime_favourited = proto.lifetime_favorited
        """The total number of people that have favourited the file."""
        self.lifetime_followers = proto.lifetime_followers
        """The total number of followers the file has."""
        self.lifetime_playtime = proto.lifetime_playtime
        """The file's lifetime playtime."""
        self.lifetime_playtime_sessions = proto.lifetime_playtime_sessions
        """The file's lifetime playtime sessions."""

        self.image_width = proto.image_width
        """The file's image's width."""
        self.image_height = proto.image_height
        """The file's image's height."""
        self.image_url = proto.image_url
        """The file's image's url."""

        self.shortcut_id = proto.shortcutid
        """The file's shortcut ID."""
        self.shortcut_name = proto.shortcutname
        """The file's shortcut name."""
        self.consumer_shortcut_id = proto.consumer_shortcutid
        """The file's consumer's shortcut ID."""

        self.tags = proto.tags
        """The file's tags."""
        self.kv_tags = {tag.key: tag.value for tag in proto.kvtags}
        """The file's key-value tags"""

        self.reports = proto.num_reports
        """The number of reports the file has."""
        self.upvotes = proto.vote_data.votes_up
        """The number of upvotes the file has."""
        self.downvotes = proto.vote_data.votes_down
        """The number of downvotes the file has."""
        self.score = proto.vote_data.score
        """The file's score."""
        self.playtime_stats = proto.playtime_stats
        """The file's playtime stats."""
        self.for_sale_data = proto.for_sale_data
        """The file's sale data."""

        self.metadata = proto.metadata
        """Any metadata attached to the file."""
        self.language = Language.try_value(proto.language)
        """The language the file is in."""
        self.maybe_inappropriate_sex = proto.maybe_inappropriate_sex
        """Whether the file may contain sexually inappropriate content."""
        self.maybe_inappropriate_violence = proto.maybe_inappropriate_violence
        """Whether the file may contain violent content which may be inappropriate for some."""

        self.reactions = [AwardReaction(state, reaction) for reaction in proto.reactions]
        """The file's reactions."""

    def __repr__(self) -> str:
        attrs = ("name", "id", "author", "game", "manifest_id", "change_number")
        resolved = [f"{name}={getattr(self, name)!r}" for name in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    @property
    def _commentable_kwargs(self) -> _CommentableKwargs:
        return {
            "id64": self.author.id64,
            "thread_type": 9,
        }

    async def manifest(self) -> Manifest:
        """The manifest associated with this published file."""
        return await self._state.fetch_manifest(self.game.id, self.manifest_id, self.game.id, self.name)

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[BytesIO, None]:
        if self.type not in (PublishedFileType.Art, PublishedFileType.SteamVideo):
            raise NotImplementedError(f"Cannot open {self.type}")

        async with self._state.http._session.get(self.cdn_url) as r:
            io = BytesIO(await r.read())
            io.name = self.filename
            yield io

    async def fetch_children(
        self, *, revision: PublishedFileRevision = PublishedFileRevision.Default, language: Language | None = None
    ) -> list[PublishedFile]:
        """Fetches this published file's children.

        Parameters
        ----------
        revision
            The revision to fetch.
        language
            The language to fetch children in. If ``None``, the current language is used.
        """
        results = await self._state.fetch_published_files((c.id for c in self.children), revision, language)
        # assert all(results)   # this is safe, hopefully this can be added if HKT happens
        return results  # type: ignore

    async def parents(
        self,
        *,
        revision: PublishedFileRevision = PublishedFileRevision.Default,
        language: Language | None = None,
    ) -> list[PublishedFile]:
        """Fetches this published file's parents.

        Parameters
        ----------
        revision
            The revision to fetch.
        language
            The language to fetch parents in. If ``None``, the current language is used.
        """
        cursor = "*"
        more = True
        parents: list[PublishedFile] = []
        authors: set[int] = set()

        while more:
            proto = await self._state.fetch_published_file_parents(self.id, revision, language, cursor)
            more = len(parents) < proto.total

            for file in proto.publishedfiledetails:
                author: Authors = file.creator  # type: ignore
                parents.append(PublishedFile(self._state, file, author))
                authors.add(file.creator)

        for author in await self._state._maybe_users(authors):
            for parent in parents:
                if parent.author == author.id64:
                    parent.author = author

        return parents

    async def upvote(self) -> None:
        """Upvotes this published file."""
        await self._state.upvote_published_file(self.id, True)

    async def downvote(self) -> None:
        """Downvotes this published file."""
        await self._state.upvote_published_file(self.id, False)

    async def subscribe(self) -> None:
        """Subscribes to this published file's changes."""
        await self._state.subscribe_to_published_file(self.id)

    async def unsubscribe(self) -> None:
        """Unsubscribes from this published file's changes."""
        await self._state.unsubscribe_from_published_file(self.id)

    async def is_subscribed(self) -> bool:
        """Whether the client user is subscribed to this published file."""
        return await self._state.is_subscribed_to_published_file(self.id)

    async def add_child(self, child: PublishedFile) -> None:
        """Adds a child to this published file.

        Parameters
        ----------
        child
            The child to add.
        """
        await self._state.add_published_file_child(self.id, child.id)

    async def remove_child(self, child: PublishedFile) -> None:
        """Removes a child from this published file.

        Parameters
        ----------
        child
            The child to remove.
        """
        await self._state.remove_published_file_child(self.id, child.id)

    async def history(self, *, language: Language | None = None) -> list[PublishedFileChange]:
        """Fetches this published file's history.

        Parameters
        ----------
        language
            The language to fetch history in. If ``None``, the current language is used.
        """
        changes = await self._state.fetch_published_file_history(self.id, language)
        return [
            PublishedFileChange(change.change_description, DateTime.from_timestamp(change.timestamp))
            for change in changes
        ]

    async def fetch_history_entry(self, at: datetime, *, language: Language | None = None) -> PublishedFileChange:
        """Fetches the history entry at a given time.

        Parameters
        ----------
        at
            The time to fetch the history entry at.
        language
            The language to fetch history entries in. If ``None``, the current language is used.
        """
        change = await self._state.fetch_published_file_history_entry(self.id, at, language)
        return PublishedFileChange(change.change_description, at)

    # async def relationship(self):
    #     ...  # literally no clue what this does

    # async def friends_who_favourited(self):
    #     "https://steamcommunity.com/sharedfiles/friendswhofavoritedfile?id=2120834324&appid=440"
    #     # requires avatar hash property might wait till v1

    async def edit(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        visibility: PublishedFileVisibility | None = None,
        tags: Sequence[str] = (),
        filename: str | None = None,
        preview_filename: str | None = None,
    ) -> None:
        """Edits this published file.

        Parameters
        ----------
        name
            The new name of the file.
        description
            The new description of the file.
        visibility
            The new visibility of the file.
        tags
            The new tags of the file.
        filename
            The new filename of the file.
        preview_filename
            The new preview filename of the file.
        """
        try:
            preview_filename = self.previews[0].filename  # TODO test
        except IndexError:
            preview_filename = ""
        await self._state.edit_published_file(
            self.id,
            self.game.id,
            name if name is not None else self.name,
            description if description is not None else self.description,
            visibility or self.visibility,
            tags if tags is not None else [t.display_name for t in self.tags],
            filename if filename is not None else self.filename,
            preview_filename if preview_filename is not None else preview_filename,
        )
