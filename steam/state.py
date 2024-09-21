"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import collections
import functools
import inspect
import logging
import random
import weakref
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, Callable, Iterable, Sequence
from contextlib import asynccontextmanager
from copy import copy
from datetime import datetime, timedelta
from itertools import count
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Final, Generic, Protocol, TypeVar, cast, get_args
from zlib import crc32

from yarl import URL as URL_

from . import utils
from ._const import JSON_LOADS, READ_U32, URL, VDF_BINARY_LOADS, VDF_LOADS, TaskGroup, timeout
from .abc import Awardable, Commentable, PartialUser, _CommentThreadType
from .app import App, AuthenticationTicket, FetchedApp
from .bundle import FetchedBundle
from .clan import Clan, ClanMember, PartialClan
from .comment import Comment
from .enums import *
from .errors import *
from .friend import Friend
from .gateway import CMServer, ConnectionClosed, Msgs, ProtoMsgs, SteamWebSocket, unpack_multi
from .group import Group, GroupMember
from .guard import *
from .id import _ID64_TO_ID32, ID, parse_id64
from .invite import ClanInvite, GroupInvite, UserInvite
from .manifest import AppInfo, ContentServer, Manifest, PackageInfo
from .message import *
from .message import ClanMessage
from .models import Wallet
from .package import FetchedPackage, License
from .protobufs import (
    SERVICE_EMSGS,
    EMsg,
    NoMsg,
    UnifiedMessage,
    app_info,
    base,
    chat,
    clan,
    client_server,
    client_server_2,
    community,
    content_server,
    econ,
    encrypted_app_ticket,
    friend_messages,
    friends,
    game_servers,
    leaderboards,
    login,
    loyalty_rewards,
    notifications,
    player,
    published_file,
    quest,
    reviews,
    store,
    user_news,
    user_stats,
)
from .published_file import PublishedFile
from .reaction import (
    Award,
    ClientEffect,
    ClientEmoticon,
    ClientSticker,
    Emoticon,
    MessageReaction,
    ReactionProtocol,
    Sticker,
    _Reaction,
)
from .role import Role, RolePermissions
from .trade import Item, TradeOffer
from .types.id import *
from .user import ClientUser, User
from .utils import DateTime, cached_property, call_once

if TYPE_CHECKING:
    from types import CoroutineType

    from typing_extensions import Never, Self, Unpack

    from .abc import Message
    from .chat import PartialMember
    from .client import Client, ClientKwargs
    from .media import Media
    from .types import manifest, trade
    from .types.http import Coro
    from .types.user import Author, AuthorT, IndividualID


log = logging.getLogger(__name__)

T = TypeVar("T")
OwnerT = TypeVar("OwnerT", bound=Commentable)


class Queue(Generic[T]):
    def __init__(self, attr: attrgetter[int] = attrgetter("id")) -> None:
        self.queue: list[T] = []
        self.attr = attr
        self._waiting_for: dict[int, asyncio.Future[T]] = {}

    async def wait_for(self, id: int) -> T:
        for item in reversed(self.queue):  # check if it's already here
            if self.attr(item) == id:
                self.queue.remove(item)
                return item

        self._waiting_for[id] = future = asyncio.get_running_loop().create_future()
        item = await future
        self.queue.remove(item)
        return item

    def __len__(self) -> int:
        return len(self.queue)

    def __iadd__(self, other: Iterable[T]) -> Self:
        self.queue += other

        for item in other:
            attr = self.attr(item)
            try:
                future = self._waiting_for[attr]
            except KeyError:
                pass
            else:
                future.set_result(item)
                del self._waiting_for[attr]

        return self


StateT = TypeVar("StateT", bound="ConnectionState", contravariant=True)
MsgsT = TypeVar("MsgsT", bound="Msgs", contravariant=True)


class ParserCallback(Protocol[StateT, MsgsT]):
    __name__: str

    def __call__(self_, self: StateT, msg: MsgsT, /, *args: Any) -> CoroutineType[Any, Any, Any] | Any: ...


F = TypeVar("F", bound=Callable[..., Any])


def parser(func: F) -> F:
    func.__parser__ = True  # type: ignore
    return func


class noop:
    def __await__(self):
        yield


def requires_intent(intent: Intents) -> Callable[[F], F]:
    def deco(func: F) -> F:
        @functools.wraps(func)
        def inner(self: ConnectionState, *args: Any, **kwargs: Any) -> Any:
            return func(self, *args, **kwargs) if self.intents & intent > 0 else noop()

        return cast(F, inner)

    return deco


class ConnectionState:
    parsers: dict[EMsg, ParserCallback[Self, ProtoMsgs]]

    def __init__(self, client: Client, **kwargs: Unpack[ClientKwargs]):
        self.client = client
        self.dispatch = client.dispatch
        self.http = client.http

        self.handled_friends = asyncio.Event()
        self.handled_emoticons = asyncio.Event()
        self.handled_chat_groups = asyncio.Event()
        self.handled_group_members = asyncio.Event()
        self.login_complete = asyncio.Event()
        self.handled_licenses = asyncio.Event()
        self.handled_wallet = asyncio.Event()
        self.intents: Final = kwargs.get("intents", Intents.Safe)
        self.max_messages: int | None = kwargs.get("max_messages", 1000)

        app = kwargs.get("app")
        apps = kwargs.get("apps")
        apps = [app.to_proto() for app in apps] if apps is not None else []
        if app is not None:
            apps.append(app.to_proto())
        self._apps: list[client_server.CMsgClientGamesPlayedGamePlayed] = apps
        self._state: PersonaState = kwargs.get("state", PersonaState.Online)
        self._ui_mode: UIMode = kwargs.get("ui_mode", UIMode.Desktop)
        self._flags: PersonaStateFlag = kwargs.get("flags", PersonaStateFlag.NONE)
        self._force_kick: bool = kwargs.get("force_kick", False)
        self.auto_chunk_chat_groups: bool = kwargs.get("auto_chunk_chat_groups", False)

        self.clear()

    def clear(self) -> None:
        self._users = weakref.WeakValueDictionary[ID32, User]()

        self._groups: dict[ChatGroupID, Group] = {}
        self._clans: dict[ID32, Clan] = {}
        self._clans_by_chat_id: dict[ChatGroupID, Clan] = {}
        self.chat_group_to_view_id: defaultdict[ChatGroupID, int] = defaultdict(count().__next__)
        self.active_chat_groups: set[ChatGroupID] = set()

        self._messages: deque[Message] = deque(maxlen=self.max_messages or 0)
        self.invites: dict[ID64, UserInvite | ClanInvite] = {}

        self.emoticons: list[ClientEmoticon] = []
        self.stickers: list[ClientSticker] = []
        self.effects: list[ClientEffect] = []

        self._trades: dict[TradeOfferID, TradeOffer[Item[User], Item[ClientUser], User]] = {}
        self._confirmations: dict[TradeOfferID, Confirmation] = {}
        self.confirmation_generation_locks = defaultdict[Tags, asyncio.Lock](asyncio.Lock)
        self.trade_queue = Queue[TradeOffer[Item[User], Item[ClientUser], User]]()
        self._trades_to_watch: set[TradeOfferID] = set()
        self.polling_confirmations = False
        self.confirmation_queue = Queue[Confirmation](attr=attrgetter("creator_id"))

        self.cell_id = 0
        self._connected_cm: CMServer | None = None

        self.wallet: Wallet = None  # type: ignore

        self.licenses: dict[PackageID, License] = {}
        self._license_lock = asyncio.Lock()
        self.licenses_being_waited_for = weakref.WeakValueDictionary[PackageID, asyncio.Future[License]]()
        self._manifest_passwords: dict[AppID, dict[str, str]] = {}

        self._game_connect_bytes: list[bytes] = (
            []
        )  # this is a bad name but it's a combination of gc_token, steam id, and time
        self.connection_count = 0
        self._h_steam_pipe = random.randint(1, 1000001)
        self._active_auth_tickets: dict[tuple[AppID, ID64], AuthenticationTicket] = {}
        self._auth_seq_me = 0
        self._auth_seq_them = 0

        self.handled_friends.clear()
        self.handled_emoticons.clear()
        self.handled_chat_groups.clear()
        self.login_complete.clear()
        self.handled_licenses.clear()
        self.handled_wallet.clear()

    @utils.cached_property
    def ws(self) -> SteamWebSocket:
        assert self.client.ws is not None
        return self.client.ws

    @utils.cached_property
    def user(self) -> ClientUser:
        assert self.http.user is not None
        return self.http.user

    @utils.cached_property
    def _device_id(self) -> str:
        return get_device_id(self.user.id64)

    @property
    def _tg(self) -> TaskGroup:
        return self.client._tg

    @utils.cached_property
    def _task_error(self) -> asyncio.Future[None]:
        """Holds the exceptions so that the gateway can propagate exceptions to the client.login call"""
        return asyncio.get_running_loop().create_future()

    @property
    def language(self) -> Language:
        return self.http.language

    @property
    def steam_time(self) -> datetime:
        if self.client.ws is None:  # can't be more precise
            return DateTime.now()
        return DateTime.now() + self.ws.server_offset

    @property
    def users(self) -> list[User]:
        return list(self._users.values())

    @property
    def trades(self) -> list[TradeOffer]:
        return list(self._trades.values())

    @property
    def groups(self) -> list[Group]:
        return list(self._groups.values())

    @property
    def clans(self) -> list[Clan]:
        return list(self._clans.values())

    @property
    def confirmations(self) -> list[Confirmation]:
        return list(self._confirmations.values())

    def get_partial_user(self, id: Intable) -> PartialUser:
        return PartialUser(self, id)

    def get_user(self, id: ID32) -> User | None:
        return self._users.get(id)

    async def fetch_user(self, user_id64: ID64) -> User:
        (user,) = await self.fetch_users((user_id64,))
        return user

    async def fetch_users(self, user_id64s: Iterable[ID64]) -> Sequence[User]:
        user_id64s = list(user_id64s)
        try:
            users = [user async for user in self.ws.fetch_users(user_id64s)]
        except asyncio.TimeoutError:
            users = [User._dict_to_proto(user) async for user in self.http.get_users(user_id64s)]
        return [self._store_user(user) for user in users]

    async def _maybe_user(self, id: Intable) -> User:
        steam_id = ID(id, type=Type.Individual)
        return self.get_user(steam_id.id) or await self.fetch_user(steam_id.id64)

    async def _maybe_users(self, id64s: Iterable[ID64]) -> Sequence[User]:
        ret: list[User | None] = []
        to_fetch: dict[ID64, list[int]] = {}
        for idx, id64 in enumerate(id64s):
            user = self.get_user(_ID64_TO_ID32(id64))
            if user is not None:
                ret.append(user)
            else:
                idxs = to_fetch.get(id64)
                if idxs is None:
                    idxs = to_fetch[id64] = []

                idxs.append(idx)
                ret.append(None)

        if to_fetch:
            for idxs, user in zip(to_fetch.values(), await self.fetch_users(to_fetch)):
                for idx in idxs:
                    ret[idx] = user

        return cast("list[User]", ret)

    def _store_user(self, proto: friends.CMsgClientPersonaStateFriend) -> User:
        try:
            user = self._users[_ID64_TO_ID32(proto.friendid)]
        except KeyError:
            user = User(state=self, proto=proto)
            self._users[user.id] = user
        else:
            user._update(proto)
        return user

    def get_friend(self, id: ID32) -> Friend:
        return self.user._friends[id]

    def _maybe_friend(self, id: ID32) -> Friend | PartialUser:
        return self.user._friends.get(id) or self.get_partial_user(id)

    def _store_friend(self, user: User) -> Friend:
        self.user._friends[user.id] = friend = Friend(self, user)
        return friend

    @parser
    @requires_intent(Intents.Users)
    def parse_persona_state_update(self, msg: friends.CMsgClientPersonaState) -> None:
        for friend in msg.friends:
            after = self.get_user(_ID64_TO_ID32(friend.friendid))
            if after is None:
                continue

            before = copy(after)
            after._update(friend)
            self.dispatch("user_update", before, after)

    @parser
    @requires_intent(Intents.Users)
    async def process_friends(self, msg: friends.CMsgClientFriendsList) -> None:
        await self.login_complete.wait()
        clan_invitees = None
        client_user_friends: list[ID64] = []
        is_load = not msg.bincremental
        for friend in msg.friends:
            id = ID(friend.ulfriendid)
            match relationship := FriendRelationship.try_value(friend.efriendrelationship):
                case FriendRelationship.Friend:
                    try:
                        invite = self.invites.pop(id.id64)
                    except KeyError:
                        if id.type == Type.Individual:
                            if is_load:
                                client_user_friends.append(id.id64)
                            else:
                                user = await self.fetch_user(id.id64)
                                assert user is not None
                                self._store_friend(user)
                    else:
                        self.dispatch("invite_accept", invite)
                        if isinstance(invite, UserInvite):
                            if isinstance(invite.author, User):
                                friend = self._store_friend(invite.author)
                                self.dispatch("friend_add", friend)
                        else:
                            if isinstance(invite.clan, Clan):
                                self._clans[invite.clan.id] = invite.clan

                case (
                    FriendRelationship.RequestInitiator | FriendRelationship.RequestRecipient
                ):  # TODO this needs checking for clans
                    match id.type:
                        case Type.Individual:
                            invitee = await self._maybe_user(id.id64)
                            self.invites[invitee.id64] = invite = UserInvite(
                                self, self.user, author=invitee, relationship=relationship
                            )
                        case Type.Clan:
                            if clan_invitees is None:
                                clan_invitees = await self.http.get_clan_invitees()

                            invitee = await self._maybe_user(clan_invitees[id.id64])
                            try:
                                clan = await self.fetch_clan(id.id64)
                            except WSException:
                                clan = cast(Clan, PartialClan(self, id.id64))
                                log.info("Unknown clan %s invited us", clan)
                            self.invites[clan.id64] = invite = ClanInvite(
                                self, self.user, author=invitee, clan=clan, relationship=relationship
                            )
                        case _:
                            continue
                    self.dispatch("invite", invite)

                case FriendRelationship.NONE:
                    match id.type:
                        case Type.Individual:
                            try:
                                invite = self.invites.pop(id.id64)
                            except KeyError:
                                friend = self.user._friends.pop(id.id, None)
                                if friend is None:
                                    return log.debug("Unknown friend %s removed", id)
                                self.dispatch("friend_remove", friend)
                                continue

                        case Type.Clan:
                            try:
                                invite = self.invites.pop(id.id64)
                            except KeyError:
                                clan = self._clans.pop(id.id, None)
                                if clan is None:
                                    return log.debug("Unknown clan %s removed", id)
                                self.dispatch("clan_leave", clan)
                                continue
                        case _:
                            continue

                    self.dispatch("invite_decline", invite)

        if is_load:
            self.user._friends = {user.id: Friend(self, user) for user in await self.fetch_users(client_user_friends)}
            self.handled_friends.set()

    @requires_intent(Intents.Messages | Intents.Users)
    async def handle_user_message(self, msg: friend_messages.IncomingMessageNotification) -> None:
        await self.client.wait_until_ready()
        id64 = msg.steamid_friend
        partner = self.user._friends.get(_ID64_TO_ID32(id64)) or await self._maybe_user(id64)
        author = self.user if msg.local_echo else partner  # local_echo is always us

        if msg.chat_entry_type == ChatEntryType.Text:
            message = UserMessage(msg, partner._channel, author)
            partner._channel.last_message = message
            self._messages.append(message)
            self.dispatch("message", message)

        elif msg.chat_entry_type == ChatEntryType.Typing:
            when = DateTime.from_timestamp(msg.rtime32_server_timestamp)
            self.dispatch("typing", author, when)

    async def send_user_message(self, user_id64: ID64, content: str) -> UserMessage:
        msg: friend_messages.SendMessageResponse = await self.ws.send_um_and_wait(
            friend_messages.SendMessageRequest(
                steamid=user_id64,
                message=content,
                chat_entry_type=ChatEntryType.Text,
                contains_bbcode=utils.contains_chat_command(content),
            )
        )

        if msg.result == Result.LimitExceeded:
            raise WSForbidden(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        proto = friend_messages.IncomingMessageNotification(
            chat_entry_type=ChatEntryType.Text,
            message=msg.modified_message,
            rtime32_server_timestamp=msg.server_timestamp,
            ordinal=msg.ordinal,
            message_no_bbcode=msg.message_without_bb_code,
        )
        id = _ID64_TO_ID32(user_id64)
        participant = self.user._friends.get(id) or self._users[id]
        message = UserMessage(proto, participant._channel, self.user)
        participant._channel.last_message = message
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def send_user_typing(self, user_id64: ID64) -> None:
        msg: friend_messages.SendMessageResponse = await self.ws.send_um_and_wait(
            friend_messages.SendMessageRequest(
                steamid=user_id64,
                chat_entry_type=ChatEntryType.Typing,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        self.dispatch("typing", self.user, DateTime.from_timestamp(msg.server_timestamp))

    async def ack_user_message(self, user_id64: ID64, timestamp: int) -> None:
        await self.ws.send_proto(friend_messages.AckMessageNotification(steamid_partner=user_id64, timestamp=timestamp))

    async def fetch_user_history(
        self,
        user_id64: ID64,
        start: int,
        last: int,
        start_ordinal: int = 0,
    ) -> friend_messages.GetRecentMessagesResponse:
        msg: friend_messages.GetRecentMessagesResponse = await self.ws.send_um_and_wait(
            friend_messages.GetRecentMessagesRequest(
                steamid1=self.user.id64,
                steamid2=user_id64,
                rtime32_start_time=start,
                bbcode_format=False,
                time_last=last,
                start_ordinal=start_ordinal,
                count=100,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def react_to_user_message(
        self,
        user_id64: ID64,
        server_timestamp: int,
        ordinal: int,
        reaction_name: str,
        reaction_type: friend_messages.EMessageReactionType,
        is_add: bool,
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            friend_messages.UpdateMessageReactionRequest(
                steamid=user_id64,
                server_timestamp=server_timestamp,
                ordinal=ordinal,
                reaction=reaction_name,
                reaction_type=reaction_type,
                is_add=is_add,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    @requires_intent(Intents.Messages | Intents.Users)
    async def handle_user_message_reaction(self, msg: friend_messages.MessageReactionNotification) -> None:
        id64 = msg.steamid_friend
        partner = self.user._friends.get(_ID64_TO_ID32(id64)) or await self._maybe_user(id64)
        reactor = self.user if msg.reactor == self.user.id else partner
        ordinal = msg.ordinal
        created_at = DateTime.from_timestamp(msg.server_timestamp)
        authors = {partner, self.user}
        message = utils.find(
            lambda message: (
                message.author in authors
                and message.created_at == created_at
                and message.ordinal == ordinal
                and message.group is None
                and message.clan is None
            ),
            reversed(self._messages),
        )
        if message is None:
            return log.debug("Got a reaction to an unknown message %s %s", created_at, ordinal)
        match msg.reaction_type:
            case Emoticon._TYPE:
                reaction = MessageReaction(
                    self, message, Emoticon(self, msg.reaction), None, reactor, created_at, ordinal
                )
            case Sticker._TYPE:
                reaction = MessageReaction(
                    self, message, None, Sticker(self, msg.reaction), reactor, created_at, ordinal
                )
            case _:
                return log.debug(
                    "Got an unknown reaction_type %s on message %s %s", msg.reaction_type, created_at, ordinal
                )
        if msg.is_add:
            message.reactions.append(reaction)
        else:
            message.reactions.remove(reaction)

        self.dispatch(f"reaction_{'add' if msg.is_add else 'remove'}", reaction)

    async def fetch_user_apps(self, user_id64: ID64, include_free: bool) -> list[player.GetOwnedGamesResponseGame]:
        msg: player.GetOwnedGamesResponse = await self.ws.send_um_and_wait(
            player.GetOwnedGamesRequest(
                steamid=user_id64,
                include_appinfo=True,
                include_free_sub=True,
                include_played_free_games=include_free,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.games

    async def fetch_user_equipped_profile_items(
        self,
        user_id64: ID64,
        language: Language | None,
    ) -> player.GetProfileItemsEquippedResponse:
        msg: player.GetProfileItemsEquippedResponse = await self.ws.send_um_and_wait(
            player.GetProfileItemsEquippedRequest(
                steamid=user_id64,
                language=(language or self.language).api_name,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_user_profile_customisation(
        self,
        user_id64: ID64,
    ) -> player.GetProfileCustomizationResponse:
        msg: player.GetProfileCustomizationResponse = await self.ws.send_um_and_wait(
            player.GetProfileCustomizationRequest(
                steamid=user_id64,
                include_inactive_customizations=True,
                include_purchased_customizations=True,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_profile_items(self, language: Language | None) -> player.GetProfileItemsOwnedResponse:
        msg: player.GetProfileItemsOwnedResponse = await self.ws.send_um_and_wait(
            player.GetProfileItemsOwnedRequest(
                language=(language or self.language).api_name,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_user_levels(self, *user_ids: ID32) -> dict[ID32, int]:
        msg: client_server_2.CMsgClientFsGetFriendsSteamLevelsResponse = await self.ws.send_proto_and_wait(
            client_server_2.CMsgClientFsGetFriendsSteamLevels(list(user_ids))
        )
        if msg.result not in (Result.OK, Result.Invalid):
            raise WSException(msg)

        return cast(dict[ID32, int], {friend.accountid: friend.level for friend in msg.friends})

    async def fetch_user_favourite_badge(self, user_id64: ID64) -> player.GetFavoriteBadgeResponse:
        msg: player.GetFavoriteBadgeResponse = await self.ws.send_um_and_wait(
            player.GetFavoriteBadgeRequest(
                steamid=user_id64,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_friend_profile_info(self, user_id64: ID64) -> friends.CMsgClientFriendProfileInfoResponse:
        msg: friends.CMsgClientFriendProfileInfoResponse = await self.ws.send_proto_and_wait(
            friends.CMsgClientFriendProfileInfo(steamid_friend=user_id64)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_user_app_stats(self, user_id64: ID64, app_id: AppID) -> user_stats.CMsgClientGetUserStatsResponse:
        msg: user_stats.CMsgClientGetUserStatsResponse = await self.ws.send_proto_and_wait(
            user_stats.CMsgClientGetUserStats(steam_id_for_user=user_id64, game_id=app_id),
        )

        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_user_achievements(
        self, user_id64: ID64, *app_ids: AppID, language: Language | None
    ) -> list[player.GetAchievementsProgressResponseAchievementProgress]:
        msg: player.GetAchievementsProgressResponse = await self.ws.send_proto_and_wait(
            player.GetAchievementsProgressRequest(
                steamid=user_id64,
                appids=cast(list[int], list(app_ids)),
                language=(language or self.language).api_name,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.achievement_progress

    async def fetch_user_post(self, user_id64: ID64, post_id: PostID) -> player.GetPostedStatusResponse:
        msg: player.GetPostedStatusResponse = await self.ws.send_um_and_wait(
            player.GetPostedStatusRequest(
                steamid=user_id64,
                postid=post_id,
            )
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def create_user_post(self, content: str, app_id: AppID) -> None:
        msg: player.PostStatusToFriendsResponse = await self.ws.send_um_and_wait(
            player.PostStatusToFriendsRequest(appid=app_id, status_text=content)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def delete_user_post(self, post_id: PostID) -> None:
        msg: player.DeletePostedStatusResponse = await self.ws.send_um_and_wait(
            player.DeletePostedStatusRequest(
                postid=post_id,
            )
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_user_reviews(
        self, user_id64: ID64, app_ids: Iterable[AppID]
    ) -> list[reviews.RecommendationDetails]:
        msg: reviews.GetIndividualRecommendationsResponse = await self.ws.send_um_and_wait(
            reviews.GetIndividualRecommendationsRequest(
                [
                    reviews.GetIndividualRecommendationsRequestRecommendationRequest(steamid=user_id64, appid=app_id)
                    for app_id in app_ids
                ]
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.recommendations

    async def edit_review(
        self,
        review_id: int,
        content: str,
        public: bool,
        commentable: bool,
        language: str,
        is_in_early_access: bool,
        received_compensation: bool,
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            reviews.UpdateRequest(
                recommendationid=review_id,
                review_text=content,
                is_public=public,
                language=language,
                is_in_early_access=is_in_early_access,
                received_compensation=received_compensation,
                comments_disabled=not commentable,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def add_user(self, user_id64: ID64) -> None:
        msg: player.AddFriendResponse = await self.ws.send_proto_and_wait(player.AddFriendRequest(steamid=user_id64))
        if msg.result != Result.OK:
            raise WSException(msg)

    async def remove_user(self, user_id64: ID64) -> None:
        msg: player.RemoveFriendResponse = await self.ws.send_um_and_wait(player.RemoveFriendRequest(steamid=user_id64))
        if msg.result != Result.OK:
            raise WSException(msg)

    async def _block_user(self, user_id64: ID64, block: bool) -> None:
        msg: player.IgnoreFriendResponse = await self.ws.send_um_and_wait(
            player.IgnoreFriendRequest(steamid=user_id64, unignore=block)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def block_user(self, user_id64: ID64) -> None:
        await self._block_user(user_id64, False)

    async def unblock_user(self, user_id64: ID64) -> None:
        await self._block_user(user_id64, True)

    async def fetch_user_inventory(
        self, user_id64: ID64, app_id: AppID, context_id: ContextID, language: Language | None
    ) -> econ.GetInventoryItemsWithDescriptionsResponse:
        more_items = True
        original_msg = None
        start_asset_id = 0
        while more_items:
            msg: econ.GetInventoryItemsWithDescriptionsResponse = await self.ws.send_um_and_wait(
                econ.GetInventoryItemsWithDescriptionsRequest(
                    steamid=user_id64,
                    appid=app_id,
                    contextid=context_id,
                    get_descriptions=True,
                    language=(language or self.language).api_name,
                    count=2000,
                    start_assetid=start_asset_id,
                )
            )
            if msg.result == Result.AccessDenied:
                raise WSForbidden(msg)
            if msg.result != Result.OK:
                raise WSException(msg)

            if original_msg is None:
                original_msg = msg
            else:
                original_msg.assets += msg.assets
                original_msg.descriptions += msg.descriptions
            more_items = msg.more_items
            try:
                start_asset_id = msg.assets[-1].assetid
            except IndexError:
                break
        assert original_msg is not None
        return original_msg

    async def fetch_user_news(
        self,
        flags: UserNewsType,
        app_id: AppID | None,
        before: datetime,
        after: datetime,
        language: Language | None,
    ) -> user_news.GetUserNewsResponse:
        msg: user_news.GetUserNewsResponse = await self.ws.send_um_and_wait(
            user_news.GetUserNewsRequest(
                100,
                int(after.timestamp()),
                int(before.timestamp()),
                language=(language or self.language).api_name,
                filterflags=flags.flag,
                filterappid=app_id or 0,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    @parser
    @requires_intent(Intents.Users)
    async def parse_account_info(self, msg: login.CMsgClientAccountInfo) -> None:
        await self.login_complete.wait()
        if msg.persona_name != self.user.name:
            before = copy(self.user)
            self.user.name = msg.persona_name or self.user.name
            self.dispatch("user_update", before, self.user)

    async def fetch_servers(self, query: str, limit: int) -> list[game_servers.GetServerListResponseServer]:
        msg: game_servers.GetServerListResponse = await self.ws.send_um_and_wait(
            game_servers.GetServerListRequest(
                filter=query,
                limit=limit,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.servers

    async def fetch_server_ip_from_steam_id(self, *ids: ID64) -> list[game_servers.IPsWithSteamIDsResponseServer]:
        msg: game_servers.IPsWithSteamIDsResponse = await self.ws.send_um_and_wait(
            game_servers.GetServerIPsBySteamIdRequest(
                server_steamids=list(ids),
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.servers

    async def query_server(
        self, ip: int, port: int, app_id: AppID, type: game_servers.EQueryType
    ) -> game_servers.QueryResponse:
        msg: game_servers.QueryResponse = await self.ws.send_um_and_wait(
            game_servers.QueryRequest(
                query_type=type,
                fake_ip=ip,  # why these are "fake" I'm not really sure
                fake_port=port,
                app_id=app_id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    def get_group(self, id: ChatGroupID) -> Group | None:
        return self._groups.get(id)

    async def create_group(self, name: str, members: Iterable[IndividualID]) -> Group:
        msg: chat.CreateChatRoomGroupResponse = await self.ws.send_um_and_wait(
            chat.CreateChatRoomGroupRequest(name=name, steamid_invitees=[member.id64 for member in members])
        )
        group = Group(self, ChatGroupID(msg.chat_group_id))
        group._update_header_state(msg.state.header_state)
        group._update_channels(msg.state.chat_rooms, default_channel_id=msg.state.default_chat_id)
        group._update_group_state(msg.state)
        group._top_members = []
        group.active_member_count = 0
        return group

    def get_clan(self, id: ID32) -> Clan | None:
        return self._clans.get(id)

    async def fetch_clan(self, id64: ID64, *, maybe_chunk: bool = True, create: bool = False) -> Clan:
        msg: chat.GetClanChatRoomInfoResponse = await self.ws.send_um_and_wait(
            chat.GetClanChatRoomInfoRequest(steamid=id64, autocreate=create)
        )
        if msg.result == Result.Busy:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        clan = await Clan._from_proto(self, msg.chat_group_summary, maybe_chunk=maybe_chunk)
        self._clans[clan.id] = clan
        return clan

    async def _maybe_clan(self, id: ID64, *, create: bool = False) -> Clan:
        return self._clans.get(_ID64_TO_ID32(id)) or await self.fetch_clan(id, create=create)

    @cached_property
    def _chat_groups(self) -> utils.ChainMap[ChatGroupID, Group | Clan]:
        return utils.ChainMap(self._clans_by_chat_id, self._groups)  # type: ignore  # needs HKT

    async def join_chat_group(self, chat_group_id: ChatGroupID, invite_code: str | None = None) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.JoinChatRoomGroupRequest(chat_group_id=chat_group_id, invite_code=invite_code or "")
        )

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def leave_chat_group(self, chat_group_id: ChatGroupID) -> None:
        msg = await self.ws.send_um_and_wait(chat.LeaveChatRoomGroupRequest(chat_group_id=chat_group_id))

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def invite_user_to_chat_group(self, user_id64: ID64, chat_group_id: ChatGroupID) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.InviteFriendToChatRoomGroupRequest(chat_group_id=chat_group_id, steamid=user_id64)
        )

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def revoke_chat_group_invite(self, user_id64: ID64, chat_group_id: ChatGroupID) -> None:
        msg = await self.ws.send_um_and_wait(chat.RevokeInviteRequest(chat_group_id=chat_group_id, steamid=user_id64))
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def respond_to_clan_invite(self, clan_id64: ID64, accept: bool) -> None:
        msg: clan.RespondToClanInviteResponse = await self.ws.send_um_and_wait(
            clan.RespondToClanInviteRequest(steamid=clan_id64, accept=accept)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def rate_clan_announcement(self, clan_id: ID32, announcement_id: int, upvoted: bool) -> None:
        msg = await self.ws.send_um_and_wait(
            community.RateClanAnnouncementRequest(
                announcementid=announcement_id,
                clan_accountid=clan_id,
                vote_up=upvoted,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    @parser
    @requires_intent(Intents.ChatGroups)
    async def update_clan(self, msg: client_server.CMsgClientClanState) -> None:
        await self.handled_chat_groups.wait()
        steam_id = ID(msg.steamid_clan)
        clan = self.get_clan(steam_id.id) or await self.fetch_clan(steam_id.id64, maybe_chunk=False)

        for event in msg.events:
            if event.just_posted:
                event = await clan.fetch_event(event.gid)
                self.dispatch("event_create", event)
        for announcement in msg.announcements:
            if announcement.just_posted:
                announcement = await clan.fetch_announcement(announcement.gid)
                self.dispatch("announcement_create", announcement)

        user_counts = msg.user_counts
        name_info = msg.name_info
        flags_changed = clan.flags != msg.clan_account_flags
        dispatch_update = user_counts or name_info or flags_changed

        before = None
        if dispatch_update:
            before = copy(clan)
        if user_counts:
            clan.member_count = user_counts.members
            clan.in_game_count = user_counts.in_game
            clan.online_count = user_counts.online
            clan.active_member_count = user_counts.chatting
        if name_info:
            clan.name = name_info.clan_name
            clan._avatar_sha = name_info.sha_avatar
        if flags_changed:
            clan.flags = ClanAccountFlags.try_value(msg.clan_account_flags)

        if dispatch_update:
            assert before is not None
            self.dispatch("clan_update", before, clan)

    @requires_intent(Intents.ChatGroups)
    async def handle_get_my_chat_groups(self, msg: chat.GetMyChatRoomGroupsResponse) -> None:
        for chat_group in msg.chat_room_groups:
            if chat_group.group_summary.clanid:  # received a clan
                clan = await Clan._from_proto(self, chat_group.group_summary)
                clan._update_channels(
                    chat_group.user_chat_group_state.user_chat_room_state,
                    default_channel_id=chat_group.group_summary.default_chat_id,
                )
                self._clans[clan.id] = clan
                assert clan._id is not None
                self._clans_by_chat_id[clan._id] = clan
            else:  # else it's a group
                group = await Group._from_proto(self, chat_group.group_summary)
                group._update_channels(
                    chat_group.user_chat_group_state.user_chat_room_state,
                    default_channel_id=chat_group.group_summary.default_chat_id,
                )
                self._groups[group.id] = group

        self.handled_chat_groups.set()

    async def set_chat_group_active(self, chat_group_id: ChatGroupID) -> chat.GroupState:
        self.active_chat_groups.add(chat_group_id)
        proto: chat.SetSessionActiveChatRoomGroupsResponse = await self.ws.send_um_and_wait(
            chat.SetSessionActiveChatRoomGroupsRequest(
                chat_group_ids=list(self.active_chat_groups),
                chat_groups_data_requested=[chat_group_id],
            )
        )

        try:
            (state,) = proto.chat_states
        except ValueError:
            raise WSForbidden(proto) from None
        if proto.result != Result.OK:
            raise WSException(proto)

        return state

    async def edit_chat_group(
        self, chat_group_id: ChatGroupID, name: str | None, tagline: str | None, avatar: Media | None
    ) -> None:
        chat_group = self._chat_groups.get(chat_group_id)
        if name is not None:
            msg = await self.ws.send_um_and_wait(
                chat.RenameChatRoomGroupRequest(
                    chat_group_id=chat_group_id,
                    name=name,
                )
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)
            if chat_group is not None:
                chat_group.name = name
        if avatar is not None:
            sha = await self.http.upload_chat_icon(avatar)
            msg = await self.ws.send_um_and_wait(
                chat.SetChatRoomGroupAvatarRequest(
                    chat_group_id=chat_group_id,
                    avatar_sha=sha,
                )
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)
            if chat_group is not None:
                chat_group._avatar_sha = sha
        if tagline is not None:
            msg = await self.ws.send_um_and_wait(
                chat.SetChatRoomGroupTaglineRequest(
                    chat_group_id=chat_group_id,
                    tagline=tagline,
                )
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)
            if chat_group is not None:
                chat_group.tagline = tagline

    @requires_intent(Intents.ChatGroups)
    def handle_chat_group_update(self, msg: chat.ChatRoomHeaderStateNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.header_state.chat_group_id)]
        except KeyError:
            return log.debug("Updating a group that isn't cached %s", msg.header_state.chat_group_id)

        before = copy(chat_group)
        before._roles = {r_id: copy(r) for r_id, r in before._roles.items()}
        chat_group._update_header_state(msg.header_state)
        self.dispatch(f"{chat_group.__class__.__name__.lower()}_update", before, chat_group)

    @requires_intent(Intents.ChatGroups)
    async def handle_chat_group_user_action(self, msg: chat.NotifyChatGroupUserStateChangedNotification) -> None:
        if msg.user_action == chat.EChatRoomMemberStateChange.Joined:  # join group
            if msg.group_summary.clanid:
                clan = await Clan._from_proto(self, msg.group_summary)
                self._clans[clan.id] = clan
                assert clan._id is not None
                self._clans_by_chat_id[clan._id] = clan
                self.dispatch("clan_join", clan)
            else:
                group = await Group._from_proto(self, msg.group_summary)
                self._groups[group.id] = group
                self.dispatch("group_join", group)

        elif msg.user_action == chat.EChatRoomMemberStateChange.Parted:  # leave group
            left = self._chat_groups.pop(ChatGroupID(msg.chat_group_id), None)
            if left is None:
                return

            self.dispatch(f"{left.__class__.__name__.lower()}_leave", left)
        # elif msg.user_action == chat.EChatRoomMemberStateChange.Invited:
        #     if msg.group_summary.clanid:
        #         return
        #     group = await Group._from_proto(self, msg.group_summary)
        #     self._groups[group.id] = group
        #     self.dispatch("group_invite", group)

    @requires_intent(Intents.ChatGroups | Intents.Users)
    async def handle_chat_member_update(self, msg: chat.MemberStateChangeNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got a chat member update for a chat group we aren't in %d", msg.chat_group_id)

        match msg.change:
            case chat.EChatRoomMemberStateChange.Joined:
                member = await chat_group._add_member(msg.member)
                return self.dispatch("member_join", member)
            case (
                chat.EChatRoomMemberStateChange.Parted
                | chat.EChatRoomMemberStateChange.Kicked
                | chat.EChatRoomMemberStateChange.Banned
            ):
                member = chat_group._remove_member(msg.member)
                if member is None:
                    return
                member.kick_expires_at = DateTime.from_timestamp(msg.member.time_kick_expire)
                name = {
                    chat.EChatRoomMemberStateChange.Parted: "member_leave",
                    chat.EChatRoomMemberStateChange.Kicked: "member_kick",
                    chat.EChatRoomMemberStateChange.Banned: "member_ban",
                }[msg.change]
                return self.dispatch(name, member)
            case chat.EChatRoomMemberStateChange.Invited | chat.EChatRoomMemberStateChange.InviteDismissed:
                return  # handled in handle_chat_server_message

        id = ID32(msg.member.accountid)
        member = chat_group._maybe_member(id)
        if msg.change == chat.EChatRoomMemberStateChange.Muted:
            return self.dispatch("member_mute", member)

        before = copy(member)
        match msg.change:
            case chat.EChatRoomMemberStateChange.RankChanged:
                member.rank = ChatMemberRank.try_value(int(msg.member.rank))
                if member.rank is ChatMemberRank.Moderator:
                    chat_group._mods.append(id)
                    try:
                        chat_group._officers.remove(id)
                    except ValueError:
                        pass
                elif member.rank is ChatMemberRank.Officer:
                    chat_group._officers.append(id)
                    try:
                        chat_group._mods.remove(id)
                    except ValueError:
                        pass
            case chat.EChatRoomMemberStateChange.RolesChanged:
                member._role_ids = cast(tuple[RoleID, ...], tuple(msg.member.role_ids))

        self.dispatch("member_update", before, member)

    async def fetch_chat_group_members(
        self,
        chat_group_id: ChatGroupID,
        view_id: int,
        client_change_number: int,
        start: int,
        stop: int,
    ) -> list[User]:
        fut = self.ws.wait_for(
            chat.MemberListViewUpdatedNotification,
            check=lambda msg: (
                isinstance(msg, chat.MemberListViewUpdatedNotification)
                and msg.view_id == view_id
                and msg.view.client_changenumber == client_change_number
            ),
        )
        await self.ws.send_proto(  # send_um isn't used as job_id doesn't do anything
            chat.UpdateMemberListViewNotification(
                chat_group_id=chat_group_id,
                view_id=view_id,
                start=start,
                end=stop,
                client_changenumber=client_change_number,
            )
        )
        msg = await fut
        return [self._store_user(member.persona) for member in msg.members]

    async def mute_chat_group_member(self, chat_group_id: ChatGroupID, user_id64: ID64, expires_at: datetime) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.MuteUserRequest(
                chat_group_id=chat_group_id,
                steamid=user_id64,
                expiration=int(expires_at.timestamp()),
            )
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def kick_chat_group_member(self, chat_group_id: ChatGroupID, user_id64: ID64, expires_at: datetime) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.KickUserRequest(
                chat_group_id=chat_group_id,
                steamid=user_id64,
                expiration=int(expires_at.timestamp()),
            )
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def set_chat_group_ban_state(self, chat_group_id: ChatGroupID, user_id64: ID64, banned: bool) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.SetUserBanStateRequest(
                chat_group_id=chat_group_id,
                steamid=user_id64,
                ban_state=banned,
            )
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def create_role(self, chat_group_id: ChatGroupID, name: str) -> Role:
        msg: chat.CreateRoleResponse = await self.ws.send_um_and_wait(
            chat.CreateRoleRequest(
                chat_group_id=chat_group_id,
                name=name,
            )
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)
        roles = await self.fetch_chat_group_roles(chat_group_id)
        role = utils.get(roles, id=msg.actions.role_id)
        assert role is not None
        return Role(self, self._chat_groups[chat_group_id], role, msg.actions)

    async def edit_role(
        self,
        chat_group_id: ChatGroupID,
        role_id: RoleID,
        name: str | None,
        permissions: RolePermissions | None,
        ordinal: int | None,
    ) -> None:
        if name is not None:
            msg = await self.ws.send_um_and_wait(
                chat.RenameRoleRequest(chat_group_id=chat_group_id, role_id=role_id, name=name)
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)
        if permissions is not None:
            msg = await self.ws.send_um_and_wait(
                chat.ReplaceRoleActionsRequest(
                    chat_group_id=chat_group_id,
                    role_id=role_id,
                    actions=permissions.to_proto(),
                )
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)
        if ordinal is not None:
            msg = await self.ws.send_um_and_wait(
                chat.ReorderRoleRequest(chat_group_id=chat_group_id, role_id=role_id, ordinal=ordinal)
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)

    async def delete_role(self, chat_group_id: ChatGroupID, role_id: RoleID) -> None:
        msg = await self.ws.send_um_and_wait(chat.DeleteRoleRequest(chat_group_id=chat_group_id, role_id=role_id))
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def create_chat(self, chat_group_id: ChatGroupID, name: str) -> chat.State:
        msg: chat.CreateChatRoomResponse = await self.ws.send_um_and_wait(
            chat.CreateChatRoomRequest(chat_group_id=chat_group_id, name=name)
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)
        return msg.chat_room

    @requires_intent(Intents.ChatGroups | Intents.Chat)
    def handle_chat_update(self, msg: chat.ChatRoomGroupRoomsChangeNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got an update for a chat group we aren't in %d", msg.chat_group_id)

        before = copy(chat_group)
        before._channels = {c_id: copy(c) for c_id, c in before._channels.items()}  # type: ignore  # needs conditional types
        chat_group._update_channels(msg.chat_rooms)
        self.dispatch(f"{chat_group.__class__.__name__.lower()}_update", before, chat_group)

    async def edit_chat(
        self,
        chat_group_id: ChatGroupID,
        chat_id: ChatID,
        name: str | None,
        after_chat_id: ChatID | None,
    ) -> None:
        if name is not None:
            msg = await self.ws.send_um_and_wait(
                chat.RenameChatRoomRequest(chat_group_id=chat_group_id, chat_id=chat_id, name=name)
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)
        if after_chat_id is not None:
            msg = await self.ws.send_um_and_wait(
                chat.ReorderChatRoomRequest(
                    chat_group_id=chat_group_id, chat_id=chat_id, move_after_chat_id=after_chat_id
                )
            )
            if msg.result == Result.InvalidParameter:
                raise WSNotFound(msg)
            elif msg.result != Result.OK:
                raise WSException(msg)

    async def delete_chat(self, chat_group_id: ChatGroupID, chat_id: ChatID) -> None:
        msg = await self.ws.send_um_and_wait(chat.DeleteChatRoomRequest(chat_group_id=chat_group_id, chat_id=chat_id))
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    def handle_chat_server_message(
        self, chat_group: Clan | Group, author: ClanMember | GroupMember | PartialMember, msg: chat.ServerMessage
    ) -> None:
        if self.intents & Intents.Users & Intents.Chat > 0:
            return
        user_id = ID32(msg.accountid_param)
        match msg.message:
            case chat.EChatRoomServerMessage.Invited:
                invite = chat_group._invites[user_id] = (
                    ClanInvite(
                        self,
                        chat_group._get_partial_member(user_id),
                        author,
                        FriendRelationship.RequestRecipient,
                        clan=chat_group,
                    )
                    if isinstance(chat_group, Clan)
                    else GroupInvite(
                        self,
                        chat_group._get_partial_member(user_id),
                        author,
                        FriendRelationship.RequestRecipient,
                        group=chat_group,
                    )
                )
                self.dispatch("invite", invite)
            case chat.EChatRoomServerMessage.Joined:
                invite = chat_group._invites.pop(user_id, None)
                if invite is not None:
                    self.dispatch("invite_accept", invite)

    @requires_intent(Intents.ChatGroups | Intents.Chat | Intents.Messages | Intents.Users)
    def handle_chat_message(self, msg: chat.IncomingChatMessageNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got a message for a chat we aren't in %s", msg.chat_group_id)

        channel = chat_group._channels[ChatID(msg.chat_id)]
        channel._update(msg)
        author = chat_group._maybe_member(_ID64_TO_ID32(msg.steamid_sender))
        if msg.server_message:
            return self.handle_chat_server_message(chat_group, author, msg.server_message)

        message_cls, *_ = channel._type_args
        message = message_cls(
            proto=msg,
            channel=channel,  # type: ignore  # type checkers aren't able to figure out this is ok
            author=author,
        )
        channel.last_message = message  # type: ignore  # same as above
        self._messages.append(message)
        self.dispatch("message", message)

    async def send_chat_message(
        self, chat_group_id: ChatGroupID, chat_id: ChatID, content: str
    ) -> ClanMessage | GroupMessage:
        msg: chat.SendChatMessageResponse = await self.ws.send_um_and_wait(
            chat.SendChatMessageRequest(
                chat_id=chat_id,
                chat_group_id=chat_group_id,
                message=content.replace("\\", "\\\\"),
            )
        )

        if msg.result == Result.LimitExceeded:
            raise WSForbidden(msg)
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        proto = chat.IncomingChatMessageNotification(
            chat_id=chat_id,
            chat_group_id=chat_group_id,
            message=msg.modified_message,
            ordinal=msg.ordinal,
            message_no_bbcode=msg.message_without_bb_code,
            timestamp=msg.server_timestamp,
        )
        group = self._chat_groups[chat_group_id]
        channel = group._channels[chat_id]
        channel._update(proto)
        message_cls, *_ = channel._type_args
        message = message_cls(
            proto=proto,
            channel=channel,  # type: ignore  # type checkers can't figure out this is ok
            author=group.me,
        )
        channel.last_message = message  # type: ignore  # same as above
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def delete_chat_messages(
        self, chat_group_id: ChatGroupID, chat_id: ChatID, *messages: tuple[int, int]
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.DeleteChatMessagesRequest(
                chat_id=chat_id,
                chat_group_id=chat_group_id,
                messages=[
                    chat.DeleteChatMessagesRequestMessage(server_timestamp=timestamp, ordinal=ordinal)
                    for timestamp, ordinal in messages
                ],
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def ack_chat_message(self, chat_group_id: ChatGroupID, chat_id: ChatID, timestamp: int) -> None:
        await self.ws.send_proto(
            chat.AckChatMessageNotification(chat_group_id=chat_group_id, chat_id=chat_id, timestamp=timestamp)
        )

    async def fetch_chat_history(
        self, chat_group_id: ChatGroupID, chat_id: ChatID, start: int, last: int, last_ordinal: int
    ) -> chat.GetMessageHistoryResponse:
        msg: chat.GetMessageHistoryResponse = await self.ws.send_um_and_wait(
            chat.GetMessageHistoryRequest(
                chat_group_id=chat_group_id,
                chat_id=chat_id,
                last_time=last,
                start_time=start,
                last_ordinal=last_ordinal,
                max_count=100,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    @requires_intent(Intents.ChatGroups | Intents.Chat | Intents.Messages | Intents.Users)
    def handle_chat_message_reaction(self, msg: chat.MessageReactionNotification) -> None:
        try:
            destination = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got a message reaction for a chat we aren't in %s", msg.chat_group_id)
        ordinal = msg.ordinal
        created_at = DateTime.from_timestamp(msg.server_timestamp)
        location = (destination._id, msg.chat_id)
        message = utils.find(
            lambda message: (
                isinstance(message, (ClanMessage, GroupMessage))
                and message.channel._location == location
                and message.created_at == created_at
                and message.ordinal == ordinal
            ),
            reversed(self._messages),
        )
        if message is None:
            return log.debug(
                "Got a reaction to an unknown message %s %s (location %s)",
                created_at,
                ordinal,
                location,
            )
        match msg.reaction_type:
            case Emoticon._TYPE:
                reaction = MessageReaction(
                    self,
                    message,
                    Emoticon(self, msg.reaction),
                    None,
                    destination._maybe_member(_ID64_TO_ID32(msg.reactor)),
                    created_at,
                    ordinal,
                )
            case Sticker._TYPE:
                reaction = MessageReaction(
                    self,
                    message,
                    None,
                    Sticker(self, msg.reaction),
                    destination._maybe_member(_ID64_TO_ID32(msg.reactor)),
                    created_at,
                    ordinal,
                )
            case _:
                return log.debug("Got an unknown reaction_type %s", msg.reaction_type)

        if msg.is_add:
            message.reactions.append(reaction)
        else:
            try:
                message.reactions.remove(reaction)
            except ValueError:
                log.debug("Got a reaction remove for a reaction that wasn't added")

        self.dispatch(f"reaction_{'add' if msg.is_add else 'remove'}", reaction)

    async def react_to_chat_message(
        self,
        chat_group_id: ChatGroupID,
        chat_id: ChatID,
        server_timestamp: int,
        ordinal: int,
        reaction_name: str,
        reaction_type: chat.EChatRoomMessageReactionType,
        is_add: bool,
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.UpdateMessageReactionRequest(
                chat_group_id=chat_group_id,
                chat_id=chat_id,
                server_timestamp=server_timestamp,
                ordinal=ordinal,
                reaction=reaction_name,
                reaction_type=reaction_type,
                is_add=is_add,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_message_reactors(
        self,
        chat_group_id: ChatGroupID,
        chat_id: ChatID,
        server_timestamp: int,
        ordinal: int,
        reaction_name: str,
        reaction_type: chat.EChatRoomMessageReactionType,
    ) -> list[ID32]:
        msg: chat.GetMessageReactionReactorsResponse = await self.ws.send_um_and_wait(
            chat.GetMessageReactionReactorsRequest(
                chat_group_id=chat_group_id,
                chat_id=chat_id,
                server_timestamp=server_timestamp,
                ordinal=ordinal,
                reaction=reaction_name,
                reaction_type=reaction_type,
                limit=0xFFFFFFFF,
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return cast("list[ID32]", msg.reactors)

    async def fetch_trade_url(self, generate_new: bool) -> str:
        msg: econ.GetTradeOfferAccessTokenResponse = await self.ws.send_um_and_wait(
            econ.GetTradeOfferAccessTokenRequest(generate_new_token=generate_new)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return str(URL.COMMUNITY / "tradeoffer/new" % {"partner": self.user.id, "token": msg.trade_offer_access_token})

    def get_trade(self, id: TradeOfferID) -> TradeOffer | None:
        return self._trades.get(id)

    async def fetch_trade(
        self, id: TradeOfferID, language: Language | None
    ) -> TradeOffer[Item[User], Item[ClientUser], User] | None:
        try:
            data = await self.http.get_trade(id, language)
        except KeyError:
            pass
        else:
            (trade,) = await self._process_trades(
                (data["offer"],),
                {
                    (description["classid"], description["instanceid"]): econ.ItemDescription().from_dict(description)
                    for description in data.get("descriptions", ())
                },
            )
            return trade

    async def _process_trades(
        self, trades_: Iterable[trade.TradeOffer], descriptions: dict[tuple[str, str], econ.ItemDescription]
    ) -> list[TradeOffer[Item[User], Item[ClientUser], User]]:
        trades: list[TradeOffer[Item[User], Item[ClientUser], User]] = []
        dispatch: list[tuple[Any, ...]] = []  # my brain doesn't have the power to type this correctly
        for trade_ in trades_:
            id = TradeOfferID(int(trade_["tradeofferid"]))
            user = trade_["accountid_other"]
            try:
                receiving = [
                    (econ.Asset().from_dict(asset), descriptions[asset["classid"], asset["instanceid"]])
                    for asset in trade_.get("items_to_receive", ())
                ]
                sending = [
                    (econ.Asset().from_dict(asset), descriptions[asset["classid"], asset["instanceid"]])
                    for asset in trade_.get("items_to_give", ())
                ]
            except KeyError:
                receiving = [econ.Asset().from_dict(asset) for asset in trade_.get("items_to_receive", ())]
                sending = [econ.Asset().from_dict(asset) for asset in trade_.get("items_to_give", ())]

            try:
                trade = self._trades[id]
            except KeyError:
                log.info("Received trade #%d", id)
                trade = TradeOffer._from_api(
                    state=self,
                    data=trade_,
                    user=cast(User, ID(user)),
                    sending=cast("list[tuple[econ.Asset, econ.ItemDescription]]", sending),
                    receiving=cast("list[tuple[econ.Asset, econ.ItemDescription]]", receiving),
                )
                self._trades[id] = trade
                if trade.state in (TradeOfferState.Active, TradeOfferState.ConfirmationNeed) and (
                    trade.sending or trade.receiving
                ):  # could be glitched
                    dispatch.append(("trade", trade))
                    self._trades_to_watch.add(trade.id)
            else:
                before = copy(trade)
                trade._update(trade_, sending=sending, receiving=receiving)  # type: ignore  # I cba fixing this
                if trade.state != before.state:
                    log.info("Trade #%d has updated its trade state to %r", id, trade.state)
                    if trade.sending or trade.receiving:
                        dispatch.append(("trade_update", before, trade))
                        self._trades_to_watch.discard(trade.id)
            trades.append(trade)

        for trade, user in zip(trades, await self._maybe_users(trade.user.id64 for trade in trades)):
            if trade.user is not user:  # should only have been fetched if _from_api
                for item in trade.receiving:
                    item.owner = user
            trade.user = user

        for args in dispatch:
            self.dispatch(*args)

        return trades

    @requires_intent(Intents.TradeOffers)
    @call_once
    async def poll_trades(self) -> None:
        await self.fill_trades()
        await asyncio.sleep(5)  # preventative measure against notification spam making us excessively poll

        while self._trades_to_watch:  # watch trades for changes
            await self.fill_trades()
            await asyncio.sleep(10)

    async def fill_trades(self) -> None:
        try:
            trades = await self.http.get_trade_offers()
        except HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(300)
                return await self.fill_trades()
            raise
        descriptions = {
            (description["classid"], description["instanceid"]): econ.ItemDescription().from_dict(description)
            for description in trades.get("descriptions", ())
        }
        self.trade_queue += await self._process_trades(trades.get("trade_offers_received", ()), descriptions)
        self.trade_queue += await self._process_trades(trades.get("trade_offers_sent", ()), descriptions)

    async def wait_for_trade(self, id: TradeOfferID) -> TradeOffer[Item[User], Item[ClientUser], User]:
        self._trades_to_watch.add(id)
        self._tg.create_task(self.poll_trades())  # start re-polling trades
        return await self.trade_queue.wait_for(id=id)

    @parser
    async def parse_new_items(self, msg: client_server_2.CMsgClientItemAnnouncements) -> None:
        if msg.count_new_items:
            await self.poll_trades()

    def get_confirmation(self, id: TradeOfferID) -> Confirmation | None:
        return self._confirmations.get(id)

    async def fill_confirmations(self) -> None:
        key, timestamp = await self._get_confirmation_code("list")
        try:
            data = await self.http.get(
                URL.COMMUNITY / "mobileconf/getlist",
                params={
                    "p": self._device_id,
                    "a": self.user.id64,
                    "k": key,
                    "t": timestamp,
                    "m": "react",
                    "tag": "list",
                },
            )
        except HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(300)
                return await self.fill_confirmations()
            raise
        if not data.get("success", False):
            raise ConfirmationError(f"{data.get('message', 'Unknown error')}\n{data.get('detail', '')}".strip())

        confirmations: list[Confirmation] = []
        for confirmation in data["conf"]:
            confirmation_ = Confirmation(
                self, int(confirmation["id"]), int(confirmation["nonce"]), TradeOfferID(int(confirmation["creator_id"]))
            )
            self._confirmations[confirmation_.creator_id] = confirmation_
            confirmations.append(confirmation_)
        self.confirmation_queue += confirmations

    @cached_property
    def identity_secret(self) -> str:
        if (secret := self.client.identity_secret) is None:
            raise ValueError("Cannot generate confirmation codes without passing an identity_secret")
        return secret

    async def _get_confirmation_code(self, tag: Tags) -> tuple[str, int]:
        # generate a confirmation code for a given tag at this instant.
        # this can wait x amount of time (<1s) for the code to be generated if codes would collide as they can only be
        # used once.
        lock = self.confirmation_generation_locks[tag]
        await lock.acquire()

        steam_time = self.steam_time
        timestamp = int(steam_time.timestamp())
        try:
            return get_confirmation_code(self.identity_secret, tag, timestamp), timestamp
        finally:
            # wait for the next second whole before allowing generation of a new confirmation code
            next_code_valid_at = steam_time.replace(microsecond=0) + timedelta(seconds=1)  # ceiling + 1 second
            asyncio.get_running_loop().call_later((next_code_valid_at - steam_time).total_seconds(), lock.release)

    async def poll_confirmations(self) -> None:
        if self.polling_confirmations:
            return

        self.polling_confirmations = True
        try:
            await self.fill_confirmations()

            while self.confirmation_queue.queue:
                await asyncio.sleep(20)
                await self.fill_confirmations()
        finally:
            self.polling_confirmations = False

    async def wait_for_confirmation(self, id: TradeOfferID) -> Confirmation:
        self._tg.create_task(self.poll_confirmations())
        return await self.confirmation_queue.wait_for(id=id)

    async def _fetch_store_info(
        self, ids: list[store.StoreItemId], language: Language | None = None
    ) -> list[store.StoreItem]:
        msg: store.GetItemsResponse = await self.ws.send_proto_and_wait(
            store.GetItemsRequest(
                ids=ids,
                context=store.StoreBrowseContext(
                    country_code=(language or self.language).web_api_name,
                ),
                data_request=store.StoreBrowseItemDataRequest(
                    include_assets=True,
                    include_release=True,
                    include_platforms=True,
                    include_all_purchase_options=True,
                    include_screenshots=True,
                    include_trailers=True,
                    include_ratings=True,
                    include_tag_count=True,
                    include_reviews=True,
                    include_basic_info=True,
                    include_supported_languages=True,
                ),
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.store_items

    async def fetch_store_info(
        self,
        app_ids: Iterable[AppID] = (),
        package_ids: Iterable[PackageID] = (),
        bundle_ids: Iterable[BundleID] = (),
        language: Language | None = None,
    ) -> list[store.StoreItem]:
        ids = (
            [store.StoreItemId(appid=app_id) for app_id in app_ids]
            + [store.StoreItemId(packageid=package_id) for package_id in package_ids]
            + [store.StoreItemId(bundleid=bundle_id) for bundle_id in bundle_ids]
        )
        return await self._fetch_store_info(ids, language)

    async def fetch_app_tag(self, *tag_ids: int, language: Language | None = None) -> list[store.StoreItem]:
        return await self._fetch_store_info([store.StoreItemId(tagid=tag_id) for tag_id in tag_ids], language)

    async def fetch_app_categories(self, *category_ids: int, language: Language | None = None) -> list[store.StoreItem]:
        return await self._fetch_store_info(
            [store.StoreItemId(hubcategoryid=category_id) for category_id in category_ids], language
        )

    async def fetch_app(self, app_id: AppID, language: Language | None) -> FetchedApp:
        resp = await self.http.get_app(app_id, language)
        data = resp[str(app_id)]
        if data["success"]:
            return FetchedApp(self, data["data"], language or self.language)
        raise ValueError("app_id is invalid")

    async def fetch_app_player_count(self, app_id: AppID) -> int:
        msg: client_server_2.CMsgDpGetNumberOfCurrentPlayersResponse = await self.ws.send_proto_and_wait(
            client_server_2.CMsgDpGetNumberOfCurrentPlayers(appid=app_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.player_count

    async def fetch_app_achievements(
        self, app_id: AppID, language: Language | None
    ) -> list[player.GetGameAchievementsResponseAchievement]:
        msg: player.GetGameAchievementsResponse = await self.ws.send_proto_and_wait(
            player.GetGameAchievementsRequest(appid=app_id, language=(language or self.language).api_name)
        )

        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.achievements

    async def fetch_or_create_app_leaderboard(
        self, app_id: AppID, leaderboard_name: str, create: bool = False
    ) -> leaderboards.CMsgClientLbsFindOrCreateLbResponse:
        msg: leaderboards.CMsgClientLbsFindOrCreateLbResponse = await self.ws.send_proto_and_wait(
            leaderboards.CMsgClientLbsFindOrCreateLb(
                app_id=app_id, leaderboard_name=leaderboard_name, create_if_not_found=create
            ),
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_app_leaderboard_entries(
        self,
        app_id: AppID,
        leaderboard_id: int,
        start: int,
        stop: int,
        leaderboard_data_request: int,
        id64s: list[ID64],
    ) -> list[leaderboards.CMsgClientLbsGetLbEntriesResponseEntry]:
        try:
            async with timeout(15):
                msg: leaderboards.CMsgClientLbsGetLbEntriesResponse = await self.ws.send_proto_and_wait(
                    leaderboards.CMsgClientLbsGetLbEntries(
                        leaderboard_id=leaderboard_id,
                        app_id=app_id,
                        range_start=start,
                        range_end=stop,
                        leaderboard_data_request=leaderboard_data_request,
                        steamids=cast("list[int]", id64s),
                    ),
                )
        except asyncio.TimeoutError:
            raise WSNotFound(leaderboards.CMsgClientLbsGetLbEntriesResponse(eresult=Result.NoMatch)) from None
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.entries

    async def set_app_leaderboard_score(
        self,
        app_id: AppID,
        leaderboard_id: LeaderboardID,
        score: int,
        details: bytes,
        method: LeaderboardUploadScoreMethod,
    ) -> leaderboards.CMsgClientLbsSetScoreResponse:
        msg: leaderboards.CMsgClientLbsSetScoreResponse = await self.ws.send_proto_and_wait(
            leaderboards.CMsgClientLbsSetScore(
                app_id=app_id,
                leaderboard_id=leaderboard_id,
                score=score,
                details=details,
                upload_score_method=method,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def set_app_leaderboard_ugc(self, app_id: AppID, leaderboard_id: LeaderboardID, ugc_id: int) -> None:
        msg: leaderboards.CMsgClientLbsSetUgcResponse = await self.ws.send_proto_and_wait(
            leaderboards.CMsgClientLbsSetUgc(
                app_id=app_id,
                leaderboard_id=leaderboard_id,
                ugc_id=ugc_id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_community_item_definitions(
        self, app_id: AppID, item_type: CommunityDefinitionItemType, language: Language | None
    ) -> list[quest.GetCommunityItemDefinitionsResponseItemDefinition]:
        msg: quest.GetCommunityItemDefinitionsResponse = await self.ws.send_um_and_wait(
            quest.GetCommunityItemDefinitionsRequest(
                appid=app_id, item_type=item_type, language=(language or self.language).name, keyvalues_as_json=True
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.item_definitions

    async def fetch_reward_items(self, app_id: AppID, language: Language | None) -> list[loyalty_rewards.Definition]:
        msg: loyalty_rewards.QueryRewardItemsResponse = await self.ws.send_um_and_wait(
            loyalty_rewards.QueryRewardItemsRequest(appids=[app_id], language=(language or self.language).name)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.definitions

    async def fetch_friend_thoughts(self, app_id: AppID) -> reviews.GetFriendsRecommendedAppResponse:
        msg: reviews.GetFriendsRecommendedAppResponse = await self.ws.send_um_and_wait(
            reviews.GetFriendsRecommendedAppRequest(appid=app_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_friends_who_own(self, app_id: AppID) -> list[ID64]:
        msg: friends.ClientGetFriendsWhoPlayGameResponse = await self.ws.send_proto_and_wait(
            friends.ClientGetFriendsWhoPlayGame(app_id=app_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return cast(list[ID64], msg.friends)

    @asynccontextmanager
    async def hold_licenses(self) -> AsyncGenerator[None, None]:
        async with self._license_lock:
            self.handled_licenses.clear()
            yield
            await self.handled_licenses.wait()

    @parser
    async def handle_licenses(self, msg: client_server.CMsgClientLicenseList) -> None:
        await self.login_complete.wait()
        users: dict[int, User] = {
            user.id: user
            for user in await self._maybe_users(
                parse_id64(license.owner_id, type=Type.Individual) for license in msg.licenses
            )
        }
        for license in msg.licenses:
            self.licenses[license_.id] = (license_ := License(self, license, users[license.owner_id]))
            if future := self.licenses_being_waited_for.get(license_.id):
                future.set_result(license_)

        self.handled_licenses.set()

    async def request_free_licenses(self, *app_ids: AppID) -> dict[AppID, list[License]]:
        async with self.hold_licenses():
            msg: client_server_2.CMsgClientRequestFreeLicenseResponse = await self.ws.send_proto_and_wait(
                client_server_2.CMsgClientRequestFreeLicense(appids=list(app_ids)),
            )
            if msg.result != Result.OK:
                raise WSException(msg)
            if any(app_id not in msg.granted_appids for app_id in app_ids):
                raise WSNotFound(msg)
            if not msg.granted_packageids:
                raise ValueError("No licenses granted")

        ret: dict[AppID, list[License]] = {app_id: [] for app_id in cast(list[AppID], msg.granted_appids)}
        _, packages = await self.fetch_product_info((), cast(list[PackageID], msg.granted_packageids))
        for package in packages:
            for app in await package.apps():
                try:
                    ret[app.id].append(self.licenses[package.id])
                except KeyError:
                    pass
        return ret

    async def fetch_legacy_cd_key(self, app_id: AppID) -> str:
        msg: client_server_2.ClientGetLegacyGameKeyResponse = await self.ws.send_proto_and_wait(
            client_server_2.ClientGetLegacyGameKeyRequest(app_id=app_id),
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.legacy_game_key

    async def register_cd_key(self, key: str) -> store.PurchaseReceiptInfo:
        msg: store.RegisterCDKeyResponse = await self.ws.send_um_and_wait(
            store.RegisterCDKeyRequest(activation_code=key)
        )
        if msg.result != Result.OK:
            msg.header.error_message += (
                f"\nPurchase result {PurchaseResult.try_value(msg.purchase_receipt_info.result_detail)!r}"
            )
            msg.header.error_message = msg.header.error_message.strip()
            raise WSException(msg)
        return msg.purchase_receipt_info

    async def fetch_encrypted_app_ticket(
        self, app_id: AppID, user_data: bytes
    ) -> encrypted_app_ticket.EncryptedAppTicket:
        msg: client_server.CMsgClientRequestEncryptedAppTicketResponse = await self.ws.send_proto_and_wait(
            client_server.CMsgClientRequestEncryptedAppTicket(app_id=app_id, userdata=user_data),
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.encrypted_app_ticket

    async def fetch_app_ownership_ticket(self, app_id: AppID) -> bytes:
        msg: client_server.CMsgClientGetAppOwnershipTicketResponse = await self.ws.send_proto_and_wait(
            client_server.CMsgClientGetAppOwnershipTicket(app_id=app_id),
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.ticket

    @parser
    def handle_game_connect_tokens(self, msg: client_server.CMsgClientGameConnectTokens) -> None:
        self._game_connect_bytes += msg.tokens

    @asynccontextmanager
    async def temporarily_play(self, *apps: App) -> AsyncGenerator[None, None]:
        old_apps = self._apps
        to_proto_apps = [app.to_proto() for app in apps]
        if all(app in old_apps for app in to_proto_apps):
            yield
            return

        try:
            await self.ws.change_presence(apps=[*self._apps, *to_proto_apps])
            yield
        finally:
            await self.ws.change_presence(apps=old_apps)

    async def activate_auth_session_tickets(self, *tickets: AuthenticationTicket) -> None:
        for ticket in tickets:
            if not ticket.is_valid():
                raise ValueError(f"Ticket {ticket!r} is not valid")

            if (ticket.app.id, ticket.user.id64) in self._active_auth_tickets:
                log.debug("Ticket %r is already active", ticket)

                if ticket.user != self.user:
                    log.info("Canceling existing ticket %r", ticket)
            self._active_auth_tickets[ticket.app.id, ticket.user.id64] = ticket
        await self.send_auth_list()

    async def deactivate_auth_session_tickets(self, *tickets: AuthenticationTicket) -> None:
        assert tickets
        for ticket in tickets:
            try:
                del self._active_auth_tickets[ticket.app.id, ticket.user.id64]
            except KeyError:
                log.debug("Ticket %r is not active", ticket)

        if ticket.user == self.user:  # type: ignore  # ticket cannot be unbound
            return  # can't deactivate our own ticket?
        await self.send_auth_list()

    async def send_auth_list(self, force_app_id: AppID | None = None) -> None:
        unique_app_ids = {app_id for app_id, _ in self._active_auth_tickets}
        if force_app_id is not None:
            unique_app_ids.add(force_app_id)
        log.info("Sending authentication list with %s active tickets", len(self._active_auth_tickets))

        msg: client_server.CMsgClientAuthListAck = await self.ws.send_proto_and_wait(
            client_server.CMsgClientAuthList(
                tokens_left=len(self._game_connect_bytes),
                last_request_seq=self._auth_seq_me,
                last_request_seq_from_server=self._auth_seq_them,
                app_ids=list(unique_app_ids),
                message_sequence=self._auth_seq_me + 1,
                tickets=[
                    client_server.CMsgAuthTicket(
                        estate=int(self.user != ticket.user),
                        steamid=0 if self.user == ticket.user else ticket.user.id64,
                        gameid=ticket.app.id,
                        h_steam_pipe=self._h_steam_pipe,
                        ticket_crc=crc32(ticket.auth_ticket),
                        ticket=ticket.auth_ticket,
                    )
                    for ticket in self._active_auth_tickets.values()
                ],
            ),
            check=lambda msg: (
                isinstance(msg, client_server.CMsgClientAuthListAck) and msg.message_sequence == self._auth_seq_me + 1
            ),
        )
        self._auth_seq_me += 1
        self._auth_seq_them = msg.message_sequence

    @parser
    def handle_ticket_auth_complete(self, msg: client_server.CMsgClientTicketAuthComplete) -> None:
        ticket = utils.find(
            lambda ticket: crc32(ticket.auth_ticket) == msg.ticket_crc, self._active_auth_tickets.values()
        )
        if ticket is None:
            return log.info("Got auth complete for unknown ticket %r discarding", msg.ticket_crc)

        if msg.eauth_session_response != AuthSessionResponse.OK:
            del self._active_auth_tickets[ticket.app.id, ticket.user.id64]
            log.info(
                "Removed canceled ticket %r with state %s. Now have %s active tickets.",
                ticket,
                msg.eauth_session_response,
                len(self._active_auth_tickets),
            )

        self.dispatch(
            "authentication_ticket_update",
            ticket,
            AuthSessionResponse.try_value(msg.eauth_session_response),
            msg.estate,
        )

    async def fetch_package(self, package_id: PackageID, language: Language | None) -> FetchedPackage:
        resp = await self.http.get_package(package_id, language)
        data = resp[str(package_id)]
        if data["success"]:
            return FetchedPackage(self, data["data"])
        raise ValueError("package_id is invalid")

    async def fetch_bundle(self, bundle_id: BundleID, language: Language | None) -> FetchedBundle:
        (data,) = await self.http.get_bundle(bundle_id, language)
        return FetchedBundle(self, data)

    async def fetch_item_info(
        self, app_id: AppID, items: Iterable[CacheKey], language: Language | None
    ) -> dict[CacheKey, econ.ItemDescription]:
        msgs = cast(
            list[econ.GetAssetClassInfoResponse],
            await asyncio.gather(
                *(
                    self.ws.send_um_and_wait(
                        econ.GetAssetClassInfoRequest(
                            language=(language or self.language).api_name,
                            appid=app_id,
                            classes=[econ.GetAssetClassInfoRequestClass(*item_info) for item_info in chunk],
                        )
                    )
                    for chunk in utils.as_chunks(items, 100)
                )
            ),
        )

        return cast(
            dict[CacheKey, econ.ItemDescription],
            {(item.classid, item.instanceid): item for msg in msgs for item in msg.descriptions},
        )

    async def fetch_chat_group_roles(self, chat_group_id: ChatGroupID) -> list[chat.Role]:
        msg: chat.GetRolesResponse = await self.ws.send_um_and_wait(chat.GetRolesRequest(chat_group_id=chat_group_id))
        if msg.result == Result.AccessDenied:
            raise WSForbidden(msg)
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.roles

    async def fetch_comment(self, owner: Commentable, id: int) -> community.GetCommentThreadResponse.Comment:
        msg: community.GetCommentThreadResponse = await self.ws.send_um_and_wait(
            community.GetCommentThreadRequest(**owner._commentable_kwargs, type=owner._COMMENTABLE_TYPE, id=id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.comments[0]

    async def fetch_comments(
        self, owner: Commentable, count: int, starting_from: int, oldest_first: bool
    ) -> community.GetCommentThreadResponse:
        msg: community.GetCommentThreadResponse = await self.ws.send_um_and_wait(
            community.GetCommentThreadRequest(
                **owner._commentable_kwargs,
                type=owner._COMMENTABLE_TYPE,
                count=count,
                start=starting_from,
                oldest_first=oldest_first,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def post_comment(self, owner: OwnerT, content: str, subscribe: bool) -> Comment[OwnerT, ClientUser]:
        msg: community.PostCommentToThreadResponse = await self.ws.send_um_and_wait(
            community.PostCommentToThreadRequest(
                **owner._commentable_kwargs,
                type=owner._COMMENTABLE_TYPE,
                content=content,
                suppress_notifications=not subscribe,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        comment = Comment(
            self,
            id=CommentID(msg.id),
            content=content,
            created_at=self.steam_time,
            author=self.user,
            owner=owner,
            reactions=[],
        )
        self.dispatch("comment", comment)
        return comment

    async def delete_comment(self, owner: Commentable, comment_id: CommentID) -> None:
        msg: community.DeleteCommentFromThreadResponse = await self.ws.send_um_and_wait(
            community.DeleteCommentFromThreadRequest(
                **owner._commentable_kwargs,
                type=owner._COMMENTABLE_TYPE,
                id=comment_id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def report_comment(self, owner: Commentable, comment_id: CommentID) -> None:
        msg: community.PostCommentToThreadResponse = await self.ws.send_um_and_wait(
            community.PostCommentToThreadRequest(  # some odd api here
                **owner._commentable_kwargs,
                type=owner._COMMENTABLE_TYPE,
                is_report=True,
                parent_id=comment_id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_notifications(self) -> list[notifications.SteamNotificationData]:
        msg: notifications.GetSteamNotificationsResponse = await self.ws.send_um_and_wait(
            notifications.GetSteamNotificationsRequest(include_hidden=True)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.notifications

    async def handle_notifications(self, msg: notifications.GetSteamNotificationsResponse) -> None:
        for notification in msg.notifications:
            match notification.notification_type:
                case 3:  # comment
                    body: dict[str, Any] = JSON_LOADS(notification.body_data)
                    forum_id = int(body["forum_id"])
                    partial_user = self.get_partial_user(body["owner_steam_id"])
                    partial_clan = PartialClan(self, body["owner_steam_id"])
                    match type := _CommentThreadType.try_value(int(body["type"])):
                        case _CommentThreadType.User:
                            commentable = partial_user
                        case _CommentThreadType.Clan:
                            commentable = partial_clan
                        case _CommentThreadType.Event:
                            commentable = await partial_clan.fetch_event(forum_id)
                        case _CommentThreadType.Announcement:
                            commentable = await partial_clan.fetch_announcement(forum_id)
                        case _CommentThreadType.PublishedFile:
                            (commentable,) = await self.fetch_published_files(
                                (PublishedFileID(forum_id),), PublishedFileRevision.Latest, None
                            )
                            assert commentable is not None
                        case _CommentThreadType.Review:
                            commentable = await partial_user.fetch_review(App(id=forum_id))
                        case _CommentThreadType.Post:
                            commentable = await partial_user.fetch_post(forum_id)
                        case _CommentThreadType.Topic:
                            log.debug("Ignoring topic comment notification %s", notification)
                            continue
                        case _:
                            log.info("Unknown commentable type %d", type)
                            continue
                    try:
                        self.dispatch("comment", await commentable.fetch_comment(int(body["cgid"])))
                    except (WSException, KeyError):
                        log.info("Failed to fetch comment %s", notification, exc_info=True)
                case 9:  # trade, this is only going to happen at startup
                    await self.poll_trades()

        await self.ws.send_um(
            notifications.MarkNotificationsReadNotification(
                notification_ids=[
                    notification.notification_id
                    for notification in msg.notifications
                    if notification.notification_type != 9
                ]
            )
        )

    @parser
    async def handle_comments(self, msg: client_server_2.CMsgClientCommentNotifications) -> None:
        while all(notification.notification_type != 3 for notification in await self.fetch_notifications()):
            await asyncio.sleep(5)  # steam takes a bit to put comments in your notifications

    @parser
    async def parse_notification(self, msg: client_server_2.CMsgClientUserNotifications) -> None:
        if any(b.user_notification_type == 1 for b in msg.notifications):
            # 1 is a trade offer
            await self.poll_trades()

    @parser
    def handle_emoticon_list(self, msg: friends.CMsgClientEmoticonList) -> None:
        self.emoticons = [ClientEmoticon(self, emoticon) for emoticon in msg.emoticons]
        self.stickers = [ClientSticker(self, sticker) for sticker in msg.stickers]
        self.effects = [ClientEffect(self, effect) for effect in msg.effects]
        self.handled_emoticons.set()

    async def add_award(self, awardable: Awardable, award: Award) -> None:
        msg = await self.ws.send_um_and_wait(
            loyalty_rewards.AddReactionRequest(
                target_type=awardable._AWARDABLE_TYPE,
                targetid=awardable.id,
                reactionid=award.id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_award_reactions(self, awardable: Awardable) -> list[ReactionProtocol]:
        # this method doesn't work and when steamcommunity tries to use it, It returns an empty response so, I'm
        # assuming it's just broken for now
        msg: loyalty_rewards.GetReactionsResponse = await self.ws.send_um_and_wait(
            loyalty_rewards.GetReactionsRequest(
                target_type=awardable.__class__._AWARDABLE_TYPE,
                targetid=awardable.id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        # but also if this doesn't work there's no point including this method
        return [_Reaction(reactionid=id, count=count) for id, count in collections.Counter(msg.reactionids).items()]

    @parser
    def handle_wallet(self, msg: client_server.CMsgClientWalletInfoUpdate) -> None:
        self.wallet = Wallet(
            self, msg.balance64, Currency.try_value(msg.currency), msg.balance64_delayed, Realm.try_value(msg.realm)
        )
        self.handled_wallet.set()

    async def fetch_cs_list(self, limit: int = 20) -> list[content_server.ServerInfo]:
        msg: content_server.GetServersForSteamPipeResponse = await self.ws.send_um_and_wait(
            content_server.GetServersForSteamPipeRequest(
                cell_id=self.cell_id,
                max_servers=limit,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.servers

    @utils.call_once(wait=True)
    async def cs_servers(self) -> list[ContentServer]:
        try:
            return self._cs_servers
        except AttributeError:
            self._cs_servers = sorted(
                (
                    ContentServer(
                        self,
                        URL_.build(scheme=f"http{'s' * (server.https_support != 'none')}", host=server.vhost),
                        server.weighted_load,
                    )
                    for server in await self.fetch_cs_list(limit=20)
                    if server.type in {"CDN", "SteamCache"}
                ),
                key=attrgetter("weighted_load"),
            )
            return self._cs_servers

    async def fetch_manifest(
        self,
        app_id: AppID,
        id: ManifestID,
        depot_id: DepotID,
        name: str | None = None,
        branch: str = "public",
        password_hash: str = "",
    ) -> Manifest:
        servers = await self.cs_servers()

        for server in tuple(servers):
            try:
                return await server.fetch_manifest(app_id, id, depot_id, name, branch, password_hash)
            except HTTPException as exc:
                if 500 <= exc.status <= 599:
                    del servers[0]
                else:
                    raise

        return await self.fetch_manifest(app_id, id, depot_id, name, branch, password_hash)

    async def fetch_manifests(
        self, app_id: AppID, branch_name: str, password: str | None, limit: int | None, password_hash: str = ""
    ) -> list[Coro[Manifest]]:
        (app_info,), _ = await self.fetch_product_info((app_id,))

        branch = app_info.get_branch(branch_name)
        if branch is None:
            raise ValueError(f"No branch named {branch_name!r} for app {app_id}")

        try:
            branch.password = self._manifest_passwords[app_id].get(branch_name)
        except KeyError:
            pass
        if branch.password_required and branch.password is None:
            if not password:
                raise ValueError(f"Branch {branch!r} requires a password")

            password_msg: client_server_2.CMsgClientCheckAppBetaPasswordResponse = await self.ws.send_proto_and_wait(
                client_server_2.CMsgClientCheckAppBetaPassword(app_id=app_id, betapassword=password)
            )
            if password_msg.result != Result.OK:
                raise WSException(password_msg)

            branch_password = utils.get(password_msg.betapasswords, betaname=branch.name)

            if branch_password is None:
                raise ValueError(f"Supplied password is not for the branch {branch!r}")
            branch.password = branch_password.betapassword
            try:
                self._manifest_passwords[app_id][branch.name] = branch.password
            except KeyError:
                self._manifest_passwords[app_id] = {branch.name: branch.password}

        return [
            self.fetch_manifest(
                app_id,
                depot.manifest.id,
                depot.id,
                depot.name,
                password_hash,
            )
            for depot in branch.depots[:limit]
        ]

    async def fetch_manifest_request_code(
        self,
        manifest_id: ManifestID,
        depot_id: DepotID,
        app_id: AppID,
        branch: str = "",
        password_hash: str = "",
    ) -> int:
        msg: content_server.GetManifestRequestCodeResponse = await self.ws.send_um_and_wait(
            content_server.GetManifestRequestCodeRequest(
                app_id=app_id,
                depot_id=depot_id,
                manifest_id=manifest_id,
                app_branch=branch,
                branch_password_hash=password_hash,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        if code := msg.manifest_request_code:
            return code

        raise ValueError

    async def fetch_product_info(
        self, app_ids: Iterable[AppID] = (), package_ids: Iterable[PackageID] = ()
    ) -> tuple[list[AppInfo], list[PackageInfo]]:
        apps_to_fetch: list[app_info.CMsgClientPicsProductInfoRequestAppInfo] = []
        packages_to_fetch: list[app_info.CMsgClientPicsProductInfoRequestPackageInfo] = []
        app_access_tokens_to_collect = list(app_ids)
        package_access_tokens_to_collect: list[PackageID] = []

        for package_id in package_ids:
            try:
                packages_to_fetch.append(
                    app_info.CMsgClientPicsProductInfoRequestPackageInfo(
                        package_id, self.licenses[package_id].access_token
                    )
                )
            except KeyError:
                package_access_tokens_to_collect.append(package_id)

        if app_access_tokens_to_collect or package_access_tokens_to_collect:
            fetched_tokens = await self.fetch_manifest_access_tokens(
                app_access_tokens_to_collect, package_access_tokens_to_collect
            )
            apps_to_fetch += (
                app_info.CMsgClientPicsProductInfoRequestAppInfo(token.appid, token.access_token)
                for token in fetched_tokens.app_access_tokens
            )
            packages_to_fetch += (
                app_info.CMsgClientPicsProductInfoRequestPackageInfo(token.packageid, token.access_token)
                for token in fetched_tokens.package_access_tokens
            )

        # this is done to avoid missing the message if the product info is massive. this sizes for the worst case
        # AFAICT where it's one response per app + 1 for the final termination message.
        max_futures = len(apps_to_fetch) + len(packages_to_fetch) + 1
        seen_msgs = list[app_info.CMsgClientPicsProductInfoResponse]()  # can't be hashed unfortunately

        def check(msg: app_info.CMsgClientPicsProductInfoResponse) -> bool:
            if msg.header.job_id_target != job_id:
                return False
            if msg in seen_msgs:
                return False
            seen_msgs.append(msg)
            return True

        futures = [
            self.ws.wait_for(app_info.CMsgClientPicsProductInfoResponse, check=check) for _ in range(max_futures)
        ]

        to_send = app_info.CMsgClientPicsProductInfoRequest(
            apps=apps_to_fetch,
            packages=packages_to_fetch,
            supports_package_tokens=True,
        )
        to_send.header.job_id_source = job_id = self.ws.next_job_id
        await self.ws.send_proto(to_send)

        response_pending = True
        apps: list[AppInfo] = []
        packages: list[PackageInfo] = []

        while response_pending:
            msg = await futures.pop(0)

            apps += (
                AppInfo(
                    self,
                    cast("manifest.AppInfo", VDF_LOADS(app.buffer[:-1].decode("UTF-8", "replace"))["appinfo"]),
                    app,
                )
                for app in msg.apps
            )

            packages += (
                PackageInfo(
                    self,
                    cast("manifest.PackageInfo", VDF_BINARY_LOADS(package.buffer[4:])[str(package.packageid)]),
                    package,
                )
                for package in msg.packages
            )

            response_pending = msg.response_pending

        for future in futures:
            future.cancel()
        await asyncio.gather(*futures, return_exceptions=True)

        return apps, packages

    async def fetch_depot_key(self, app_id: AppID, depot_id: DepotID) -> bytes:
        msg: client_server_2.CMsgClientGetDepotDecryptionKeyResponse = await self.ws.send_proto_and_wait(
            client_server_2.CMsgClientGetDepotDecryptionKey(app_id=app_id, depot_id=depot_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.depot_encryption_key

    async def fetch_manifest_access_tokens(
        self,
        app_ids: list[AppID] | None = None,
        package_ids: list[PackageID] | None = None,
    ) -> app_info.CMsgClientPicsAccessTokenResponse:
        msg: app_info.CMsgClientPicsAccessTokenResponse = await self.ws.send_proto_and_wait(
            app_info.CMsgClientPicsAccessTokenRequest(
                appids=cast(list[int], [] if app_ids is None else app_ids),
                packageids=cast(list[int], [] if package_ids is None else package_ids),
            )
        )
        if msg.result not in (
            Result.OK,
            Result.Invalid,
        ):  # invalid is for the case where access tokens are not required
            raise WSException(msg)
        return msg

    async def fetch_published_files_with_author(
        self,
        published_file_ids: Iterable[PublishedFileID],
        user: AuthorT,  # type: ignore  # I cba making an invariant version of this
        revision: PublishedFileRevision,
        language: Language | None,
    ) -> list[PublishedFile[AuthorT] | None]:
        msg: published_file.GetDetailsResponse = await self.ws.send_um_and_wait(
            published_file.GetDetailsRequest(
                publishedfileids=list(published_file_ids),
                language=(language or self.language).value,
                includetags=True,
                includeadditionalpreviews=True,
                includechildren=True,
                includekvtags=True,
                includevotes=True,
                includeforsaledata=True,
                includemetadata=True,
                strip_description_bbcode=True,
                includereactions=True,
                return_playtime_stats=True,
                desired_revision=revision,  # type: ignore
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        if any(proto.creator != user.id64 for proto in msg.publishedfiledetails):
            raise ValueError("An id passed was not published by this author")

        return [
            PublishedFile(self, proto, user) if proto.result == Result.OK else None
            for proto in msg.publishedfiledetails
        ]

    async def fetch_published_files(
        self,
        published_file_ids: Iterable[PublishedFileID],
        revision: PublishedFileRevision,
        language: Language | None,
    ) -> list[PublishedFile[Author] | None]:
        msg: published_file.GetDetailsResponse = await self.ws.send_um_and_wait(
            published_file.GetDetailsRequest(
                publishedfileids=list(published_file_ids),
                language=(language or self.language).value,
                includetags=True,
                includeadditionalpreviews=True,
                includechildren=True,
                includekvtags=True,
                includevotes=True,
                includeforsaledata=True,
                includemetadata=True,
                strip_description_bbcode=True,
                includereactions=True,
                return_playtime_stats=True,
                desired_revision=revision,  # type: ignore
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        protos = msg.publishedfiledetails
        authors = await self._maybe_users(ID64(proto.creator) for proto in protos)
        return [
            PublishedFile(self, proto, author) if proto.result == Result.OK else None
            for proto, author in zip(protos, authors)
        ]

    async def fetch_user_published_files(
        self,
        user_id64: ID64,
        app_id: AppID,
        page: int,
        file_type: PublishedFileType,
        revision: PublishedFileRevision,
        language: Language | None,
    ) -> published_file.GetUserFilesResponse:
        msg: published_file.GetUserFilesResponse = await self.ws.send_um_and_wait(
            published_file.GetUserFilesRequest(
                steamid=user_id64,
                appid=app_id,
                numperpage=30,
                page=page,
                filetype=file_type.value,
                language=(language or self.language).value,
                return_vote_data=True,
                return_tags=True,
                return_kv_tags=True,
                return_previews=True,
                return_children=True,
                return_for_sale_data=True,
                return_metadata=True,
                return_playtime_stats=True,
                strip_description_bbcode=True,
                return_reactions=True,
                desired_revision=revision,  # type: ignore
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_app_published_files(
        self,
        app_id: AppID,
        file_type: PublishedFileQueryFileType,
        revision: PublishedFileRevision,
        language: Language | None,
        limit: int | None,
        cursor: str = "*",
    ) -> published_file.QueryFilesResponse:
        msg: published_file.QueryFilesResponse = await self.ws.send_um_and_wait(
            published_file.QueryFilesRequest(
                numperpage=min(limit or 100, 100),
                appid=app_id,
                filetype=file_type,
                cursor=cursor,
                language=(language or self.language).value,
                return_vote_data=True,
                return_tags=True,
                return_kv_tags=True,
                return_previews=True,
                return_children=True,
                return_for_sale_data=True,
                return_metadata=True,
                return_playtime_stats=True,
                return_details=True,
                return_reactions=True,
                desired_revision=revision,  # type: ignore
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_published_file_parents(
        self,
        published_file_id: PublishedFileID,
        revision: PublishedFileRevision,
        language: Language | None,
        cursor: str = "*",
    ) -> published_file.QueryFilesResponse:
        msg: published_file.QueryFilesResponse = await self.ws.send_um_and_wait(
            published_file.QueryFilesRequest(
                numperpage=100,
                child_publishedfileid=published_file_id,
                cursor=cursor,
                language=(language or self.language).value,
                return_vote_data=True,
                return_tags=True,
                return_kv_tags=True,
                return_previews=True,
                return_children=True,
                return_for_sale_data=True,
                return_metadata=True,
                return_playtime_stats=True,
                return_details=True,
                return_reactions=True,
                desired_revision=revision,  # type: ignore
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_published_file_history(
        self, published_file_id: PublishedFileID, language: Language | None
    ) -> list[published_file.GetChangeHistoryResponseChangeLog]:
        msg: published_file.GetChangeHistoryResponse = await self.ws.send_um_and_wait(
            published_file.GetChangeHistoryRequest(
                publishedfileid=published_file_id,
                language=(language or self.language).value,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.changes

    async def fetch_published_file_history_entry(
        self, published_file_id: PublishedFileID, dt: datetime, language: Language | None
    ) -> published_file.GetChangeHistoryEntryResponse:
        msg: published_file.GetChangeHistoryEntryResponse = await self.ws.send_um_and_wait(
            published_file.GetChangeHistoryEntryRequest(
                publishedfileid=published_file_id,
                timestamp=int(dt.timestamp()),
                language=(language or self.language).value,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def subscribe_to_published_file(self, published_file_id: PublishedFileID) -> None:
        msg = await self.ws.send_um_and_wait(
            published_file.SubscribeRequest(publishedfileid=published_file_id, notify_client=True)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def unsubscribe_from_published_file(self, published_file_id: PublishedFileID) -> None:
        msg = await self.ws.send_um_and_wait(
            published_file.UnsubscribeRequest(publishedfileid=published_file_id, notify_client=True)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def is_subscribed_to_published_file(self, published_file_id: PublishedFileID) -> bool:
        msg: published_file.CanSubscribeResponse = await self.ws.send_um_and_wait(
            published_file.CanSubscribeRequest(publishedfileid=published_file_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.can_subscribe

    async def add_published_file_child(
        self, published_file_id: PublishedFileID, child_published_file_id: PublishedFileID
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            published_file.AddChildRequest(
                publishedfileid=published_file_id, child_publishedfileid=child_published_file_id
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def remove_published_file_child(
        self, published_file_id: PublishedFileID, child_published_file_id: PublishedFileID
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            published_file.RemoveChildRequest(
                publishedfileid=published_file_id,
                child_publishedfileid=child_published_file_id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def upvote_published_file(self, published_file_id: PublishedFileID, vote_up: bool) -> None:
        msg = await self.ws.send_um_and_wait(
            published_file.VoteRequest(
                publishedfileid=published_file_id,
                vote_up=vote_up,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def edit_published_file(
        self,
        published_file_id: PublishedFileID,
        app_id: AppID,
        name: str,
        content: str,
        visibility: int,
        tags: list[str],
        filename: str,
        preview_filename: str,
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            published_file.UpdateRequest(
                appid=app_id,
                publishedfileid=published_file_id,
                title=name,
                file_description=content,
                visibility=visibility,
                tags=tags,
                filename=filename,
                preview_filename=preview_filename,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    @parser
    async def handle_close(self, _: login.CMsgClientLogOff | Any = None) -> Never:
        if not self.ws.socket.closed:
            await self.ws.close()
        if hasattr(self.ws, "_keep_alive"):
            self.ws._keep_alive.stop()
            del self.ws._keep_alive
        log.info("Websocket closed, cannot reconnect.")
        self.ws.closed = True
        raise ConnectionClosed(self.ws.cm)

    @parser
    def ack_heartbeat(self, msg: login.CMsgClientHeartBeat) -> None:
        self.ws._keep_alive.ack()

    @parser
    def set_steam_time(self, msg: login.CMsgClientServerTimestampResponse) -> None:
        self.server_offset = timedelta(milliseconds=msg.server_timestamp_ms - msg.client_request_timestamp)

    @parser
    def handle_multi(self, msg: base.CMsgMulti) -> None:
        data: bytearray = unpack_multi(msg) if msg.size_unzipped else msg.message_body  # type: ignore

        while data:
            size = READ_U32(data)
            self.ws.receive(data[4 : 4 + size])
            data = data[4 + size :]

    @parser
    async def handle_logoff(self, msg: login.CMsgClientLoggedOff) -> Never:
        await self.handle_close()

    @parser
    async def parse_um(self, msg: UnifiedMessage) -> None:
        match msg:
            case chat.IncomingChatMessageNotification():
                self.handle_chat_message(msg)
            case chat.MessageReactionNotification():
                self.handle_chat_message_reaction(msg)
            case chat.ChatRoomHeaderStateNotification():
                self.handle_chat_group_update(msg)
            case chat.NotifyChatGroupUserStateChangedNotification():
                await self.handle_chat_group_user_action(msg)
            case chat.MemberStateChangeNotification():
                await self.handle_chat_member_update(msg)
            case chat.ChatRoomGroupRoomsChangeNotification():
                self.handle_chat_update(msg)
            case friend_messages.IncomingMessageNotification():
                await self.handle_user_message(msg)
            case friend_messages.MessageReactionNotification():
                await self.handle_user_message_reaction(msg)
            case chat.GetMyChatRoomGroupsResponse():
                await self.handle_get_my_chat_groups(msg)
            case notifications.GetSteamNotificationsResponse():
                await self.handle_notifications(msg)
            case _:
                log.debug("No handler for UM: %r %r", msg.UM_NAME, msg)


ConnectionState.parsers = {}
for _, func in inspect.getmembers(ConnectionState, lambda x: inspect.isfunction(x) and getattr(x, "__parser__", False)):
    try:
        params = list(inspect.get_annotations(func, eval_str=True).values())
    except NameError:
        continue
    if args := get_args(params[0]):
        ConnectionState.parsers[args[0].MSG] = func
    elif params[0].MSG not in SERVICE_EMSGS | {NoMsg.NONE}:
        ConnectionState.parsers[params[0].MSG] = func

for msg in SERVICE_EMSGS:
    ConnectionState.parsers[msg] = ConnectionState.parse_um  # type: ignore
