"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import collections
import logging
import random
import weakref
from collections import defaultdict, deque
from collections.abc import AsyncGenerator, Callable, Collection, Iterable, Sequence
from contextlib import asynccontextmanager
from copy import copy
from datetime import datetime, timedelta
from itertools import count
from operator import attrgetter
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from zlib import crc32

from typing_extensions import Self
from yarl import URL as URL_

from . import utils
from ._const import JSON_LOADS, URL, VDF_BINARY_LOADS, VDF_LOADS, TaskGroup, timeout
from .abc import Awardable, BaseUser, Commentable, PartialUser, _CommentableThreadType
from .app import App, AuthenticationTicket, FetchedApp, PartialApp
from .channel import UserChannel
from .clan import Clan, PartialClan
from .comment import Comment
from .enums import *
from .enums import PurchaseResult
from .errors import *
from .friend import Friend
from .group import Group
from .guard import *
from .id import _ID64_TO_ID32, ID, parse_id64
from .invite import ClanInvite, UserInvite
from .manifest import AppInfo, ContentServer, Manifest, PackageInfo
from .message import *
from .message import ClanMessage
from .models import Registerable, Wallet, register
from .package import FetchedPackage, License
from .protobufs import (
    EMsg,
    ProtobufMessage,
    UnifiedMessage,
    app_info,
    chat,
    clan,
    client_server,
    client_server_2,
    comments,
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
    user_stats,
)
from .published_file import PublishedFile
from .reaction import (
    Award,
    ClientEmoticon,
    ClientSticker,
    Emoticon,
    MessageReaction,
    ReactionProtocol,
    Sticker,
    _Reaction,
)
from .role import RolePermissions
from .trade import Item, TradeOffer
from .types.id import *
from .types.user import Author
from .user import ClientUser, User
from .utils import DateTime, cached_property

if TYPE_CHECKING:
    from .abc import Message
    from .client import Client
    from .gateway import CMServer, SteamWebSocket
    from .types import trade
    from .types.http import Coro

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
        for item in other:
            attr = self.attr(item)
            try:
                future = self._waiting_for[attr]
            except KeyError:
                pass
            else:
                future.set_result(item)
                del self._waiting_for[attr]

        self.queue += other
        return self


class ConnectionState(Registerable):
    parsers: dict[EMsg, Callable[..., Any]]

    def __init__(self, client: Client, **kwargs: Any):
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
        self.max_messages: int | None = kwargs.pop("max_messages", 1000)

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
        self._users: weakref.WeakValueDictionary[ID32, User] = weakref.WeakValueDictionary()
        self._trades: dict[TradeOfferID, TradeOffer[Item[User], Item[ClientUser], User]] = {}

        self._groups: dict[ChatGroupID, Group] = {}
        self._clans: dict[ID32, Clan] = {}
        self._clans_by_chat_id: dict[ChatGroupID, Clan] = {}
        self.chat_group_to_view_id: defaultdict[ChatGroupID, int] = defaultdict(count().__next__)
        self.active_chat_groups: set[ChatGroupID] = set()

        self._confirmations: dict[TradeOfferID, Confirmation] = {}
        self.confirmation_generation_locks: dict[str, tuple[asyncio.Lock, datetime]] = {}
        self._messages: deque[Message] = deque(maxlen=self.max_messages or 0)
        self.invites: dict[ID64, UserInvite | ClanInvite] = {}
        self.emoticons: list[ClientEmoticon] = []
        self.stickers: list[ClientSticker] = []

        self.polling_trades = False
        self.trade_queue = Queue[TradeOffer[Item[User], Item[ClientUser], User]]()
        self._trades_to_watch: set[TradeOfferID] = set()
        self._trades_received_cache: Sequence[dict[str, Any]] = ()
        self._trades_sent_cache: Sequence[dict[str, Any]] = ()
        self.polling_confirmations = False
        self.confirmation_queue = Queue[Confirmation](attr=attrgetter("creator_id"))

        self.cell_id = 0
        self._connected_cm: CMServer | None = None

        self.wallet: Wallet = None  # type: ignore

        self.licenses: dict[PackageID, License] = {}
        self._license_lock = asyncio.Lock()
        self.licenses_being_waited_for = weakref.WeakValueDictionary[PackageID, asyncio.Future[License]]()
        self._manifest_passwords: dict[AppID, dict[str, str]] = {}
        self.cs_servers: list[ContentServer] = []
        self.cs_servers_lock = asyncio.Lock()

        self._game_connect_bytes: list[
            bytes
        ] = []  # this is a bad name but it's a combination of gc_token, steam id, and time
        self.connection_count = 0
        self._h_steam_pipe = random.randint(1, 1000001)
        self._active_auth_tickets: dict[tuple[AppID, ID64], AuthenticationTicket] = {}
        self._auth_seq_me = 0
        self._auth_seq_them = 0

        self.handled_friends.clear()
        self.handled_emoticons.clear()
        self.handled_chat_groups.clear()
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
        return generate_device_id(self.user)

    @utils.cached_property
    def _tg(self) -> TaskGroup:
        return self.client._tg

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

    def get_user(self, id: ID32) -> User | None:
        return self._users.get(id)

    async def fetch_user(self, user_id64: ID64) -> User:
        (user,) = await self.fetch_users((user_id64,))
        return user

    async def fetch_users(self, user_id64s: Iterable[ID64]) -> list[User]:
        friends = await self.ws.fetch_users(user_id64s)
        return [self._store_user(user) for user in friends]

    async def _maybe_user(self, id: Intable) -> User:
        steam_id = ID(id, type=Type.Individual)
        return self.get_user(steam_id.id) or await self.fetch_user(steam_id.id64) or PartialUser(self, steam_id.id64)

    async def _maybe_users(self, id64s: Iterable[ID64]) -> list[User]:
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

    def get_group(self, id: ChatGroupID) -> Group | None:
        return self._groups.get(id)

    def get_clan(self, id: ID32) -> Clan | None:
        return self._clans.get(id)

    async def fetch_clan(self, id64: ID64, *, maybe_chunk: bool = True) -> Clan:
        msg: chat.GetClanChatRoomInfoResponse = await self.ws.send_um_and_wait(
            chat.GetClanChatRoomInfoRequest(steamid=id64)
        )
        if msg.result == Result.Busy:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        clan = await Clan._from_proto(self, msg.chat_group_summary, maybe_chunk=maybe_chunk)
        self._clans[clan.id] = clan
        return clan

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
            (trade,) = await self._process_trades((data["offer"],), data.get("descriptions", ()))
            return trade

    async def _store_trade(self, data: trade.TradeOffer) -> TradeOffer[Item[User], Item[ClientUser], User]:
        try:
            trade = self._trades[TradeOfferID(int(data["tradeofferid"]))]
        except KeyError:
            log.info(f'Received trade #{data["tradeofferid"]}')
            trade = TradeOffer._from_api(
                state=self, data=data, partner=await self._maybe_user(utils.parse_id64(data["accountid_other"]))
            )
            self._trades[trade.id] = trade
            if trade.state in (TradeOfferState.Active, TradeOfferState.ConfirmationNeed) and (
                trade.sending or trade.receiving  # trade could be glitched
            ):
                self.dispatch("trade_send" if trade.is_our_offer() else "trade_receive", trade)
                self._trades_to_watch.add(trade.id)
        else:
            before_state = trade.state
            trade._update(data)
            if trade.state != before_state:
                log.info(f"Trade #{trade.id} has updated its trade state to {trade.state}")
                event_name = trade.state.event_name
                if event_name and (trade.sending or trade.receiving):
                    self.dispatch(f"trade_{event_name}", trade)
                    self._trades_to_watch.discard(trade.id)
        return trade

    async def _process_trades(
        self, trades: Iterable[trade.TradeOffer], descriptions: Collection[trade.Description]
    ) -> list[TradeOffer[Item[User], Item[ClientUser], User]]:
        ret: list[TradeOffer[Item[User], Item[ClientUser], User]] = []
        for trade in trades:
            for description in descriptions:
                for asset in trade.get("items_to_receive", ()):
                    if description["classid"] == asset["classid"] and description["instanceid"] == asset["instanceid"]:
                        asset |= description
                for asset in trade.get("items_to_give", ()):
                    if description["classid"] == asset["classid"] and description["instanceid"] == asset["instanceid"]:
                        asset |= description
            ret.append(await self._store_trade(trade))
        return ret

    async def poll_trades(self) -> None:
        if self.polling_trades or not await self.http.get_api_key():
            return

        self.polling_trades = True
        try:
            await self.fill_trades()

            while self._trades_to_watch:  # watch trades for changes
                await asyncio.sleep(5)
                await self.fill_trades()
        finally:
            self.polling_trades = False

    async def fill_trades(self) -> None:
        try:
            trades = await self.http.get_trade_offers()
            descriptions = trades.get("descriptions", ())
            trades_received = trades.get("trade_offers_received", ())
            trades_sent = trades.get("trade_offers_sent", ())
            updated_received_trades = [trade for trade in trades_received if trade not in self._trades_received_cache]
            updated_sent_trades = [trade for trade in trades_sent if trade not in self._trades_sent_cache]
            received_trades = await self._process_trades(updated_received_trades, descriptions)
            sent_trades = await self._process_trades(updated_sent_trades, descriptions)
            self._trades_received_cache = trades_received
            self._trades_sent_cache = trades_sent

            self.trade_queue += received_trades
            self.trade_queue += sent_trades
        except Exception as exc:
            await asyncio.sleep(30)
            log.info("Error while polling trades", exc_info=exc)

    async def wait_for_trade(self, id: TradeOfferID) -> TradeOffer[Item[User], Item[ClientUser], User]:
        self._tg.create_task(self.poll_trades())  # start re-polling trades
        return await self.trade_queue.wait_for(id=id)

    # confirmations

    def get_confirmation(self, id: TradeOfferID) -> Confirmation | None:
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id: TradeOfferID) -> Confirmation | None:
        await self.fill_confirmations()
        return self._confirmations.get(id)

    async def fill_confirmations(self) -> None:
        key, timestamp = await self._generate_confirmation_code("list")
        data = await self.http.get(
            URL.COMMUNITY / "mobileconf/getlist",
            params={"p": self._device_id, "a": self.user.id64, "k": key, "t": timestamp, "m": "react", "tag": "list"},
        )
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

    async def _create_confirmation_params(self, tag: str) -> dict[str, Any]:
        code, timestamp = await self._generate_confirmation_code(tag)
        return {
            "p": self._device_id,
            "a": self.user.id64,
            "k": code,
            "t": timestamp,
            "m": "android",
            "tag": tag,
        }

    async def _generate_confirmation_code(self, tag: str) -> tuple[str, int]:
        # generate a confirmation code for a given tag at this instant.
        # this can wait x amount of time (<1s) for the code to be generated if codes would collide as they can only be
        # used once.
        secret = self.client.identity_secret
        if secret is None:
            raise ValueError("Cannot generate confirmation codes without passing an identity_secret")

        steam_time = self.steam_time
        timestamp = int(steam_time.timestamp())
        try:
            lock, last_confirmation_time = self.confirmation_generation_locks[tag]
        except KeyError:
            lock = asyncio.Lock()
            last_confirmation_time = steam_time - timedelta(seconds=2)
            self.confirmation_generation_locks[tag] = lock, last_confirmation_time

        await lock.acquire()
        try:
            return generate_confirmation_code(secret, tag, timestamp), timestamp
        finally:
            # wait for the next second whole before allowing generation of a new confirmation code
            next_code_valid_in = (steam_time.replace(microsecond=0) - last_confirmation_time).total_seconds()
            if next_code_valid_in < 0:
                lock.release()
            else:
                asyncio.get_running_loop().call_later(next_code_valid_in, lock.release)
            self.confirmation_generation_locks[tag] = lock, steam_time

    async def poll_confirmations(self) -> None:
        if self.polling_confirmations:
            return

        self.polling_confirmations = True
        try:
            await self.fill_confirmations()

            while self.confirmation_queue.queue:
                await asyncio.sleep(10)
                await self.fill_confirmations()
        finally:
            self.polling_confirmations = False

    async def wait_for_confirmation(self, id: TradeOfferID) -> Confirmation:
        self._tg.create_task(self.poll_confirmations())
        return await self.confirmation_queue.wait_for(id=id)

    async def fetch_and_confirm_confirmation(self, trade_id: TradeOfferID) -> bool:
        if self.client.identity_secret:
            confirmation = await self.wait_for_confirmation(id=trade_id)
            await confirmation.confirm()
            return True

        return False

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

    # ws stuff

    @cached_property
    def _chat_groups(self) -> utils.ChainMap[ChatGroupID, Group | Clan]:
        return utils.ChainMap(self._clans_by_chat_id, self._groups)  # type: ignore  # needs HKT

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
        channel = UserChannel(state=self, participant=participant)
        message = UserMessage(proto, channel, self.user)
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
        (message_cls,) = channel._type_args
        message = message_cls(
            proto=proto,
            channel=channel,  # type: ignore  # type checkers can't figure out this is ok
            author=group.me,
        )
        channel.last_message = message  # type: ignore  # same as above
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def delete_chat_message(
        self, chat_group_id: ChatGroupID, chat_id: ChatID, timestamp: int, ordinal: int
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            chat.DeleteChatMessagesRequest(
                chat_id=chat_id,
                chat_group_id=chat_group_id,
                messages=[chat.DeleteChatMessagesRequestMessage(server_timestamp=timestamp, ordinal=ordinal)],
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

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
        await self.ws.send_um(  # send_um_and_wait doesn't work here cause job_id is not meant to be set
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

    async def edit_role_name(self, chat_group_id: ChatGroupID, role_id: RoleID, name: str) -> None:
        msg: ProtobufMessage = await self.ws.send_um_and_wait(
            chat.RenameRoleRequest(chat_group_id=chat_group_id, role_id=role_id, name=name)
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def edit_role_permissions(
        self, chat_group_id: ChatGroupID, role_id: RoleID, permissions: RolePermissions
    ) -> None:
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

    async def delete_role(self, chat_group_id: ChatGroupID, role_id: RoleID) -> None:
        msg = await self.ws.send_um_and_wait(chat.DeleteRoleRequest(chat_group_id=chat_group_id, role_id=role_id))
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

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

    async def fetch_chat_group_history(
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
            )
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return cast("list[ID32]", msg.reactors)

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

    async def fetch_package(self, package_id: PackageID, language: Language | None) -> FetchedPackage:
        resp = await self.http.get_package(package_id, language)
        data = resp[str(package_id)]
        if data["success"]:
            return FetchedPackage(self, data["data"])
        raise ValueError("package_id is invalid")

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

    async def fetch_friend_profile_info(self, user_id64: ID64) -> friends.CMsgClientFriendProfileInfoResponse:
        msg: friends.CMsgClientFriendProfileInfoResponse = await self.ws.send_proto_and_wait(
            friends.CMsgClientFriendProfileInfo(steamid_friend=user_id64)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

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
        if msg.result != Result.OK:
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

    async def fetch_trade_url(self, generate_new: bool) -> str:
        msg: econ.GetTradeOfferAccessTokenResponse = await self.ws.send_um_and_wait(
            econ.GetTradeOfferAccessTokenRequest(generate_new_token=generate_new)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return str(URL.COMMUNITY / "tradeoffer/new" % {"partner": self.user.id, "token": msg.trade_offer_access_token})

    # parsers

    @register(EMsg.ServiceMethod)
    async def parse_um(self, msg: UnifiedMessage) -> None:
        match msg:
            case chat.IncomingChatMessageNotification():
                await self.handle_chat_message(msg)
            case chat.MessageReactionNotification():
                await self.handle_chat_message_reaction(msg)
            case chat.ChatRoomHeaderStateNotification():
                await self.handle_chat_group_update(msg)
            case chat.NotifyChatGroupUserStateChangedNotification():
                await self.handle_chat_group_user_action(msg)
            case chat.MemberStateChangeNotification():
                await self.handle_chat_member_update(msg)
            case chat.ChatRoomGroupRoomsChangeNotification():
                await self.handle_chat_update(msg)
            case friend_messages.IncomingMessageNotification():
                await self.handle_user_message(msg)
            case friend_messages.MessageReactionNotification():
                await self.handle_user_message_reaction(msg)
            case chat.GetMyChatRoomGroupsResponse():
                await self.handle_get_my_chat_groups(msg)
            case notifications.GetSteamNotificationsResponse():
                await self.handle_notifications(msg)
            case _:
                log.debug("Got a UM %r that we don't handle %r", msg.UM_NAME, msg)

    @register(EMsg.ServiceMethodResponse)
    async def parse_service_method_response(self, msg: UnifiedMessage) -> None:
        await self.parse_um(msg)

    @register(EMsg.ServiceMethodSendToClient)
    async def parse_service_method_send_to_client(self, msg: UnifiedMessage) -> None:
        await self.parse_um(msg)

    @register(EMsg.ServiceMethodCallFromClient)
    async def parse_service_method_call_from_client(self, msg: UnifiedMessage) -> None:
        await self.parse_um(msg)

    async def handle_user_message(self, msg: friend_messages.IncomingMessageNotification) -> None:
        await self.client.wait_until_ready()
        id64 = msg.steamid_friend
        partner = self.user._friends.get(_ID64_TO_ID32(id64)) or await self._maybe_user(id64)
        author = self.user if msg.local_echo else partner  # local_echo is always us

        if msg.chat_entry_type == ChatEntryType.Text:
            channel = UserChannel(state=self, participant=partner)  # type: ignore  # remove when above fixme removed
            message = UserMessage(msg, channel, author)
            self._messages.append(message)
            self.dispatch("message", message)

        if msg.chat_entry_type == ChatEntryType.Typing:
            when = DateTime.from_timestamp(msg.rtime32_server_timestamp)
            self.dispatch("typing", author, when)

    async def handle_user_message_reaction(self, msg: friend_messages.MessageReactionNotification) -> None:
        user = await self._maybe_user(msg.steamid_friend)
        ordinal = msg.ordinal
        created_at = DateTime.from_timestamp(msg.server_timestamp)
        message = utils.find(
            lambda message: (
                message.author in (user, self.user)
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
                reaction = MessageReaction(self, message, Emoticon(self, msg.reaction), None, user, created_at, ordinal)
            case Sticker._TYPE:
                reaction = MessageReaction(self, message, None, Sticker(self, msg.reaction), user, created_at, ordinal)
            case _:
                return log.debug(
                    "Got an unknown reaction_type %s on message %s %s", msg.reaction_type, created_at, ordinal
                )

        self.dispatch(f"reaction_{'add' if msg.is_add else 'remove'}", reaction)

    async def handle_chat_message(self, msg: chat.IncomingChatMessageNotification) -> None:
        try:
            destination = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got a message for a chat we aren't in %s", msg.chat_group_id)

        channel = destination._channels[ChatID(msg.chat_id)]
        channel._update(msg)

        (message_cls,) = channel._type_args
        message = message_cls(
            proto=msg,
            channel=channel,  # type: ignore  # type checkers aren't able to figure out this is ok
            author=destination._maybe_member(_ID64_TO_ID32(msg.steamid_sender)),
        )
        channel.last_message = message  # type: ignore  # same as above
        self._messages.append(message)
        self.dispatch("message", message)

    async def handle_chat_message_reaction(self, msg: chat.MessageReactionNotification) -> None:
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

        self.dispatch(f"reaction_{'add' if msg.is_add else 'remove'}", reaction)

    async def handle_chat_group_update(self, msg: chat.ChatRoomHeaderStateNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.header_state.chat_group_id)]
        except KeyError:
            return log.debug("Updating a group that isn't cached %s", msg.header_state.chat_group_id)

        before = copy(chat_group)
        before._roles = {r_id: copy(r) for r_id, r in before._roles.items()}
        chat_group._update_header_state(msg.header_state)
        self.dispatch(f"{'group' if isinstance(chat_group, Group) else 'clan'}_update", before, chat_group)

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

            if isinstance(left, Clan):
                self.dispatch("clan_leave", left)
            else:
                self.dispatch("group_leave", left)
        # elif msg.user_action == chat.EChatRoomMemberStateChange.Invited:
        #     if msg.group_summary.clanid:
        #         return
        #     group = await Group._from_proto(self, msg.group_summary)
        #     self._groups[group.id] = group
        #     self.dispatch("group_invite", group)

    async def handle_chat_member_update(self, msg: chat.MemberStateChangeNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got a chat member update for a chat group we aren't in %d", msg.chat_group_id)

        match msg.change:
            case chat.EChatRoomMemberStateChange.Joined:
                member = await chat_group._add_member(msg.member)
                self.dispatch("member_join", member)
            case chat.EChatRoomMemberStateChange.Parted:
                member = chat_group._remove_member(msg.member)
                if member is None:
                    return
                self.dispatch("member_leave", chat_group, member)
            # TODO: handle other user_actions

    async def handle_chat_update(self, msg: chat.ChatRoomGroupRoomsChangeNotification) -> None:
        try:
            chat_group = self._chat_groups[ChatGroupID(msg.chat_group_id)]
        except KeyError:
            return log.debug("Got an update for a chat group we aren't in %d", msg.chat_group_id)

        before = copy(chat_group)
        before._channels = {c_id: copy(c) for c_id, c in before._channels.items()}  # type: ignore  # needs conditional types
        chat_group._update_channels(msg.chat_rooms)
        self.dispatch(f"{chat_group.__class__.__name__}_update", before, chat_group)

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
        await self.handled_friends.wait()  # ensure friend cache is ready
        await self.handled_emoticons.wait()  # ensure emoticon cache is ready
        await self.handled_licenses.wait()  # ensure licenses are ready
        await self.handled_wallet.wait()  # ensure wallet is ready
        await self.client._handle_ready()

    @register(EMsg.ClientPersonaState)
    def parse_persona_state_update(self, msg: friends.CMsgClientPersonaState) -> None:
        for friend in msg.friends:
            after = self.get_user(_ID64_TO_ID32(friend.friendid))
            if after is None:
                continue

            before = copy(after)

            after._update(friend)
            old = [getattr(before, attr, None) for attr in BaseUser.__slots__]
            new = [getattr(after, attr, None) for attr in BaseUser.__slots__]
            if old != new and self.handled_friends.is_set():
                self.dispatch("user_update", before, after)

    def _add_friend(self, user: User) -> Friend:
        self.user._friends[user.id] = friend = Friend(self, user)
        return friend

    @register(EMsg.ClientFriendsList)
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
                                self._add_friend(user)
                    else:
                        if isinstance(invite, UserInvite):
                            self.dispatch("user_invite_accept", invite)
                            if isinstance(invite.invitee, User):
                                friend = self._add_friend(invite.invitee)
                                self.dispatch("friend_add", friend)
                        else:
                            self.dispatch("clan_invite_accept", invite)
                            if isinstance(invite.clan, Clan):
                                self._clans[invite.clan.id] = invite.clan

                case FriendRelationship.RequestInitiator | FriendRelationship.RequestRecipient:
                    match id.type:
                        case Type.Individual:
                            invitee = await self._maybe_user(id.id64)
                            invite = UserInvite(state=self, invitee=invitee, relationship=relationship)
                            self.invites[invitee.id64] = invite
                            self.dispatch("user_invite", invite)

                        case Type.Clan:
                            if clan_invitees is None:
                                clan_invitees = await self.http.get_clan_invitees()

                            invitee = await self._maybe_user(clan_invitees[id.id64])
                            clan = await self.fetch_clan(id.id64)
                            assert clan is not None
                            )

                            invitee = await self._maybe_user(invitee_id64)
                            try:
                                clan = await self.fetch_clan(id.id64) or id
                            except WSException:
                                clan = id
                            invite = ClanInvite(state=self, invitee=invitee, clan=clan, relationship=relationship)
                            self.invites[clan.id64] = invite
                            self.dispatch("clan_invite", invite)

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
                            else:
                                self.dispatch("user_invite_decline", invite)

                        case Type.Clan:
                            try:
                                invite = self.invites.pop(id.id64)
                            except KeyError:
                                clan = self._clans.pop(id.id, None)
                                if clan is None:
                                    return log.debug("Unknown clan %s removed", id)
                                self.dispatch("clan_leave", clan)
                            else:
                                self.dispatch("clan_invite_decline", invite)

        if is_load:
            await self.login_complete.wait()
            self.user._friends = {user.id: Friend(self, user) for user in await self.fetch_users(client_user_friends)}
            self.handled_friends.set()

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
                    count=5000,
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

    async def fetch_item_info(
        self, app_id: AppID, items: Iterable[CacheKey], language: Language | None
    ) -> dict[CacheKey, econ.ItemDescription]:
        result: dict[CacheKey, econ.ItemDescription] = {}

        for chunk in utils.as_chunks(items, 100):
            msg: econ.GetAssetClassInfoResponse = await self.ws.send_um_and_wait(
                econ.GetAssetClassInfoRequest(
                    language=(language or self.language).api_name,
                    appid=app_id,
                    classes=[econ.GetAssetClassInfoRequestClass(*item_info) for item_info in chunk],
                )
            )

            for item in msg.descriptions:
                result[(item.classid, item.instanceid)] = item  # type: ignore

        return result

    async def fetch_chat_group_roles(self, chat_group_id: ChatGroupID) -> list[chat.Role]:
        msg: chat.GetRolesResponse = await self.ws.send_um_and_wait(chat.GetRolesRequest(chat_group_id=chat_group_id))
        if msg.result == Result.AccessDenied:
            raise WSForbidden(msg)
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.roles

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
        await self._block_user(user_id64, True)

    async def unblock_user(self, user_id64: ID64) -> None:
        await self._block_user(user_id64, False)

    async def fetch_comment(self, owner: Commentable, id: int) -> comments.GetCommentThreadResponse.Comment:
        msg: comments.GetCommentThreadResponse = await self.ws.send_um_and_wait(
            comments.GetCommentThreadRequest(**owner._commentable_kwargs, type=owner._COMMENTABLE_TYPE, id=id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.comments[0]

    async def fetch_comments(
        self, owner: Commentable, count: int, starting_from: int, oldest_first: bool
    ) -> comments.GetCommentThreadResponse:
        msg: comments.GetCommentThreadResponse = await self.ws.send_um_and_wait(
            comments.GetCommentThreadRequest(
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
        msg: comments.PostCommentToThreadResponse = await self.ws.send_um_and_wait(
            comments.PostCommentToThreadRequest(
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
        msg: comments.DeleteCommentFromThreadResponse = await self.ws.send_um_and_wait(
            comments.DeleteCommentFromThreadRequest(
                **owner._commentable_kwargs,
                type=owner._COMMENTABLE_TYPE,
                id=comment_id,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def report_comment(self, owner: Commentable, comment_id: CommentID) -> None:
        msg: comments.PostCommentToThreadResponse = await self.ws.send_um_and_wait(
            comments.PostCommentToThreadRequest(  # some odd api here
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
            notifications.GetSteamNotificationsRequest()
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.notifications

    async def handle_notifications(self, msg: notifications.GetSteamNotificationsResponse) -> None:
        comment_index = 0
        for notification in msg.notifications:
            match notification.notification_type:
                case 3:  # comment
                    comment_index += 1
                    body: dict[str, Any] = JSON_LOADS(notification.body_data)
                    forum_id = int(body["forum_id"])
                    partial_user = PartialUser(self, body["owner_steam_id"])
                    partial_clan = PartialClan(self, body["owner_steam_id"])
                    match type := _CommentableThreadType(int(body["type"])):
                        case _CommentableThreadType.User:
                            commentable = partial_user
                        case _CommentableThreadType.Clan:
                            commentable = partial_clan
                        case _CommentableThreadType.Event:
                            commentable = await partial_clan.fetch_event(forum_id)
                        case _CommentableThreadType.Announcement:
                            commentable = await partial_clan.fetch_announcement(forum_id)
                        case _CommentableThreadType.PublishedFile:
                            (commentable,) = await self.fetch_published_files(
                                (PublishedFileID(forum_id),), PublishedFileRevision.Latest, None
                            )
                            assert commentable is not None
                        case _CommentableThreadType.Review:
                            commentable = await partial_user.fetch_review(App(id=forum_id))
                        case _CommentableThreadType.Post:
                            commentable = await partial_user.fetch_post(forum_id)
                        case _CommentableThreadType.Topic:
                            log.debug("Ignoring topic comment notification %s", notification)
                            continue
                        case _:
                            log.info(f"Unknown commentable type {type}")
                            continue
                    comments = [
                        comment async for comment in commentable.comments(limit=comment_index)
                    ]  # would be nice if steam gave the id so it could be directly fetched
                    try:
                        self.dispatch("comment", comments[comment_index])
                    except IndexError:
                        pass
                case 9:  # trade, this is only going to happen at startup
                    await self.poll_trades()

        await self.ws.send_um_and_wait(
            notifications.MarkNotificationsReadNotification(
                notification_ids=[
                    notification.notification_id
                    for notification in msg.notifications
                    if notification.notification_type != 9
                ]
            )
        )

    @register(EMsg.ClientCommentNotifications)
    async def handle_comments(self, msg: client_server_2.CMsgClientCommentNotifications) -> None:
        notifications = await self.fetch_notifications()
        while all(notification.notification_type != 3 for notification in notifications):
            await asyncio.sleep(5)  # steam takes a bit to put comments in your notifications
            notifications = await self.fetch_notifications()
        return

    @register(EMsg.ClientEmoticonList)
    def handle_emoticon_list(self, msg: friends.CMsgClientEmoticonList) -> None:
        self.emoticons = [ClientEmoticon(self, emoticon) for emoticon in msg.emoticons]
        self.stickers = [ClientSticker(self, sticker) for sticker in msg.stickers]
        # self.effects = [ClientEffect(self, effect) for effect in msg.effects]  # TODO
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

    @register(EMsg.ClientUserNotifications)
    async def parse_notification(self, msg: client_server_2.CMsgClientUserNotifications) -> None:
        if any(b.user_notification_type == 1 for b in msg.notifications):
            # 1 is a trade offer
            await self.poll_trades()

    @register(EMsg.ClientItemAnnouncements)
    async def parse_new_items(self, msg: client_server_2.CMsgClientItemAnnouncements) -> None:
        if msg.count_new_items:
            await self.poll_trades()

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

    async def fetch_friend_thoughts(self, app_id: AppID) -> reviews.GetFriendsRecommendedAppResponse:
        msg: reviews.GetFriendsRecommendedAppResponse = await self.ws.send_um_and_wait(
            reviews.GetFriendsRecommendedAppRequest(appid=app_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    @register(EMsg.ClientAccountInfo)
    async def parse_account_info(self, msg: login.CMsgClientAccountInfo) -> None:
        await self.login_complete.wait()
        if msg.persona_name != self.user.name:
            before = copy(self.user)
            self.user.name = msg.persona_name or self.user.name
            self.dispatch("user_update", before, self.user)

    async def fetch_friends_who_own(self, app_id: AppID) -> list[ID64]:
        msg: friends.ClientGetFriendsWhoPlayGameResponse = await self.ws.send_proto_and_wait(
            friends.ClientGetFriendsWhoPlayGame(app_id=app_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return cast(list[ID64], msg.friends)

    async def rate_clan_announcement(self, clan_id: ID32, announcement_id: int, upvoted: bool) -> None:
        msg = await self.ws.send_um_and_wait(
            comments.RateClanAnnouncementRequest(
                announcementid=announcement_id,
                clan_accountid=clan_id,
                vote_up=upvoted,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def respond_to_clan_invite(self, clan_id64: ID64, accept: bool) -> None:
        msg: clan.RespondToClanInviteResponse = await self.ws.send_um_and_wait(
            clan.RespondToClanInviteRequest(steamid=clan_id64, accept=accept)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    @register(EMsg.ClientClanState)
    async def update_clan(self, msg: client_server.CMsgClientClanState) -> None:
        await self.handled_chat_groups.wait()
        steam_id = ID(msg.steamid_clan)
        clan = self.get_clan(steam_id.id) or await self.fetch_clan(steam_id.id64, maybe_chunk=False)
        if clan is None:
            return

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
            self.dispatch("clan_update", before, clan)

    @register(EMsg.ClientLicenseList)
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

    @register(EMsg.ClientWalletInfoUpdate)
    def handle_wallet(self, msg: client_server.CMsgClientWalletInfoUpdate) -> None:
        self.wallet = Wallet(
            self, msg.balance64, CurrencyCode.try_value(msg.currency), msg.balance64_delayed, Realm.try_value(msg.realm)
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

    async def fetch_manifest(
        self,
        app_id: AppID,
        id: ManifestID,
        depot_id: DepotID,
        name: str | None = None,
        branch: str = "public",
        password_hash: str = "",
    ) -> Manifest:
        async with self.cs_servers_lock:
            if not self.cs_servers:
                self.cs_servers = sorted(
                    (
                        ContentServer(
                            self,
                            URL_.build(scheme=f"http{'s' * (server.https_support != 'none')}", host=server.vhost),
                            server.weighted_load,
                        )
                        for server in await self.fetch_cs_list(limit=20)
                        if server.type in ("CDN", "SteamCache")
                    ),
                    key=attrgetter("weighted_load"),
                )

        for server in tuple(self.cs_servers):
            try:
                return await server.fetch_manifest(app_id, id, depot_id, name, branch, password_hash)
            except HTTPException as exc:
                if 500 <= exc.status <= 599:
                    del self.cs_servers[0]
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
            apps_to_fetch.extend(
                app_info.CMsgClientPicsProductInfoRequestAppInfo(token.appid, token.access_token)
                for token in fetched_tokens.app_access_tokens
            )
            packages_to_fetch.extend(
                app_info.CMsgClientPicsProductInfoRequestPackageInfo(token.packageid, token.access_token)
                for token in fetched_tokens.package_access_tokens
            )

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
            msg = await self.ws.wait_for(
                app_info.CMsgClientPicsProductInfoResponse, check=lambda msg: msg.header.job_id_target == job_id
            )

            apps.extend(
                AppInfo(
                    self,
                    VDF_LOADS(  # type: ignore  # can be removed if AnyOf ever happens
                        app.buffer[:-1].decode("UTF-8", "replace")
                    )["appinfo"],
                    app,
                )
                for app in msg.apps
            )

            packages.extend(
                PackageInfo(
                    self,
                    VDF_BINARY_LOADS(package.buffer[4:])[  # type: ignore  # can be removed if AnyOf ever happens
                        str(package.packageid)
                    ],
                    package,
                )
                for package in msg.packages
            )

            response_pending = msg.response_pending

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

    async def fetch_store_info(
        self,
        app_ids: Iterable[AppID],
        package_ids: Iterable[PackageID],
        bundle_ids: Iterable[BundleID],
        language: Language | None,
    ) -> list[store.StoreItem]:
        ids = (
            [store.StoreItemId(appid=app_id) for app_id in app_ids]
            + [store.StoreItemId(packageid=package_id) for package_id in package_ids]
            + [store.StoreItemId(bundleid=bundle_id) for bundle_id in bundle_ids]
        )

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
                    # include_screenshots=True,  # steam doesn't like these params for some reason
                    include_trailers=True,
                    include_ratings=True,
                    # include_tag_count=True,
                    include_reviews=True,
                    # include_basic_info=True,
                    # include_supported_languages=True,
                ),
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.store_items

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

    async def request_free_licenses(self, *app_ids: AppID) -> dict[AppID, list[License]]:
        fetched_apps: Sequence[FetchedApp] = await asyncio.gather(*(self.fetch_app(app_id, None) for app_id in app_ids))

        async with self._license_lock:
            old_licenses = self.licenses.copy()
            self.handled_licenses.clear()
            msg: client_server_2.CMsgClientRequestFreeLicenseResponse = await self.ws.send_proto_and_wait(
                client_server_2.CMsgClientRequestFreeLicense(appids=list(app_ids)),
            )
            if msg.result != Result.OK:
                raise WSException(msg)
            if any(app_id not in msg.granted_appids for app_id in app_ids):
                raise WSNotFound(msg)
            if not msg.granted_packageids:
                raise ValueError("No licenses granted")
            await self.handled_licenses.wait()

        ret: dict[AppID, list[License]] = dict.fromkeys(msg.granted_appids)  # type: ignore
        for app_id in ret:
            fetched_app = utils.get(fetched_apps, id=app_id)
            assert fetched_app is not None
            possible_package_ids = {package.id for package in fetched_app._packages if package.is_free()}
            ret[app_id] = [
                l for l in self.licenses.values() if l.id not in old_licenses and l.id in possible_package_ids
            ]
        return ret

    async def fetch_legacy_cd_key(self, app_id: AppID) -> str:
        msg: client_server_2.ClientGetLegacyGameKeyResponse = await self.ws.send_proto_and_wait(
            client_server_2.ClientGetLegacyGameKeyRequest(app_id=app_id),
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.legacy_game_key

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

    @register(EMsg.ClientGameConnectTokens)
    def handle_game_connect_tokens(self, msg: client_server.CMsgClientGameConnectTokens) -> None:
        self._game_connect_bytes.extend(msg.tokens)

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

        if ticket.user == self.user:  # type: ignore
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

    @register(EMsg.ClientTicketAuthComplete)
    def handle_ticket_auth_complete(self, msg: client_server.CMsgClientTicketAuthComplete) -> None:
        ticket = utils.find(
            lambda ticket: crc32(ticket.auth_ticket) == msg.ticket_crc, self._active_auth_tickets.values()
        )
        if ticket is None:
            return log.info("Got auth complete for unknown ticket %r disgaurding", msg.ticket_crc)

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

    async def fetch_user_app_stats(self, user_id64: ID64, app_id: AppID) -> user_stats.CMsgClientGetUserStatsResponse:
        msg: user_stats.CMsgClientGetUserStatsResponse = await self.ws.send_proto_and_wait(
            user_stats.CMsgClientGetUserStats(steam_id_for_user=user_id64, game_id=app_id),
        )

        if msg.result != Result.OK:
            raise WSException(msg)
        return msg

    async def fetch_app_achievements(
        self, app_id: AppID, language: Language | None
    ) -> list[player.GetGameAchievementsResponseAchievement]:
        msg: player.GetGameAchievementsResponse = await self.ws.send_proto_and_wait(
            player.GetGameAchievementsRequest(appid=app_id, language=(self.language or language).api_name)
        )

        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.achievements

    # async def fetch_user_achievements(
    #     self, user_id64: ID64, *app_ids: AppID, language: Language | None
    # ) -> list[player.GetGameAchievementsRequest]:
    #     msg: player.GetAchievementsProgressResponse = await self.ws.send_proto_and_wait(
    #         player.GetAchievementsProgressRequest(
    #             steamid=user_id64,
    #             appids=cast(list[int], list(app_ids)),
    #             language=(self.language or language).api_name,
    #         )
    #     )

    #     if msg.result != Result.OK:
    #         raise WSException(msg)
    #     return

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
