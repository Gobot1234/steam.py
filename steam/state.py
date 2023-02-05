"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import collections
import logging
import re
import weakref
from collections import defaultdict, deque
from collections.abc import Callable, Collection, Iterable, Sequence
from copy import copy
from datetime import datetime, timedelta
from itertools import count
from operator import attrgetter
from time import time
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from bs4 import BeautifulSoup
from typing_extensions import Self
from yarl import URL as URL_

from . import utils
from ._const import HTML_PARSER, URL, VDF_BINARY_LOADS, VDF_LOADS
from .abc import Awardable, BaseUser, Commentable, SteamID
from .channel import DMChannel
from .clan import Clan
from .comment import Comment
from .enums import *
from .errors import *
from .friend import Friend
from .group import Group
from .guard import *
from .invite import ClanInvite, UserInvite
from .manifest import ContentServer, GameInfo, Manifest, PackageInfo
from .message import *
from .message import ClanMessage
from .models import Registerable, register
from .package import License
from .protobufs import (
    EMsg,
    Msg,
    MsgProto,
    app_info,
    chat,
    client_server,
    client_server_2,
    comments,
    content_server,
    do_nothing_case,
    econ,
    friend_messages,
    friends,
    game_servers,
    login,
    loyalty_rewards,
    player,
    published_file,
    reviews,
    struct_messages,
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
from .trade import TradeOffer
from .types.id import ID32
from .user import ClientUser, User
from .utils import DateTime

if TYPE_CHECKING:
    from .abc import Message
    from .client import Client
    from .gateway import SteamWebSocket
    from .types import game, trade, user
    from .types.http import Coro
    from .types.id import ID64, ChannelID, ChatGroupID

log = logging.getLogger(__name__)


T = TypeVar("T")


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
    parsers: dict[EMsg, Callable]

    def __init__(self, client: Client, **kwargs: Any):
        self.client = client
        self.dispatch = client.dispatch
        self.http = client.http

        self.handled_friends = asyncio.Event()
        self.handled_emoticons = asyncio.Event()
        self.handled_chat_groups = asyncio.Event()
        self.handled_group_members = asyncio.Event()
        self.handled_licenses = asyncio.Event()
        self.max_messages: int = kwargs.pop("max_messages", 1000)

        game = kwargs.get("game")
        games = kwargs.get("games")
        games = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games.append(game.to_dict())
        self._games: list[game.GameToDict] = games
        self._state: PersonaState = kwargs.get("state", PersonaState.Online)
        self._ui_mode: UIMode = kwargs.get("ui_mode", UIMode.Desktop)
        self._flags: PersonaStateFlag = kwargs.get("flags", PersonaStateFlag.NONE)
        self._force_kick: bool = kwargs.get("force_kick", False)
        self.auto_chunk_chat_groups: bool = kwargs.get("auto_chunk_chat_groups", False)

        self.clear()

    def clear(self) -> None:
        self._users: weakref.WeakValueDictionary[ID32, User] = weakref.WeakValueDictionary()
        self._trades: dict[int, TradeOffer] = {}

        self._groups: dict[ChatGroupID, Group] = {}
        self._clans: dict[ID32, Clan] = {}
        self._clans_by_chat_id: dict[ChatGroupID, Clan] = {}
        self.chat_group_to_view_id: defaultdict[ChatGroupID, int] = defaultdict(count().__next__)
        self.active_chat_groups: set[ChatGroupID] = set()
        self.chat_group_members_waiting: dict[tuple[int, int], asyncio.Future[list[User]]] = {}

        self._confirmations: dict[int, Confirmation] = {}
        self.confirmation_generation_locks: dict[str, tuple[asyncio.Lock, datetime]] = {}
        self._confirmations_to_ignore: list[int] = []
        self._messages: deque[Message] = deque(maxlen=self.max_messages or 0)
        self.invites: dict[ID64, UserInvite | ClanInvite] = {}
        self.emoticons: list[ClientEmoticon] = []
        self.stickers: list[ClientSticker] = []

        self.polling_trades = False
        self.trade_queue = Queue[TradeOffer]()
        self._trades_to_watch: set[int] = set()
        self._trades_received_cache: Sequence[dict[str, Any]] = ()
        self._trades_sent_cache: Sequence[dict[str, Any]] = ()
        self.polling_confirmations = False
        self.confirmation_queue = Queue[Confirmation](attr=attrgetter("creator_id"))

        self.licenses: dict[int, License] = {}
        self._manifest_passwords: dict[int, dict[str, str]] = {}
        self.cs_servers: list[ContentServer] = []
        self.cs_lock = asyncio.Lock()

        self.handled_friends.clear()
        self.handled_emoticons.clear()
        self.handled_chat_groups.clear()
        self.handled_licenses.clear()

    async def __ainit__(self) -> None:
        if self.http.api_key is not None:
            self._device_id = generate_device_id(self.user)

            await self.poll_trades()

    @utils.cached_property
    def ws(self) -> SteamWebSocket:
        assert self.client.ws is not None
        return self.client.ws

    @utils.cached_property
    def user(self) -> ClientUser:
        assert self.http.user is not None
        return self.http.user

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

    async def fetch_user(self, user_id64: int) -> User | None:
        data = await self.http.get_user(user_id64)
        return self._store_user(data) if data else None
        # return (await self.fetch_users([user_id64]))[0]

    async def fetch_users(self, user_id64s: Iterable[int]) -> list[User | None]:
        resp = await self.http.get_users(user_id64s)
        """
        msg: MsgProto[CMsgClientRequestFriendData] = MsgProto(
            EMsg.ClientRequestFriendData,
            persona_state_requested=863,  # 1 | 2 | 4 | 8 | 16 | 64 | 256 | 512  corresponds to EClientPersonaStateFlag
            friends=user_id64s,
        )
        await self.ws.send_as_proto(msg)
        """

        return [self._store_user(data) for data in resp]

    async def _maybe_user(self, id64: ID64) -> User | SteamID:
        steam_id = SteamID(id64)
        return self.get_user(steam_id.id) or await self.fetch_user(id64) or steam_id

    async def _maybe_users(self, id64s: Iterable[ID64]) -> list[User | SteamID]:
        ret: list[User | SteamID] = []
        to_fetch: dict[ID64, list[int]] = {}
        for idx, id64 in enumerate(id64s):
            steam_id = SteamID(id64)
            user = self.get_user(steam_id.id)
            if user is not None:
                ret.append(user)
            else:
                idxs = to_fetch.get(id64)
                if idxs is None:
                    idxs = to_fetch[id64] = []

                idxs.append(idx)
                ret.append(steam_id)

        if to_fetch:
            for idxs, user in zip(to_fetch.values(), await self.fetch_users(to_fetch)):
                if user is not None:
                    for idx in idxs:
                        ret[idx] = user

        return ret

    def _store_user(self, data: user.User) -> User:
        try:
            user = self._users[int(data["steamid"]) & 0xFFFFFFFF]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id] = user
        else:
            user._update(data)
        return user

    def get_friend(self, id64: ID64) -> Friend:
        return self.user._friends[id64]

    def get_group(self, id: ChatGroupID) -> Group | None:
        return self._groups.get(id)

    def get_clan(self, id: ID32) -> Clan | None:
        return self._clans.get(id)

    async def fetch_clan(self, id64: ID64, *, maybe_chunk: bool = True) -> Clan | None:
        msg: MsgProto[chat.GetClanChatRoomInfoResponse] = await self.ws.send_um_and_wait(
            "ClanChatRooms.GetClanChatRoomInfo", steamid=id64
        )
        if msg.result == Result.Busy:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        clan = await Clan._from_proto(self, msg.body.chat_group_summary, maybe_chunk=maybe_chunk)
        self._clans[clan.id] = clan
        return clan

    def get_trade(self, id: int) -> TradeOffer | None:
        return self._trades.get(id)

    async def fetch_trade(self, id: int, language: Language | None) -> TradeOffer | None:
        resp = await self.http.get_trade(id, language)
        data = resp.get("response")
        if data:
            trades = await self._process_trades((data["offer"],), data.get("descriptions", ()))
            return trades[0]

    async def _store_trade(self, data: trade.TradeOffer) -> TradeOffer:
        try:
            trade = self._trades[int(data["tradeofferid"])]
        except KeyError:
            log.info(f'Received trade #{data["tradeofferid"]}')
            trade = TradeOffer._from_api(
                state=self, data=data, partner=await self._maybe_user(utils.make_id64(data["accountid_other"]))
            )
            self._trades[trade.id] = trade
            if trade.state in (TradeOfferState.Active, TradeOfferState.ConfirmationNeed) and (
                trade.items_to_send or trade.items_to_receive  # trade could be glitched
            ):
                self.dispatch("trade_send" if trade.is_our_offer() else "trade_receive", trade)
                self._trades_to_watch.add(trade.id)
        else:
            before_state = trade.state
            trade._update(data)
            if trade.state != before_state:
                log.info(f"Trade #{trade.id} has updated its trade state to {trade.state}")
                event_name = trade.state.event_name
                if event_name and (trade.items_to_send or trade.items_to_receive):
                    self.dispatch(f"trade_{event_name}", trade)
                    self._trades_to_watch.discard(trade.id)
        return trade

    async def _process_trades(
        self, trades: Iterable[trade.TradeOffer], descriptions: Collection[trade.Description]
    ) -> list[TradeOffer]:
        ret = []
        for trade in trades:
            for item in descriptions:
                for asset in trade.get("items_to_receive", ()):
                    if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                        asset.update(item)
                for asset in trade.get("items_to_give", ()):
                    if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                        asset.update(item)
            ret.append(await self._store_trade(trade))
        return ret

    async def poll_trades(self) -> None:
        if self.polling_trades or not self.http.api_key:
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

    async def wait_for_trade(self, id: int) -> TradeOffer:
        self.loop.create_task(self.poll_trades())  # start re-polling trades
        return await self.trade_queue.wait_for(id=id)

    # confirmations

    def get_confirmation(self, id: int) -> Confirmation | None:
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id: int) -> Confirmation | None:
        await self.fill_confirmations()
        return self._confirmations.get(id)

    async def fill_confirmations(self) -> None:
        key, timestamp = await self._generate_confirmation_code("list")
        data = await self.http.get(
            URL.COMMUNITY / "mobileconf/getlist",
            params={"p": self._device_id, "a": self.user.id64, "k": key, "t": timestamp, "m": "react", "tag": "list"},
        )
        if not data.get("success", False):
            raise ConfirmationError(f"{data.get('message', 'Unknown error')}\n{data.get('detail') or ''}".strip())

        confirmations: list[Confirmation] = []
        for confirmation in data["conf"]:
            confirmation_ = Confirmation(
                self, int(confirmation["id"]), int(confirmation["nonce"]), int(confirmation["creator_id"])
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

    async def wait_for_confirmation(self, id: int) -> Confirmation:
        self.loop.create_task(self.poll_confirmations())
        return await self.confirmation_queue.wait_for(id=id)

    async def fetch_and_confirm_confirmation(self, trade_id: int) -> bool:
        if self.client.identity_secret:
            confirmation = await self.wait_for_confirmation(id=trade_id)
            if confirmation is not None:
                await confirmation.confirm()
                return True

        return False

    # ws stuff

    @property
    def _chat_groups(self) -> utils.ChainMap[ChatGroupID, Group | Clan]:
        return utils.ChainMap(self._clans_by_chat_id, self._groups)  # type: ignore  # needs HKT

    async def send_user_message(self, user_id64: int, content: str) -> UserMessage:
        contains_bbcode = utils.contains_bbcode(content)
        msg: MsgProto[friend_messages.SendMessageResponse] = await self.ws.send_um_and_wait(
            "FriendMessages.SendMessage",
            steamid=user_id64,
            message=content.replace("[", "\\[") if contains_bbcode else content,
            chat_entry_type=ChatEntryType.Text,
            contains_bbcode=contains_bbcode,
        )

        if msg.result == Result.LimitExceeded:
            raise WSForbidden(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        proto = friend_messages.IncomingMessageNotification(
            chat_entry_type=ChatEntryType.Text,
            message=content,
            rtime32_server_timestamp=msg.body.server_timestamp,
            ordinal=msg.body.ordinal,
            message_no_bbcode=msg.body.message_without_bb_code,
        )
        channel = DMChannel(state=self, participant=self.get_user(user_id64 & 0xFFFFFFFF))  # type: ignore
        message = UserMessage(proto=proto, channel=channel)
        message.author = self.user
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def send_user_typing(self, user_id64: int) -> None:
        await self.ws.send_um(
            "FriendMessages.SendMessage",
            steamid=user_id64,
            chat_entry_type=ChatEntryType.Typing,
        )
        self.dispatch("typing", self.user, DateTime.now())

    async def react_to_user_message(
        self, user_id64: int, server_timestamp: int, ordinal: int, reaction_name: str, reaction_type: int, is_add: bool
    ) -> None:
        await self.ws.send_um_and_wait(
            "FriendMessages.UpdateMessageReaction",
            steamid=user_id64,
            server_timestamp=server_timestamp,
            ordinal=ordinal,
            reaction=reaction_name,
            reaction_type=reaction_type,
            is_add=is_add,
        )

    async def send_chat_message(
        self, chat_group_id: ChatGroupID, chat_id: ChannelID, content: str
    ) -> ClanMessage | GroupMessage:
        msg: MsgProto[chat.SendChatMessageResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.SendChatMessage", chat_id=chat_id, chat_group_id=chat_group_id, message=content
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
            steamid_sender=0,
            message=content,
            ordinal=msg.body.ordinal,
            message_no_bbcode=msg.body.message_without_bb_code,
            timestamp=int(time()),
        )
        group = self._chat_groups[chat_group_id]
        channel = group._channels[chat_id]
        channel._update(proto)

        message = (ClanMessage if isinstance(group, Clan) else GroupMessage)(
            proto=proto,
            channel=channel,  # type: ignore  # type checkers can't figure out this is ok
            author=self.user,
        )
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def react_to_chat_message(
        self,
        chat_group_id: ChatGroupID,
        chat_id: ChannelID,
        server_timestamp: int,
        ordinal: int,
        reaction_name: str,
        reaction_type: int,
        is_add: bool,
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.UpdateMessageReaction",
            chat_group_id=chat_group_id,
            chat_id=chat_id,
            server_timestamp=server_timestamp,
            ordinal=ordinal,
            reaction=reaction_name,
            reaction_type=reaction_type,
            is_add=is_add,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

    async def join_chat_group(self, chat_group_id: ChatGroupID, invite_code: str | None = None) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.JoinChatRoomGroup", chat_group_id=chat_group_id, invite_code=invite_code or ""
        )

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def leave_chat_group(self, chat_group_id: ChatGroupID) -> None:
        msg = await self.ws.send_um_and_wait("ChatRoom.LeaveChatRoomGroup", chat_group_id=chat_group_id)

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def invite_user_to_chat_group(self, user_id64: int, chat_group_id: ChatGroupID) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.InviteFriendToChatRoomGroup", chat_group_id=chat_group_id, steamid=user_id64
        )

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def request_chat_group_members(
        self,
        chat_group_id: ChatGroupID,
        view_id: int,
        client_change_number: int,
        start: int,
        stop: int,
    ) -> list[User]:
        self.chat_group_members_waiting[(view_id, client_change_number)] = future = asyncio.Future()
        await self.ws.send_um(
            "ChatRoom.UpdateMemberListView",
            chat_group_id=chat_group_id,
            view_id=view_id,
            start=start,
            end=stop,
            client_changenumber=client_change_number,
        )
        return await future

    def handle_member_list_view_update(self, msg: MsgProto[chat.MemberListViewUpdatedNotification]):
        self.chat_group_members_waiting[msg.body.view_id, msg.body.view.client_changenumber].set_result(
            [self._store_user(self.patch_user_from_ws({}, member.persona)) for member in msg.body.members]
        )

    async def edit_role_name(self, chat_group_id: ChatGroupID, role_id: int, name: str) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.RenameRole", chat_group_id=chat_group_id, role_id=role_id, name=name
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def edit_role_permissions(
        self, chat_group_id: ChatGroupID, role_id: int, permissions: RolePermissions
    ) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.ReplaceRoleActions",
            chat_group_id=chat_group_id,
            role_id=role_id,
            actions=permissions.to_dict(),
        )
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def delete_role(self, chat_group_id: ChatGroupID, role_id: int) -> None:
        msg = await self.ws.send_um_and_wait("ChatRoom.DeleteRole", chat_group_id=chat_group_id, role_id=role_id)
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
        msg: MsgProto[friend_messages.GetRecentMessagesResponse] = await self.ws.send_um_and_wait(
            "FriendMessages.GetRecentMessages",
            steamid1=self.user.id64,
            steamid2=user_id64,
            rtime32_start_time=start,
            bbcode_format=False,
            time_last=last,
            start_ordinal=start_ordinal,
            count=100,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_group_history(
        self, chat_group_id: ChatGroupID, chat_id: ChannelID, start: int, last: int, last_ordinal: int
    ) -> chat.GetMessageHistoryResponse:
        msg: MsgProto[chat.GetMessageHistoryResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.GetMessageHistory",
            chat_group_id=chat_group_id,
            chat_id=chat_id,
            last_time=last,
            start_time=start,
            last_ordinal=last_ordinal,
            max_count=100,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_message_reactors(
        self,
        chat_group_id: ChatGroupID,
        chat_id: ChannelID,
        server_timestamp: int,
        ordinal: int,
        reaction_name: str,
        reaction_type: int,
    ) -> list[ID32]:
        msg: MsgProto[chat.GetMessageReactionReactorsResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.GetMessageReactionReactors",
            chat_group_id=chat_group_id,
            chat_id=chat_id,
            server_timestamp=server_timestamp,
            ordinal=ordinal,
            reaction=reaction_name,
            reaction_type=reaction_type,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.reactors

    async def fetch_servers(self, query: str, limit: int) -> list[game_servers.GetServerListResponseServer]:
        msg: MsgProto[game_servers.GetServerListResponse] = await self.ws.send_um_and_wait(
            "GameServers.GetServerList",
            filter=query,
            limit=limit,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.servers

    async def fetch_server_ip_from_steam_id(self, *ids: int) -> list[game_servers.IPsWithSteamIDsResponseServer]:
        msg: MsgProto[game_servers.IPsWithSteamIDsResponse] = await self.ws.send_um_and_wait(
            "GameServers.GetServerIPsBySteamID",
            server_steamids=list(ids),
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.servers

    async def query_server(
        self, ip: int, port: int, app_id: int, type: game_servers.EQueryType
    ) -> game_servers.QueryResponse:
        msg: MsgProto[game_servers.QueryResponse] = await self.ws.send_um_and_wait(
            "GameServers.QueryByFakeIP",
            query_type=type,
            fake_ip=ip,  # why these are "fake" I'm not really sure
            fake_port=port,
            app_id=app_id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    async def fetch_game_player_count(self, game_id: int) -> int:
        msg: MsgProto[client_server_2.CMsgDpGetNumberOfCurrentPlayersResponse] = await self.ws.send_proto_and_wait(
            MsgProto(EMsg.ClientGetNumberOfCurrentPlayersDP, appid=game_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.player_count

    async def fetch_user_games(self, user_id64: int, include_free: bool) -> list[player.GetOwnedGamesResponseGame]:
        msg: MsgProto[player.GetOwnedGamesResponse] = await self.ws.send_um_and_wait(
            "Player.GetOwnedGames",
            steamid=user_id64,
            include_appinfo=True,
            include_played_free_games=include_free,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.games

    async def fetch_friend_profile_info(self, user_id64: int) -> friends.CMsgClientFriendProfileInfoResponse:
        msg: MsgProto[friends.CMsgClientFriendProfileInfoResponse] = await self.ws.send_proto_and_wait(
            MsgProto(EMsg.ClientFriendProfileInfo, steamid_friend=user_id64)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_user_equipped_profile_items(
        self,
        user_id64: int,
        language: Language | None,
    ) -> player.GetProfileItemsEquippedResponse:
        msg: MsgProto[player.GetProfileItemsEquippedResponse] = await self.ws.send_um_and_wait(
            "Player.GetProfileItemsEquipped",
            steamid=user_id64,
            language=(language or self.language).api_name,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_user_profile_customisation(
        self,
        user_id64: int,
        language: Language | None,
    ):
        msg: MsgProto[player.GetProfileCustomizationResponse] = await self.ws.send_um_and_wait(
            "Player.GetProfileCustomization",
            steamid=user_id64,
            include_inactive_customizations=True,
            include_purchased_customizations=True,
            language=(language or self.language).api_name,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_profile_items(self, language: Language | None) -> player.GetProfileItemsOwnedResponse:
        msg: MsgProto[player.GetProfileItemsOwnedResponse] = await self.ws.send_um_and_wait(
            "Player.GetProfileItemsOwned",
            language=(language or self.language).api_name,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_user_favourite_badge(self, user_id64: ID64) -> player.GetFavoriteBadgeResponse:
        msg: MsgProto[player.GetFavoriteBadgeResponse] = await self.ws.send_um_and_wait(
            "Player.GetFavoriteBadge",
            steamid=user_id64,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_trade_url(self, generate_new: bool) -> str:
        msg: MsgProto[econ.GetTradeOfferAccessTokenResponse] = await self.ws.send_um_and_wait(
            "Econ.GetTradeOfferAccessToken", generate_new_token=generate_new
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return (
            f"https://steamcommunity.com/tradeoffer/new/?partner={self.user.id}"
            f"&token={msg.body.trade_offer_access_token}"
        )

    # parsers

    @register(EMsg.ServiceMethod)
    async def parse_service_method(self, msg: MsgProto[Any]) -> None:
        name = msg.header.body.job_name_target
        if name == "ChatRoomClient.NotifyIncomingChatMessage":
            await self.handle_chat_message(msg)
        elif name == "ChatRoomClient.NotifyMessageReaction":
            await self.handle_chat_message_reaction(msg)
        elif name == "ChatRoomClient.NotifyChatRoomHeaderStateChange":
            await self.handle_chat_group_update(msg)
        elif name == "ChatRoomClient.NotifyChatGroupUserStateChanged":
            await self.handle_chat_group_user_action(msg)
        elif name == "ChatRoomClient.NotifyMemberStateChange":
            await self.handle_chat_member_update(msg)
        elif name == "ChatRoomClient.NotifyChatRoomGroupRoomsChange":
            await self.handle_chat_update(msg)
        elif name == "FriendMessagesClient.IncomingMessage":
            await self.handle_user_message(msg)
        elif name == "FriendMessagesClient.MessageReaction":
            await self.handle_user_message_reaction(msg)
        elif name == "ChatRoomClient.NotifyMemberListViewUpdated":
            self.handle_member_list_view_update(msg)
        else:
            log.debug("Got an event %r that we don't handle %r", msg.header.body.job_name_target, msg.body)

    async def handle_user_message(self, msg: MsgProto[friend_messages.IncomingMessageNotification]) -> None:
        partner = await self._maybe_user(msg.body.steamid_friend)  # FIXME shouldn't ever be out of cache
        author = self.user if msg.body.local_echo else partner  # local_echo is always us

        if msg.body.chat_entry_type == ChatEntryType.Text:
            channel = DMChannel(state=self, participant=partner)  # type: ignore  # remove when above fixme removed
            message = UserMessage(proto=msg.body, channel=channel)
            message.author = author
            self._messages.append(message)
            self.dispatch("message", message)

        if msg.body.chat_entry_type == ChatEntryType.Typing:
            when = DateTime.from_timestamp(msg.body.rtime32_server_timestamp)
            self.dispatch("typing", author, when)

    async def handle_user_message_reaction(self, msg: MsgProto[friend_messages.MessageReactionNotification]) -> None:
        user = await self._maybe_user(msg.body.steamid_friend)
        ordinal = msg.body.ordinal
        created_at = DateTime.from_timestamp(msg.body.server_timestamp)
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
        if msg.body.reaction_type == 1:
            emoticon = Emoticon(self, msg.body.reaction)
            sticker = None
        elif msg.body.reaction_type == 2:
            sticker = Sticker(self, msg.body.reaction)
            emoticon = None
        else:
            return log.debug(
                "Got an unknown reaction_type %s on message %s %s", msg.body.reaction_type, created_at, ordinal
            )

        reaction = MessageReaction(self, message, emoticon, sticker, user, created_at, ordinal)
        self.dispatch(f"reaction_{'add' if msg.body.is_add else 'remove'}", reaction)

    async def handle_chat_message(self, msg: MsgProto[chat.IncomingChatMessageNotification]) -> None:
        try:
            destination = self._chat_groups[msg.body.chat_group_id]
        except KeyError:
            return log.debug(f"Got a message for a chat we aren't in {msg.body.chat_group_id}")

        channel = destination._channels[msg.body.chat_id]
        channel._update(msg.body)
        author = await self._maybe_user(msg.body.steamid_sender)
        message = (ClanMessage if isinstance(destination, Clan) else GroupMessage)(
            proto=msg.body,
            channel=channel,  # type: ignore  # type checkers aren't able to figure out this is ok
            author=author,
        )
        self._messages.append(message)
        self.dispatch("message", message)

    async def handle_chat_message_reaction(self, msg: MsgProto[chat.MessageReactionNotification]) -> None:
        user = await self._maybe_user(msg.body.reactor)
        ordinal = msg.body.ordinal
        created_at = DateTime.from_timestamp(msg.body.server_timestamp)
        location = (msg.body.chat_group_id, msg.body.chat_id)
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
        if msg.body.reaction_type == 1:
            emoticon = Emoticon(self, msg.body.reaction)
            sticker = None
        elif msg.body.reaction_type == 2:
            sticker = Sticker(self, msg.body.reaction)
            emoticon = None
        else:
            return log.debug("Got an unknown reaction_type %s", msg.body.reaction_type)

        reaction = MessageReaction(self, message, emoticon, sticker, user, created_at, ordinal)
        self.dispatch(f"reaction_{'add' if msg.body.is_add else 'remove'}", reaction)

    async def handle_chat_group_update(self, msg: MsgProto[chat.ChatRoomHeaderStateNotification]) -> None:
        try:
            chat_group = self._chat_groups[msg.body.header_state.chat_group_id]
        except KeyError:
            return log.debug(f"Updating a group that isn't cached {msg.body.header_state.chat_group_id}")

        before = copy(chat_group)
        before._roles = {r_id: copy(r) for r_id, r in before._roles.items()}
        chat_group._update_header_state(msg.body.header_state)
        self.dispatch(f"{'group' if isinstance(chat_group, Group) else 'clan'}_update", before, chat_group)

    async def handle_chat_group_user_action(
        self, msg: MsgProto[chat.NotifyChatGroupUserStateChangedNotification]
    ) -> None:
        if msg.body.user_action == chat.EChatRoomMemberStateChange.Joined:  # join group
            if msg.body.group_summary.clanid:
                clan = await Clan._from_proto(self, msg.body.group_summary)
                self._clans[clan.id] = clan
                assert clan._id is not None
                self._clans_by_chat_id[clan._id] = clan
                self.dispatch("clan_join", clan)
            else:
                group = await Group._from_proto(self, msg.body.group_summary)
                self._groups[group.id] = group
                self.dispatch("group_join", group)

        elif msg.body.user_action == chat.EChatRoomMemberStateChange.Parted:  # leave group
            left = self._chat_groups.pop(msg.body.chat_group_id, None)
            if left is None:
                return

            if isinstance(left, Clan):
                self.dispatch("clan_leave", left)
            else:
                self.dispatch("group_leave", left)
        # elif msg.body.user_action == chat.EChatRoomMemberStateChange.Invited:
        #     if msg.body.group_summary.clanid:
        #         return
        #     group = await Group._from_proto(self, msg.body.group_summary)
        #     self._groups[group.id] = group
        #     self.dispatch("group_invite", group)

    async def handle_chat_member_update(self, msg: MsgProto[chat.MemberStateChangeNotification]) -> None:
        if msg.body.user_action == chat.EChatRoomMemberStateChange.Joined:
            try:
                chat_group = self._chat_groups[msg.body.chat_group_id]
            except KeyError:
                return log.debug("Got a chat member update for a chat group we aren't in %d", msg.body.chat_group_id)
            member = await chat_group._add_member(msg.body.member)
            self.dispatch("member_join", chat_group, member)
        elif msg.body.user_action == chat.EChatRoomMemberStateChange.Parted:
            try:
                chat_group = self._chat_groups[msg.body.chat_group_id]
            except KeyError:
                return log.debug("Got a chat member update for a chat group we aren't in %d", msg.body.chat_group_id)
            member = chat_group._remove_member(msg.body.member)
            if member is None:
                return
            self.dispatch("member_leave", chat_group, member)
        # TODO: handle other user_actions

    async def handle_chat_update(self, msg: MsgProto[chat.ChatRoomGroupRoomsChangeNotification]):
        try:
            chat_group = self._chat_groups[msg.body.chat_group_id]
        except KeyError:
            return log.debug("Got an update for a chat group we aren't in %d", msg.body.chat_group_id)

        before = copy(chat_group)
        before._channels = {c_id: copy(c) for c_id, c in before._channels.items()}
        chat_group._update_channels(msg.body.chat_rooms)
        self.dispatch(f"{chat_group.__class__.__name__}_update", before, chat_group)

    @register(EMsg.ServiceMethodResponse)
    async def parse_service_method_response(self, msg: MsgProto[Any]) -> None:
        name = msg.header.body.job_name_target
        if name == "ChatRoom.GetMyChatRoomGroups":
            msg: MsgProto[chat.GetMyChatRoomGroupsResponse] = msg
            for chat_group in msg.body.chat_room_groups:
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

            self.handled_chat_groups.set()  # signal to process_group_members that we are ready
            await self.handled_friends.wait()  # ensure friend cache is ready
            await self.handled_emoticons.wait()  # ensure emoticon cache is ready
            await self.handled_licenses.wait()  # ensure licenses are ready
            await self.client._handle_ready()
        else:
            log.debug("Got a service method response for %r we don't handle", msg.header.body.job_name_target)

    @register(EMsg.ClientPersonaState)
    async def parse_persona_state_update(self, msg: MsgProto[friends.CMsgClientPersonaState]) -> None:
        for friend in msg.body.friends:
            data = friend.to_dict(do_nothing_case)
            if not data:
                continue
            steam_id = SteamID(friend.friendid)
            after = self.get_user(steam_id.id)
            if after is None:  # they're private
                continue

            before = copy(after)

            try:
                data = self.patch_user_from_ws(data, friend)
            except (KeyError, TypeError):
                invitee = await self._maybe_user(steam_id.id64)
                invite = UserInvite(self, invitee, FriendRelationship.RequestRecipient)
                return self.dispatch("user_invite", invite)

            after._update(data)
            old = [getattr(before, attr, None) for attr in BaseUser.__slots__]
            new = [getattr(after, attr, None) for attr in BaseUser.__slots__]
            if old != new:
                self.dispatch("user_update", before, after)

    def patch_user_from_ws(self, data: dict[str, Any], friend: friends.CMsgClientPersonaStateFriend) -> user.User:
        data["personaname"] = friend.player_name
        data["steamid"] = friend.friendid
        data["avatarfull"] = utils._get_avatar_url(friend.avatar_hash)

        if friend.last_logoff:
            data["lastlogoff"] = friend.last_logoff
        data["gameextrainfo"] = friend.game_name or None
        data["personastate"] = friend.persona_state
        data["personastateflags"] = friend.persona_state_flags
        data["rich_presence"] = {m.key: m.value for m in friend.rich_presence}
        return data  # type: ignore  # casting is for losers

    def _add_friend(self, user: User) -> Friend:
        self.user._friends[user.id] = friend = Friend(self, user)
        return friend

    @register(EMsg.ClientFriendsList)
    async def process_friends(self, msg: MsgProto[friends.CMsgClientFriendsList]) -> None:
        elements = None
        client_user_friends: list[ID64] = []
        is_load = not msg.body.bincremental
        for friend in msg.body.friends:
            relationship = FriendRelationship.try_value(friend.efriendrelationship)
            steam_id = SteamID(friend.ulfriendid)

            if relationship == FriendRelationship.Friend:
                try:
                    invite = self.invites.pop(steam_id.id64)
                except KeyError:
                    if is_load:
                        client_user_friends.append(steam_id.id64)
                    else:
                        user = await self.fetch_user(steam_id.id64)
                        assert user is not None
                        self._add_friend(user)
                else:
                    if isinstance(invite, UserInvite):
                        assert not isinstance(invite.invitee, SteamID)
                        self.dispatch("user_invite_accept", invite)
                        if isinstance(invite.invitee, User):
                            friend = self._add_friend(invite.invitee)
                            self.dispatch("friend_add", friend)
                    else:
                        self.dispatch("clan_invite_accept", invite)
                        if isinstance(invite.clan, Clan):
                            self._clans[invite.clan.id] = invite.clan
            elif relationship in (
                FriendRelationship.RequestInitiator,
                FriendRelationship.RequestRecipient,
            ):
                if steam_id.type == Type.Individual:
                    invitee = await self._maybe_user(steam_id.id64)
                    invite = UserInvite(state=self, invitee=invitee, relationship=relationship)
                    self.invites[invitee.id64] = invite
                    self.dispatch("user_invite", invite)
                if steam_id.type == Type.Clan:
                    if elements is None:
                        resp = await self.http.get(URL.COMMUNITY / "my/groups/pending", params={"ajax": "1"})
                        soup = BeautifulSoup(resp, HTML_PARSER)
                        elements = soup.find_all("a", class_="linkStandard")
                    invitee_id64 = next(
                        (
                            utils.make_id64(elements[idx + 1]["data-miniprofile"])
                            for idx, element in enumerate(elements)
                            if str(steam_id.id64) in str(element)
                        ),
                        0,
                    )

                    invitee = await self._maybe_user(invitee_id64)
                    try:
                        clan = await self.fetch_clan(steam_id.id64) or steam_id
                    except WSException:
                        clan = steam_id
                    invite = ClanInvite(state=self, invitee=invitee, clan=clan, relationship=relationship)
                    self.invites[clan.id64] = invite
                    self.dispatch("clan_invite", invite)

            elif relationship == FriendRelationship.NONE and steam_id.type == Type.Individual:
                try:
                    invite = self.invites.pop(steam_id.id64)
                except KeyError:
                    friend = self.user._friends.pop(steam_id.id64, None)
                    if friend is None:
                        return log.debug("Unknown friend %s removed", steam_id)
                    self.dispatch("user_remove", friend)  # TODO remove
                    self.dispatch("friend_remove", friend)
                else:
                    self.dispatch(f"{'user'if steam_id.type == Type.Individual else 'clan'}_invite_decline", invite)
        if is_load:
            self.user._friends = {user.id64: Friend(self, user) for user in await self._maybe_users(client_user_friends)}  # type: ignore
            self.handled_friends.set()

    async def set_chat_group_active(self, chat_group_id: ChatGroupID) -> chat.GroupState:
        self.active_chat_groups.add(chat_group_id)
        proto: MsgProto[chat.SetSessionActiveChatRoomGroupsResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.SetSessionActiveChatRoomGroups",
            chat_group_ids=list(self.active_chat_groups),
            chat_groups_data_requested=[chat_group_id],
        )

        try:
            (state,) = proto.body.chat_states
        except ValueError:
            raise WSForbidden(proto) from None
        return state

    async def fetch_chat_group_roles(self, chat_group_id: ChatGroupID) -> list[chat.Role]:
        msg: MsgProto[chat.GetRolesResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.GetRoles", chat_group_id=chat_group_id
        )
        if msg.result == Result.AccessDenied:
            raise WSForbidden(msg)
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.roles

    async def fetch_comment(self, owner: Commentable, id: int) -> comments.GetCommentThreadResponse.Comment:
        msg: MsgProto[comments.GetCommentThreadResponse] = await self.ws.send_um_and_wait(
            "Community.GetCommentThread", **owner._commentable_kwargs, id=id
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.comments[0]

    async def fetch_comments(
        self, owner: Commentable, count: int, starting_from: int, oldest_first: bool
    ) -> comments.GetCommentThreadResponse:
        msg: MsgProto[comments.GetCommentThreadResponse] = await self.ws.send_um_and_wait(
            "Community.GetCommentThread",
            **owner._commentable_kwargs,
            count=count,
            start=starting_from,
            oldest_first=oldest_first,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def post_comment(self, owner: Commentable, content: str, subscribe: bool) -> Comment[Commentable]:
        msg: MsgProto[comments.PostCommentToThreadResponse] = await self.ws.send_um_and_wait(
            "Community.PostCommentToThread",
            **owner._commentable_kwargs,
            content=content,
            surpress_notifications=not subscribe,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        comment = Comment(
            self,
            id=msg.body.id,
            content=content,
            created_at=self.steam_time,
            author=self.user,
            owner=owner,
            reactions=[],
        )
        self.dispatch("comment", comment)
        return comment

    async def delete_comment(self, owner: Commentable, comment_id: int) -> None:
        msg: MsgProto[comments.DeleteCommentFromThreadResponse] = await self.ws.send_um_and_wait(
            "Community.DeleteCommentFromThread",
            **owner._commentable_kwargs,
            id=comment_id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def report_comment(self, owner: Commentable, comment_id: int) -> None:
        msg: MsgProto[comments.PostCommentToThreadResponse] = await self.ws.send_um_and_wait(
            "Community.PostCommentToThread",  # some odd api here
            **owner._commentable_kwargs,
            is_report=True,
            id=comment_id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    @register(EMsg.ClientCommentNotifications)
    async def handle_comments(self, msg: MsgProto[client_server_2.CMsgClientCommentNotifications]) -> None:
        resp = await self.http.get(URL.COMMUNITY / "my/commentnotifications")
        soup = BeautifulSoup(resp, HTML_PARSER)

        cached: dict[URL_, list[Commentable | int]] = {}
        for attr in soup.find_all("div", class_="commentnotification_click_overlay", limit=msg.body.count_new_comments):
            url = URL_(attr.contents[1]["href"])
            url_with_no_query = url.with_query(None)
            if url_with_no_query in cached:
                cached[url_with_no_query][1] += 1  # type: ignore
                commentable, index = cached[url_with_no_query]  # type: ignore
                commentable: Commentable
                index: int
            else:
                steam_id = await SteamID.from_url(url, self.http._session)
                if steam_id is None:
                    continue
                if steam_id.type == Type.Individual:
                    commentable = self.get_user(steam_id.id) or await self.fetch_user(steam_id.id64)  # type: ignore
                else:
                    clan = self.get_clan(steam_id.id) or await self.fetch_clan(steam_id.id64)
                    if clan is None:
                        continue
                    # now that we have the clan that the comment was posted in, if the url has a hash in the path we can
                    # extract the type of the comment section the comment is in.
                    if "#" not in url.path:
                        commentable = clan
                    else:
                        path, _, end = url.path.partition("#")[-1].partition("/")
                        if path == "events":
                            commentable = await clan.fetch_event(re.findall(r"([0-9]*)", end)[0])
                        elif path == "announcements":
                            commentable = await clan.fetch_announcement(re.findall(r"detail/([0-9]*)", end)[0])
                        else:
                            log.debug(f"Got a comment for a type we cannot handle {path}")
                            continue
                if commentable is None:
                    continue
                index = 0
                cached[url_with_no_query] = [commentable, index]

            try:
                timestamp = int(url.query["tscn"])
            except KeyError:
                log.debug("Got a comment without a timestamp")
                continue

            after = DateTime.from_timestamp(timestamp) - timedelta(minutes=1)

            comments = [comment async for comment in commentable.comments(limit=index + 1, after=after)]

            try:
                self.dispatch("comment", comments[index])
            except IndexError:
                pass

    @register(EMsg.ClientEmoticonList)
    def handle_emoticon_list(self, msg: MsgProto[friends.CMsgClientEmoticonList]) -> None:
        self.emoticons = [ClientEmoticon(self, emoticon) for emoticon in msg.body.emoticons]
        self.stickers = [ClientSticker(self, sticker) for sticker in msg.body.stickers]
        # self.effects = [ClientEffect(self, effect) for effect in msg.body.effects]  # TODO
        self.handled_emoticons.set()

    async def add_award(self, awardable: Awardable, award: Award) -> None:
        msg = await self.ws.send_um_and_wait(
            "LoyaltyRewards.AddReaction",
            target_type=awardable.__class__._AWARDABLE_TYPE,
            targetid=awardable.id,
            reactionid=award.id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_award_reactions(self, awardable: Awardable) -> list[ReactionProtocol]:
        # this method doesn't work and when steamcommunity tries to use it, It returns an empty response so, I'm
        # assuming it's just broken for now
        msg: MsgProto[loyalty_rewards.GetReactionsResponse] = await self.ws.send_um_and_wait(
            "LoyaltyRewards.GetReactions",
            target_type=awardable.__class__._AWARDABLE_TYPE,
            targetid=awardable.id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        # but also if this doesn't work there's no point including this method
        return [
            _Reaction(reactionid=id, count=count)  # type: ignore
            for id, count in collections.Counter(msg.body.reactionids).items()
        ]

    @register(EMsg.ClientUserNotifications)
    async def parse_notification(self, msg: MsgProto[client_server_2.CMsgClientUserNotifications]) -> None:
        if any(b.user_notification_type == 1 for b in msg.body.notifications):
            # 1 is a trade offer
            await self.poll_trades()

    @register(EMsg.ClientItemAnnouncements)
    async def parse_new_items(self, msg: MsgProto[client_server_2.CMsgClientItemAnnouncements]) -> None:
        if msg.body.count_new_items:
            await self.poll_trades()

    async def fetch_user_review(self, user_id64: int, app_ids: Iterable[int]) -> list[reviews.RecommendationDetails]:
        msg: MsgProto[reviews.GetIndividualRecommendationsResponse] = await self.ws.send_um_and_wait(
            "UserReviews.GetIndividualRecommendations",
            requests=[{"steamid": user_id64, "appid": app_id} for app_id in app_ids],
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.recommendations

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
            "UserReviews.Update",
            recommendationid=review_id,
            review_text=content,
            is_public=public,
            language=language,
            is_in_early_access=is_in_early_access,
            received_compensation=received_compensation,
            comments_disabled=not commentable,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_friend_thoughts(self, app_id: int) -> reviews.GetFriendsRecommendedAppResponse:
        msg: MsgProto[reviews.GetFriendsRecommendedAppResponse] = await self.ws.send_um_and_wait(
            "UserReviews.GetFriendsRecommendedApp",
            appid=app_id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    @register(EMsg.ClientAccountInfo)
    def parse_account_info(self, msg: MsgProto[login.CMsgClientAccountInfo]) -> None:
        if msg.body.persona_name != self.user.name:
            before = copy(self.user)
            self.user.name = msg.body.persona_name or self.user.name
            self.dispatch("user_update", before, self.user)

    async def fetch_friends_who_own(self, game_id: int) -> list[ID64]:
        msg: Msg[struct_messages.ClientGetFriendsWhoPlayGameResponse] = await self.ws.send_proto_and_wait(
            Msg(EMsg.ClientGetFriendsWhoPlayGame, extended=True, app_id=game_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.friends

    async def rate_clan_announcement(self, clan_id: int, announcement_id: int, upvoted: bool) -> None:
        msg = await self.ws.send_um_and_wait(
            "Community.RateClanAnnouncement",
            announcementid=announcement_id,
            clan_accountid=clan_id,
            vote_up=upvoted,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def respond_to_clan_invite(self, clan_id64: int, accept: bool) -> None:
        msg = await self.ws.send_um_and_wait("Clan.RespondToClanInvite", steamid=clan_id64, accept=accept)
        if msg.result != Result.OK:
            raise WSException(msg)

    @register(EMsg.ClientClanState)
    async def update_clan(self, msg: MsgProto[client_server.CMsgClientClanState]) -> None:
        await self.handled_chat_groups.wait()
        steam_id = SteamID(msg.body.steamid_clan)
        clan = self.get_clan(steam_id.id) or await self.fetch_clan(steam_id.id64, maybe_chunk=False)
        if clan is None:
            return

        for event in msg.body.events:
            if event.just_posted:
                event = await clan.fetch_event(event.gid)
                self.dispatch("event_create", event)
        for announcement in msg.body.announcements:
            if announcement.just_posted:
                announcement = await clan.fetch_announcement(announcement.gid)
                self.dispatch("announcement_create", announcement)

        user_counts = msg.body.user_counts
        name_info = msg.body.name_info

        if user_counts or name_info:
            before = copy(clan)
        if user_counts:
            clan.member_count = user_counts.members
            clan.in_game_count = user_counts.in_game
            clan.online_count = user_counts.online
            clan.active_member_count = user_counts.chatting
        if name_info:
            clan.name = name_info.clan_name
            clan.avatar_url = utils._get_avatar_url(name_info.sha_avatar)

        if user_counts or name_info:
            self.dispatch("clan_update", before, clan)

    @register(EMsg.ClientLicenseList)
    async def _handle_licenses(self, msg: MsgProto[client_server.CMsgClientLicenseList]) -> None:
        users = {
            user.id: user
            for user in await self._maybe_users(utils.make_id64(license.owner_id) for license in msg.body.licenses)
        }
        for license in msg.body.licenses:
            self.licenses[license.package_id] = License(self, license, users[license.owner_id])

        self.handled_licenses.set()

    async def fetch_cs_list(self, limit: int = 20) -> list[content_server.ServerInfo]:
        msg: MsgProto[content_server.GetServersForSteamPipeResponse] = await self.ws.send_um_and_wait(
            "ContentServerDirectory.GetServersForSteamPipe",
            cell_id=self.ws.cm_list.cell_id,
            max_servers=limit,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.servers

    async def fetch_manifest(
        self,
        game_id: int,
        id: int,
        depot_id: int,
        name: str | None = None,
        branch: str = "public",
        password_hash: str = "",
    ) -> Manifest:
        async with self.cs_lock:
            if not self.cs_servers:
                self.cs_servers = sorted(
                    (
                        ContentServer(
                            self,
                            URL_.build(
                                scheme=f"http{'s' if server.https_support != 'none' else ''}", host=server.vhost
                            ),
                            server.weighted_load,
                        )
                        for server in await self.fetch_cs_list(limit=20)
                        if server.type in ("CDN", "SteamCache")
                    ),
                    key=attrgetter("weighted_load"),
                )

        for server in tuple(self.cs_servers):
            try:
                return await server.fetch_manifest(game_id, id, depot_id, name, branch, password_hash)
            except HTTPException as exc:
                if 500 <= exc.status <= 599:
                    del self.cs_servers[0]
                else:
                    raise

        return await self.fetch_manifest(game_id, id, depot_id, name, branch, password_hash)

    async def fetch_manifests(
        self, game_id: int, branch_name: str, password: str | None, limit: int | None, password_hash: str = ""
    ) -> list[Coro[Manifest]]:
        (product_info,), _ = await self.fetch_product_info((game_id,))

        branch = product_info.get_branch(branch_name)
        if branch is None:
            raise ValueError(f"No branch named {branch_name!r} for app {game_id}")

        try:
            branch.password = self._manifest_passwords[game_id].get(branch_name)
        except KeyError:
            pass
        if branch.password_required and branch.password is None:
            if not password:
                raise ValueError(f"Branch {branch!r} requires a password")

            password_msg: MsgProto[
                client_server_2.CMsgClientCheckAppBetaPasswordResponse
            ] = await self.ws.send_proto_and_wait(
                MsgProto(EMsg.ClientCheckAppBetaPassword, app_id=game_id, betapassword=password)
            )
            if password_msg.result != Result.OK:
                raise WSException(password_msg)

            branch_password = utils.get(password_msg.body.betapasswords, betaname=branch.name)

            if branch_password is None:
                raise ValueError(f"Supplied password is not for the branch {branch!r}")
            branch.password = branch_password.betapassword
            try:
                self._manifest_passwords[game_id][branch.name] = branch.password
            except KeyError:
                self._manifest_passwords[game_id] = {branch.name: branch.password}

        return [
            self.fetch_manifest(
                game_id,
                depot.manifest.id,
                depot.id,
                depot.name,
                password_hash,
            )
            for depot in branch.depots[:limit]
        ]

    async def fetch_manifest_request_code(
        self,
        manifest_id: int,
        depot_id: int,
        app_id: int,
        branch: str = "",
        password_hash: str = "",
    ) -> int:
        msg: MsgProto[content_server.GetManifestRequestCodeResponse] = await self.ws.send_um_and_wait(
            "ContentServerDirectory.GetManifestRequestCode",
            app_id=app_id,
            depot_id=depot_id,
            manifest_id=manifest_id,
            app_branch=branch,
            branch_password_hash=password_hash,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        code = msg.body.manifest_request_code
        if not code:
            raise ValueError
        return code

    async def fetch_product_info(
        self, game_ids: Iterable[int] = (), package_ids: Iterable[int] = ()
    ) -> tuple[list[GameInfo], list[PackageInfo]]:
        games_to_fetch: list[dict[str, int]] = []
        packages_to_fetch: list[dict[str, int]] = []
        app_access_tokens_to_collect: list[int] = []
        package_access_tokens_to_collect: list[int] = []

        for game_id in game_ids:
            try:
                games_to_fetch.append({"appid": game_id, "access_token": self.licenses[game_id].access_token})
            except KeyError:
                app_access_tokens_to_collect.append(game_id)

        for package_id in package_ids:
            try:
                packages_to_fetch.append(
                    {"packageid": package_id, "access_token": self.licenses[package_id].access_token}
                )
            except KeyError:
                package_access_tokens_to_collect.append(package_id)

        if app_access_tokens_to_collect or package_access_tokens_to_collect:
            fetched_tokens = await self.fetch_manifest_access_tokens(
                app_access_tokens_to_collect, package_access_tokens_to_collect
            )
            games_to_fetch.extend(token.to_dict(do_nothing_case) for token in fetched_tokens.app_access_tokens)
            packages_to_fetch.extend(token.to_dict(do_nothing_case) for token in fetched_tokens.package_access_tokens)

        to_send = MsgProto[app_info.CMsgClientPicsProductInfoRequest](
            EMsg.ClientPICSProductInfoRequest,
            apps=games_to_fetch,
            packages=packages_to_fetch,
            supports_package_tokens=True,
        )
        to_send.header.body.job_id_source = job_id = self.ws.next_job_id

        await self.ws.send_proto(to_send)

        response_pending = True
        games: list[GameInfo] = []
        packages: list[PackageInfo] = []

        check: Callable[[MsgProto[app_info.CMsgClientPicsProductInfoResponse]], bool] = (
            lambda msg: msg.header.body.job_id_target == job_id
        )
        while response_pending:
            msg = await self.ws.wait_for(EMsg.ClientPICSProductInfoResponse, check)

            games.extend(
                GameInfo(
                    self,
                    VDF_LOADS(  # type: ignore  # can be removed if AnyOf ever happens
                        app.buffer[:-1].decode("UTF-8", "replace")
                    )["appinfo"],
                    app,
                )
                for app in msg.body.apps
            )

            packages.extend(
                PackageInfo(
                    self,
                    VDF_BINARY_LOADS(package.buffer[4:])[  # type: ignore  # can be removed if AnyOf ever happens
                        str(package.packageid)
                    ],
                    package,
                )
                for package in msg.body.packages
            )

            response_pending = msg.body.response_pending

        return games, packages

    async def fetch_depot_key(self, game_id: int, depot_id: int) -> bytes:
        msg: MsgProto[client_server_2.CMsgClientGetDepotDecryptionKeyResponse] = await self.ws.send_proto_and_wait(
            MsgProto(EMsg.ClientGetDepotDecryptionKey, app_id=game_id, depot_id=depot_id)
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.depot_encryption_key

    async def fetch_manifest_access_tokens(
        self,
        game_ids: list[int] | None = None,
        package_ids: list[int] | None = None,
    ) -> app_info.CMsgClientPicsAccessTokenResponse:

        game_ids = [] if game_ids is None else game_ids
        package_ids = [] if package_ids is None else package_ids

        msg: MsgProto[app_info.CMsgClientPicsAccessTokenResponse] = await self.ws.send_proto_and_wait(
            MsgProto(EMsg.ClientPICSAccessTokenRequest, appids=game_ids, packageids=package_ids),
        )
        if msg.result not in (
            Result.OK,
            Result.Invalid,
        ):  # invalid is for the case where access tokens are not required
            raise WSException(msg)
        return msg.body

    async def fetch_changes_since(
        self, change_number: int, app: bool, package: bool
    ) -> app_info.CMsgClientPicsChangesSinceResponse:
        msg: MsgProto[app_info.CMsgClientPicsChangesSinceResponse] = await self.ws.send_proto_and_wait(
            MsgProto(
                EMsg.ClientPICSChangesSinceRequest,
                since_change_number=change_number,
                send_app_info_changes=app,
                send_package_info_changes=package,
            )
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    async def fetch_published_files(
        self,
        published_file_ids: Iterable[int],
        revision: PublishedFileRevision,
        language: Language | None,
    ) -> list[PublishedFile | None]:
        msg: MsgProto[published_file.GetDetailsResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.GetDetails",
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
            desired_revision=revision,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        protos = msg.body.publishedfiledetails
        authors = await self._maybe_users(proto.creator for proto in protos)
        return [
            PublishedFile(self, proto, author) if proto.result == Result.OK else None
            for proto, author in zip(protos, authors)
        ]

    async def fetch_user_published_files(
        self,
        user_id64: int,
        app_id: int,
        page: int,
        file_type: PublishedFileType,
        revision: PublishedFileRevision,
        language: Language | None,
    ) -> published_file.GetUserFilesResponse:
        msg: MsgProto[published_file.GetUserFilesResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.GetUserFiles",
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
            desired_revision=revision,
            return_apps=True,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    async def fetch_game_published_files(
        self,
        game_id: int,
        after: datetime,
        before: datetime,
        file_type: PublishedFileQueryFileType,
        revision: PublishedFileRevision,
        language: Language | None,
        limit: int | None,
        cursor: str = "*",
    ) -> published_file.QueryFilesResponse:
        msg: MsgProto[published_file.QueryFilesResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.QueryFiles",
            numperpage=min(limit or 100, 100),
            appid=game_id,
            filetype=file_type,
            cursor=cursor,
            language=(language or self.language).value,
            date_range_created={"timestamp_start": after.timestamp(), "timestamp_end": before.timestamp()},
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
            desired_revision=revision,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    async def fetch_published_file_parents(
        self,
        published_file_id: int,
        revision: PublishedFileRevision,
        language: Language | None,
        cursor: str = "*",
    ) -> published_file.QueryFilesResponse:
        msg: MsgProto[published_file.QueryFilesResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.QueryFiles",
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
            desired_revision=revision,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    async def fetch_published_file_history(
        self, published_file_id: int, language: Language | None
    ) -> list[published_file.GetChangeHistoryResponseChangeLog]:
        msg: MsgProto[published_file.GetChangeHistoryResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.GetChangeHistory",
            publishedfileid=published_file_id,
            language=(language or self.language).value,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.changes

    async def fetch_published_file_history_entry(
        self, published_file_id: int, dt: datetime, language: Language | None
    ) -> published_file.GetChangeHistoryEntryResponse:
        msg: MsgProto[published_file.GetChangeHistoryEntryResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.GetChangeHistoryEntry",
            publishedfileid=published_file_id,
            timestamp=dt.timestamp(),
            language=(language or self.language).value,
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body

    async def subscribe_to_published_file(self, published_file_id: int) -> None:
        msg = await self.ws.send_um_and_wait(
            "PublishedFile.Subscribe", publishedfileid=published_file_id, notifyclient=True
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def unsubscribe_from_published_file(self, published_file_id: int) -> None:
        msg = await self.ws.send_um_and_wait(
            "PublishedFile.Unsubscribe", publishedfileid=published_file_id, notifyclient=True
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def is_subscribed_to_published_file(self, published_file_id: int) -> bool:
        msg: MsgProto[published_file.CanSubscribeResponse] = await self.ws.send_um_and_wait(
            "PublishedFile.CanSubscribe", publishedfileid=published_file_id
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.can_subscribe

    async def add_published_file_child(self, published_file_id: int, child_published_file_id: int) -> None:
        msg = await self.ws.send_um_and_wait(
            "PublishedFile.AddChild", publishedfileid=published_file_id, child_publishedfileid=child_published_file_id
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def remove_published_file_child(self, published_file_id: int, child_published_file_id: int) -> None:
        msg = await self.ws.send_um_and_wait(
            "PublishedFile.RemoveChild",
            publishedfileid=published_file_id,
            child_publishedfileid=child_published_file_id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def upvote_published_file(self, published_file_id: int, vote_up: bool) -> None:
        msg = await self.ws.send_um_and_wait(
            "PublishedFile.Vote",
            publishedfileid=published_file_id,
            vote_up=vote_up,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def edit_published_file(
        self,
        published_file_id: int,
        game_id: int,
        name: str,
        content: str,
        visibility: int,
        tags: Sequence[str],
        filename: str,
        preview_filename: str,
    ):
        msg = await self.ws.send_um_and_wait(
            "PublishedFile.Update",
            appid=game_id,
            publishedfileid=published_file_id,
            title=name,
            file_description=content,
            visibility=visibility,
            tags=tags,
            filename=filename,
            preview_filename=preview_filename,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    async def request_free_license(self, *app_ids: int) -> tuple[list[int], list[License]]:
        old_licenses = self.licenses.copy()
        self.handled_licenses.clear()
        msg: MsgProto[client_server_2.CMsgClientRequestFreeLicenseResponse] = await self.ws.send_proto_and_wait(
            MsgProto(EMsg.ClientRequestFreeLicense, appids=list(app_ids)),
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        if any(app_id not in msg.body.granted_appids for app_id in app_ids):
            raise WSNotFound(msg)
        if not msg.body.granted_packageids:
            raise ValueError("No licenses granted")
        await self.handled_licenses.wait()
        return msg.body.granted_appids, [l for l in self.licenses.values() if l.id not in old_licenses]
