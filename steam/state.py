"""
The MIT License (MIT)

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
"""

from __future__ import annotations

import asyncio
import logging
import re
import weakref
from collections import ChainMap, deque
from collections.abc import Callable, Iterable, Sequence
from copy import copy, deepcopy
from datetime import datetime, timedelta
from operator import attrgetter
from time import time
from typing import TYPE_CHECKING, Any, overload

from bs4 import BeautifulSoup
from typing_extensions import Self
from yarl import URL as URL_

from . import utils
from ._const import HTML_PARSER, URL, VDF_BINARY_LOADS, VDF_LOADS
from .abc import BaseUser, Commentable, SteamID
from .channel import DMChannel
from .clan import Clan
from .comment import Comment
from .enums import *
from .errors import *
from .group import Group
from .guard import *
from .invite import ClanInvite, UserInvite
from .iterators import AsyncIterator
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
    player,
    reviews,
    struct_messages,
)
from .trade import TradeOffer
from .user import User

if TYPE_CHECKING:
    from .abc import Message
    from .client import Client
    from .gateway import SteamWebSocket
    from .types.game import GameToDict
    from .types.trade import DescriptionDict, TradeOfferDict
    from .types.user import UserDict

log = logging.getLogger(__name__)


class TradeQueue:
    def __init__(self):
        self.queue: deque[TradeOffer] = deque()
        self._waiting_for: dict[int, asyncio.Future[TradeOffer]] = {}

    async def wait_for(self, id: int) -> TradeOffer:
        for trade in reversed(self.queue):  # check if it's already here
            if trade.id == id:
                self.queue.remove(trade)
                return trade

        self._waiting_for[id] = future = asyncio.get_running_loop().create_future()
        trade = await future
        self.queue.remove(trade)
        return trade

    def __len__(self) -> int:
        return len(self.queue)

    def __iadd__(self, other: list[TradeOffer]) -> Self:
        for trade in other:
            try:
                future = self._waiting_for[trade.id]
            except KeyError:
                pass
            else:
                future.set_result(trade)
                del self._waiting_for[trade.id]

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
        self.handled_groups = asyncio.Event()
        self.handled_group_members = asyncio.Event()
        self.handled_licenses = asyncio.Event()
        self.max_messages: int = kwargs.pop("max_messages", 1000)

        game = kwargs.get("game")
        games = kwargs.get("games")
        games = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games.append(game.to_dict())
        self._games: list[GameToDict] = games
        self._state: PersonaState = kwargs.get("state", PersonaState.Online)
        self._ui_mode: UIMode = kwargs.get("ui_mode", UIMode.Desktop)
        self._flags: PersonaStateFlag = kwargs.get("flags", PersonaStateFlag.NONE)
        self._force_kick: bool = kwargs.get("force_kick", False)

        self.clear()

    def clear(self) -> None:
        self._users: weakref.WeakValueDictionary[int, User] = weakref.WeakValueDictionary()
        self._trades: dict[int, TradeOffer] = {}
        self._groups: dict[int, Group] = {}
        self._clans: dict[int, Clan] = {}
        self._confirmations: dict[int, Confirmation] = {}
        self._confirmations_to_ignore: list[int] = []
        self._messages: deque[Message] = deque(maxlen=self.max_messages or 0)
        self.invites: dict[int, UserInvite | ClanInvite] = {}
        self.emoticons: list[ClientEmoticon] = []
        self.polling_trades = False
        self.trade_queue = TradeQueue()
        self.licenses: dict[int, License] = {}
        self._manifest_passwords: dict[int, dict[str, str]] = {}
        self.cs_servers: list[ContentServer] = []

        self._trades_to_watch: set[int] = set()
        self._trades_received_cache: Sequence[dict[str, Any]] = ()
        self._trades_sent_cache: Sequence[dict[str, Any]] = ()

        self.handled_friends.clear()
        self.handled_emoticons.clear()
        self.handled_groups.clear()
        self.handled_licenses.clear()

    async def __ainit__(self) -> None:
        if self.http.api_key is not None:
            self._device_id = generate_device_id(self.client.user)

            await self.poll_trades()

    @property
    def ws(self) -> SteamWebSocket:
        return self.client.ws

    @property
    def steam_time(self) -> datetime:
        if self.ws is None:  # can't be more precise
            return datetime.utcnow()
        return datetime.utcnow() + self.ws.server_offset

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

    def get_user(self, id64: int) -> User | None:
        return self._users.get(id64)

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

    async def _maybe_user(self, id64: int) -> User | SteamID:
        return self.get_user(id64) or await self.fetch_user(id64) or SteamID(id64)

    async def _maybe_users(self, id64s: Iterable[int]) -> list[User | SteamID]:
        ret: list[User | SteamID] = []
        to_fetch: dict[int, list[int]] = {}
        for idx, id64 in enumerate(id64s):
            user = self.get_user(id64)
            if user is not None:
                ret.append(user)
            else:
                idxs = to_fetch.get(id64)
                if idxs is None:
                    idxs = to_fetch[id64] = []

                idxs.append(idx)
                ret.append(id64)  # type: ignore

        if to_fetch:
            for (user_id64, idxs), user in zip(to_fetch.items(), await self.fetch_users(to_fetch)):
                if user is None:
                    user = SteamID(user_id64)
                for idx in idxs:
                    ret[idx] = user

        return ret

    def _store_user(self, data: _UserDict) -> User:
        try:
            user = self._users[int(data["steamid"])]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id64] = user
        else:
            user._update(data)
        return user

    def get_confirmation(self, id: int) -> Confirmation | None:
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id: int) -> Confirmation | None:
        await self._fetch_confirmations()
        return self.get_confirmation(id)

    def get_group(self, id: int) -> Group | None:
        return self._groups.get(id)

    def get_clan(self, id: int) -> Clan | None:
        return self._clans.get(id)

    async def fetch_clan(self, id64: int) -> Clan | None:
        msg: MsgProto[chat.GetClanChatRoomInfoResponse] = await self.ws.send_um_and_wait(
            "ClanChatRooms.GetClanChatRoomInfo", steamid=id64
        )
        if msg.result == Result.Busy:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        return await Clan._from_proto(self, msg.body)

    def get_trade(self, id: int) -> TradeOffer | None:
        return self._trades.get(id)

    async def fetch_trade(self, id: int) -> TradeOffer | None:
        resp = await self.http.get_trade(id)
        if resp.get("response"):
            trade = [resp["response"]["offer"]]
            descriptions = resp["response"].get("descriptions", ())
            trades = await self._process_trades(trade, descriptions)
            return trades[0]

    async def _store_trade(self, data: TradeOfferDict) -> TradeOffer:
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
        self, trades: list[TradeOfferDict], descriptions: list[DescriptionDict]
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
        if self.polling_trades:
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

    def _create_confirmation_params(self, tag: str) -> dict[str, Any]:
        timestamp = int(self.steam_time.timestamp())
        return {
            "p": self._device_id,
            "a": self.client.user.id64,
            "k": self._generate_confirmation(tag, timestamp),
            "t": timestamp,
            "m": "android",
            "tag": tag,
        }

    async def _fetch_confirmations(self) -> dict[int, Confirmation]:
        params = self._create_confirmation_params("conf")
        headers = {"X-Requested-With": "com.valvesoftware.android.steam.community"}
        resp = await self.http.get(URL.COMMUNITY / "mobileconf/conf", params=params, headers=headers)

        if "incorrect Steam Guard codes." in resp:
            raise InvalidCredentials("identity_secret is incorrect")

        soup = BeautifulSoup(resp, "html.parser")
        if soup.select("#mobileconf_empty"):
            return self._confirmations
        for confirmation in soup.select("#mobileconf_list .mobileconf_list_entry"):
            data_conf_id = confirmation["data-confid"]
            key = confirmation["data-key"]
            trade_id = int(confirmation.get("data-creator", 0))
            confirmation_id = confirmation["id"].split("conf")[1]
            if trade_id in self._confirmations_to_ignore:
                continue
            self._confirmations[trade_id] = Confirmation(self, confirmation_id, data_conf_id, key, trade_id)

        return self._confirmations

    def _generate_confirmation(self, tag: str, timestamp: int) -> str:
        return generate_confirmation_code(self.client.identity_secret, tag, timestamp)  # type: ignore

    async def fetch_and_confirm_confirmation(self, trade_id: int) -> bool:
        if self.client.identity_secret:
            confirmation = self.get_confirmation(trade_id) or await self.fetch_confirmation(trade_id)
            if confirmation is not None:
                await confirmation.confirm()
                return True

        return False

    # ws stuff

    @property
    def _combined(self) -> ChainMap[int, Group | Clan]:
        return ChainMap({clan.chat_id: clan for clan in self._clans.values()}, self._groups)  # type: ignore

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
            rtime32_server_timestamp=int(time()),
            message_no_bbcode=msg.body.message_without_bb_code,
        )
        channel = DMChannel(state=self, participant=self.get_user(user_id64))  # type: ignore
        message = UserMessage(proto=proto, channel=channel)
        message.author = self.client.user
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def send_user_typing(self, user_id64: int) -> None:
        await self.ws.send_um(
            "FriendMessages.SendMessage",
            steamid=user_id64,
            chat_entry_type=ChatEntryType.Typing,
        )
        self.dispatch("typing", self.client.user, datetime.utcnow())

    async def send_group_message(self, chat_id: int, group_id: int, content: str) -> ClanMessage | GroupMessage:
        msg: MsgProto[chat.SendChatMessageResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.SendChatMessage", chat_id=chat_id, chat_group_id=group_id, message=content
        )

        if msg.result == Result.LimitExceeded:
            raise WSForbidden(msg)
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        proto = chat.IncomingChatMessageNotification(
            chat_id=chat_id,
            chat_group_id=group_id,
            steamid_sender=0,
            message=content,
            message_no_bbcode=msg.body.message_without_bb_code,
            timestamp=int(time()),
        )
        group = self._combined[group_id]
        channel = group._channels[chat_id]
        channel._update(proto)

        message = (ClanMessage if isinstance(group, Clan) else GroupMessage)(
            proto=proto,
            channel=channel,  # type: ignore  # type checkers can't figure out this is ok
            author=self.client.user,
        )
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def join_chat(self, chat_id: int, invite_code: str | None = None) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.JoinChatRoomGroup", chat_group_id=chat_id, invite_code=invite_code or ""
        )

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def leave_chat(self, chat_id: int) -> None:
        msg = await self.ws.send_um_and_wait("ChatRoom.LeaveChatRoomGroup", chat_group_id=chat_id)

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def invite_user_to_group(self, user_id64: int, group_id: int) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.InviteFriendToChatRoomGroup", chat_group_id=group_id, steamid=user_id64
        )

        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def edit_role(self, group_id: int, role_id: int, *, name: str) -> None:
        msg = await self.ws.send_um_and_wait("ChatRoom.RenameRole", chat_group_id=group_id, role_id=role_id, name=name)
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.result != Result.OK:
            raise WSException(msg)

    async def fetch_user_history(
        self, user_id64: int, start: int, last: int
    ) -> friend_messages.GetRecentMessagesResponse:
        msg: MsgProto[friend_messages.GetRecentMessagesResponse] = await self.ws.send_um_and_wait(
            "FriendMessages.GetRecentMessages",
            steamid1=self.client.user.id64,
            steamid2=user_id64,
            rtime32_start_time=start,
            time_last=last,
            count=100,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_group_history(
        self, group_id: int, chat_id: int, start: int, last: int
    ) -> chat.GetMessageHistoryResponse:
        msg: MsgProto[chat.GetMessageHistoryResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.GetMessageHistory",
            chat_group_id=group_id,
            chat_id=chat_id,
            last_time=last,
            start_time=start,
            max_count=100,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

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

    # TODO use this in V.1
    async def fetch_user_games(self, user_id64: int) -> list[player.GetOwnedGamesResponseGame]:
        msg: MsgProto[player.GetOwnedGamesResponse] = await self.ws.send_um_and_wait(
            "Player.GetOwnedGames",
            steamid=user_id64,
            include_appinfo=True,
            include_played_free_games=True,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.games

    async def fetch_user_profile_info(self, user_id64: int) -> friends.CMsgClientFriendProfileInfoResponse:
        msg: MsgProto[friends.CMsgClientFriendProfileInfoResponse] = await self.ws.send_proto_and_wait(
            MsgProto(EMsg.ClientFriendProfileInfo, steamid_friend=user_id64)
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_user_equipped_profile_items(self, user_id64: int) -> player.GetProfileItemsEquippedResponse:
        msg: MsgProto[player.GetProfileItemsEquippedResponse] = await self.ws.send_um_and_wait(
            "Player.GetProfileItemsEquipped",
            steamid=user_id64,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_profile_items(self) -> player.GetProfileItemsOwnedResponse:
        msg: MsgProto[player.GetProfileItemsOwnedResponse] = await self.ws.send_um_and_wait(
            "Player.GetProfileItemsOwned",
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def fetch_user_favourite_badge(self, user_id64) -> player.GetFavoriteBadgeResponse:
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
            f"https://steamcommunity.com/tradeoffer/new/?partner={self.client.user.id}"
            f"&token={msg.body.trade_offer_access_token}"
        )

    # parsers

    @register(EMsg.ServiceMethod)
    async def parse_service_method(self, msg: MsgProto[Any]) -> None:
        name = msg.header.body.job_name_target
        if name == "ChatRoomClient.NotifyIncomingChatMessage":
            await self.handle_group_message(msg)
        elif name == "ChatRoomClient.NotifyChatRoomHeaderStateChange":
            await self.handle_group_update(msg)
        elif name == "ChatRoomClient.NotifyChatGroupUserStateChanged":
            await self.handle_group_user_action(msg)
        elif name == "ChatRoomClient.NotifyChatRoomGroupRoomsChange":
            await self.handle_group_channel_update(msg)
        elif name == "FriendMessagesClient.IncomingMessage":
            await self.handle_user_message(msg)
        else:
            log.debug("Got an event %r that we don't handle %r", msg.header.body.job_name_target, msg.body)

    async def handle_user_message(self, msg: MsgProto[friend_messages.IncomingMessageNotification]) -> None:
        partner = await self._maybe_user(msg.body.steamid_friend)  # FIXME shouldn't ever be out of cache
        author = self.client.user if msg.body.local_echo else partner  # local_echo is always us

        if msg.body.chat_entry_type == ChatEntryType.Text:
            channel = DMChannel(state=self, participant=partner)  # type: ignore  # remove when above fixme removed
            message = UserMessage(proto=msg.body, channel=channel)
            message.author = author
            self._messages.append(message)
            self.dispatch("message", message)

        if msg.body.chat_entry_type == ChatEntryType.Typing:
            when = datetime.utcfromtimestamp(msg.body.rtime32_server_timestamp)
            self.dispatch("typing", author, when)

    async def handle_group_message(self, msg: MsgProto[chat.IncomingChatMessageNotification]) -> None:
        try:
            destination = self._combined[msg.body.chat_group_id]
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

    async def handle_group_update(self, msg: MsgProto[chat.ChatRoomHeaderStateNotification]) -> None:
        try:
            group = self._combined[msg.body.header_state.chat_group_id]
        except KeyError:
            return log.debug(f"Updating a group that isn't cached {msg.body.header_state.chat_group_id}")

        before = copy(group)
        before._channels = {c_id: copy(c) for c_id, c in before._channels.items()}
        before.roles = deepcopy(before.roles)
        if isinstance(before, Group):
            before.members = before.members.copy()
        group._update(msg.body.header_state)
        self.dispatch(f"{'group' if isinstance(destination, Group) else 'clan'}_update", before, group)

    async def handle_group_user_action(self, msg: MsgProto[chat.NotifyChatGroupUserStateChangedNotification]) -> None:
        if msg.body.user_action == "Joined":  # join group
            if msg.body.group_summary.clanid:
                clan = await Clan._from_proto(self, msg.body.group_summary)
                self._clans[clan.id] = clan
                self.dispatch("clan_join", clan)
            else:
                group = await Group._from_proto(self, msg.body.group_summary)
                self._groups[group.id] = group
                self.dispatch("group_join", group)

        elif msg.body.user_action == "Parted":  # leave group
            left = self._combined.pop(msg.body.chat_group_id, None)
            if left is None:
                return

            if isinstance(left, Clan):
                self.dispatch("clan_leave", left)
            else:
                self.dispatch("group_leave", left)

    async def handle_group_channel_update(self, msg: MsgProto[chat.ChatRoomGroupRoomsChangeNotification]):
        try:
            group = self._combined[msg.body.chat_group_id]
        except KeyError:
            return log.debug(f"Got an update for a clan we aren't in {msg.body.chat_group_id}")

        before = copy(group)
        before._channels = {c_id: copy(c) for c_id, c in before._channels.items()}
        before.roles = deepcopy(before.roles)
        if isinstance(before, Group):
            before.members = before.members.copy()
        group._update(msg.body)
        self.dispatch(f"{'clan' if isinstance(group, Clan) else 'group'}_update", before, group)

    @register(EMsg.ServiceMethodResponse)
    async def parse_service_method_response(self, msg: MsgProto[Any]) -> None:
        if msg.header.body.job_name_target == "ChatRoom.GetMyChatRoomGroups":
            msg: MsgProto[chat.GetMyChatRoomGroupsResponse]
            for group in msg.body.chat_room_groups:
                if group.group_summary.clanid:  # received a clan
                    clan = await Clan._from_proto(self, group)
                    self._clans[clan.id] = clan
                else:  # else it's a group
                    group = await Group._from_proto(self, group.group_summary)
                    self._groups[group.id] = group
            self.handled_groups.set()  # signal to process_group_members that we are ready
            await self.handled_group_members.wait()  # ensure the members are ready
            await self.handled_friends.wait()  # ensure friend cache is ready
            # await self.handled_emoticons.wait()  # ensure emoticon cache is ready
            await self.client._handle_ready()

    @register(EMsg.ClientPersonaState)
    async def parse_persona_state_update(self, msg: MsgProto[friends.CMsgClientPersonaState]) -> None:
        for friend in msg.body.friends:
            data = friend.to_dict(do_nothing_case)
            if not data:
                continue
            user_id64 = friend.friendid
            after = self.get_user(user_id64)
            if after is None:  # they're private
                continue

            before = copy(after)

            try:
                data = self.patch_user_from_ws(data, friend)
            except (KeyError, TypeError):
                invitee = await self._maybe_user(user_id64)
                invite = UserInvite(self, invitee, FriendRelationship.RequestRecipient)
                return self.dispatch("user_invite", invite)

            after._update(data)
            old = [getattr(before, attr, None) for attr in BaseUser.__slots__]
            new = [getattr(after, attr, None) for attr in BaseUser.__slots__]
            if old != new:
                self.dispatch("user_update", before, after)

    def patch_user_from_ws(self, data: dict[str, Any], friend: friends.CMsgClientPersonaStateFriend) -> _UserDict:
        data["personaname"] = friend.player_name
        hash = (
            friend.avatar_hash.hex()
            if data["avatar_hash"] != "\x00" * 20
            else "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"
        )
        data[
            "avatarfull"
        ] = f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/{hash[:2]}/{hash}_full.jpg"

        if friend.last_logoff:
            data["lastlogoff"] = friend.last_logoff
        data["gameextrainfo"] = friend.game_name or None
        data["personastate"] = friend.persona_state
        data["personastateflags"] = friend.persona_state_flags
        return data  # type: ignore  # casting is for losers

    @register(EMsg.ClientFriendsList)
    async def process_friends(self, msg: MsgProto[friends.CMsgClientFriendsList]) -> None:
        elements = None
        client_user_friends: list[int] = []
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
                    self.dispatch(f"{'user'if steam_id.type == Type.Individual else 'clan'}_invite_accept", invite)
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
                        soup = BeautifulSoup(resp, "html.parser")
                        elements = soup.find_all("a", class_="linkStandard")
                    invitee_id64 = 0
                    for idx, element in enumerate(elements):
                        if str(steam_id.id64) in str(element):
                            invitee_id64 = utils.make_id64(elements[idx + 1]["data-miniprofile"])
                            break
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
                    friend = self.get_user(steam_id.id64)
                    try:
                        self.client.user.friends.remove(friend)
                    except ValueError:
                        pass
                    self.dispatch("user_remove", friend)
                else:
                    self.dispatch(f"{'user'if steam_id.type == Type.Individual else 'clan'}_invite_decline", invite)
        if is_load:
            self.client.user.friends = await self.fetch_users(client_user_friends)
            self.handled_friends.set()

    @register(EMsg.ClientFriendsGroupsList)
    async def process_group_members(self, msg: MsgProto[friends.CMsgClientFriendsGroupsList]):
        await self.handled_groups.wait()
        members = await self.fetch_users([m.ul_steam_id for m in msg.body.memberships])
        for membership in msg.body.memberships:
            for member in members:
                if member and member.id64 == membership.ul_steam_id:
                    try:
                        self._groups[membership.n_group_id].members.append(member)
                    except KeyError:
                        log.debug(f"Somehow got an unknown group {membership.n_group_id} and member {member.id64}")

        self.handled_group_members.set()

    async def fetch_group_roles(self, group_id: int) -> list[chat.Role]:
        msg: MsgProto[chat.GetRolesResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.GetRoles", chat_group_id=group_id
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
        self, owner: Commentable, limit: int | None, after: datetime, oldest_first: bool
    ) -> list[comments.GetCommentThreadResponse.Comment]:
        msg: MsgProto[comments.GetCommentThreadResponse] = await self.ws.send_um_and_wait(
            "Community.GetCommentThread",
            **owner._commentable_kwargs,
            count=2147483647 if limit is None else limit,
            oldest_first=oldest_first,
            time_oldest=int(after.timestamp()),
        )  # int(i32::MAX / 2) not entirely sure why this is the max and not i32 which is the max for the field
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.comments

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
            author=self.client.user,
            owner=owner,
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
            parent_id=comment_id,
        )
        if msg.result != Result.OK:
            raise WSException(msg)

    @register(EMsg.ClientCommentNotifications)
    async def handle_comments(self, msg: MsgProto[client_server_2.CMsgClientCommentNotifications]) -> None:
        resp = await self.http.get(URL.COMMUNITY / "my/commentnotifications")
        soup = BeautifulSoup(resp, "html.parser")

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
                    commentable = self.get_user(steam_id.id64) or await self.fetch_user(steam_id.id64)
                else:
                    clan = self.get_clan(steam_id.id64) or await self.fetch_clan(steam_id.id64)
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

            after = datetime.utcfromtimestamp(timestamp) - timedelta(minutes=1)

            comments = [comment async for comment in commentable.comments(limit=index + 1, after=after)]

            try:
                self.dispatch("comment", comments[index])
            except IndexError:
                pass

    @register(EMsg.ClientUserNotifications)
    async def parse_notification(self, msg: MsgProto[client_server_2.CMsgClientUserNotifications]) -> None:
        if any(b.user_notification_type == 1 for b in msg.body.notifications):
            # 1 is a trade offer
            await self.poll_trades()

    @register(EMsg.ClientItemAnnouncements)
    async def parse_new_items(self, msg: MsgProto[client_server_2.CMsgClientItemAnnouncements]) -> None:
        if msg.body.count_new_items:
            await self.poll_trades()

    async def fetch_user_review(self, user_id64: int, game_id: int) -> reviews.RecommendationDetails:
        # This not accepting multiple users and apps is a steam limitation not sure why.
        # The request is technically able to support it
        msg: MsgProto[reviews.GetIndividualRecommendationsResponse] = await self.ws.send_um_and_wait(
            "UserReviews.GetIndividualRecommendations",
            requests=[{"steamid": user_id64, "appid": game_id}],
        )
        if msg.result != Result.OK:
            raise WSException(msg)
        return msg.body.recommendations[0]

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

    @register(EMsg.ClientAccountInfo)
    def parse_account_info(self, msg: MsgProto[login.CMsgClientAccountInfo]) -> None:
        if self.client.user is None:
            return
        if msg.body.persona_name != self.client.user.name:
            before = copy(self.client.user)
            self.client.user.name = msg.body.persona_name or self.client.user.name
            self.dispatch("user_update", before, self.client.user)

    async def fetch_friends_who_own(self, game_id: int) -> list[int]:
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
        await self.handled_groups.wait()
        clan = self.get_clan(msg.body.steamid_clan) or await self.fetch_clan(msg.body.steamid_clan)
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
            hexed = name_info.sha_avatar.hex()
            hash = hexed if hexed != "\x00" * 20 else "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"
            clan.avatar_url = (
                f"https://steamcdn-a.akamaihd.net/steamcommunity/public/images/avatars/{hash[:2]}/{hash}_full.jpg"
            )

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

    @overload
    async def fetch_manifest(self, game_id: int, id: int, depot_id: int, name: None = ...) -> Manifest[None]:
        ...

    @overload
    async def fetch_manifest(self, game_id: int, id: int, depot_id: int, name: str = ...) -> Manifest[str]:
        ...

    async def fetch_manifest(
        self, game_id: int, id: int, depot_id: int, name: str | None = None
    ) -> Manifest[str | None]:
        if not self.cs_servers:
            self.cs_servers = sorted(
                (
                    ContentServer(
                        self,
                        URL_.build(scheme=f"http{'s' if server.https_support != 'none' else ''}", host=server.vhost),
                        server.weighted_load,
                    )
                    for server in await self.fetch_cs_list(limit=20)
                    if server.type in ("CDN", "SteamCache")
                ),
                key=attrgetter("weighted_load"),
            )

        for server in tuple(self.cs_servers):
            try:
                manifest = await server.fetch_manifest(game_id, id, depot_id)
            except HTTPException as exc:
                if exc.status == 404:
                    raise
                self.cs_servers.pop(0)
            else:
                manifest.name = name
                return manifest

        return await self.fetch_manifest(game_id, id, depot_id, name)

    async def fetch_manifests(
        self, game_id: int, branch_name: str, password: str | None, limit: int | None
    ) -> list[Manifest[str]]:
        (product_info,), _ = await self.fetch_product_info((game_id,))

        try:
            branch = product_info._branches[branch_name]
        except KeyError:
            raise ValueError(f"No branch named {branch_name!r} for app {game_id}") from None

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
            self._manifest_passwords[game_id][branch.name] = branch.password

        return await asyncio.gather(
            *(
                self.fetch_manifest(
                    game_id,
                    depot.manifest.id,
                    depot.id,
                    depot.name,
                )
                for depot in branch.depots[:limit]
            )
        )  # type: ignore  # typeshed lies

    async def fetch_product_info(
        self, game_ids: Iterable[int] = (), package_ids: Iterable[int] = ()
    ) -> tuple[list[GameInfo], list[PackageInfo]]:
        games_to_fetch: list[dict[str, int]] = []
        packages_to_fetch: list[dict[str, int]] = []
        to_collect: list[int] = []

        for game_id in game_ids:
            try:
                games_to_fetch.append({"appid": game_id, "access_token": self.licenses[game_id].access_token})
            except KeyError:
                to_collect.append(game_id)

        for package_id in package_ids:
            try:
                packages_to_fetch.append(
                    {"packageid": package_id, "access_token": self.licenses[package_id].access_token}
                )
            except KeyError:
                to_collect.append(package_id)

        if to_collect:
            fetched_tokens = await self.fetch_manifest_access_tokens(to_collect)
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
