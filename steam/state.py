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
import gc
import logging
import weakref
from collections import ChainMap, deque
from datetime import datetime
from time import time
from typing import TYPE_CHECKING, Any, Optional, Union

from bs4 import BeautifulSoup

from . import utils
from .abc import SteamID, UserDict
from .channel import ClanChannel, DMChannel, GroupChannel
from .clan import Clan
from .enums import ChatEntryType, FriendRelationship, PersonaState, Result, TradeOfferState, Type, UIMode
from .errors import *
from .game import GameToDict
from .group import Group
from .guard import *
from .invite import ClanInvite, UserInvite
from .message import *
from .message import ClanMessage
from .models import URL, EventParser, Registerable, register
from .protobufs import (
    EMsg,
    MsgProto,
    do_nothing_case,
    steammessages_chat as chat,
    steammessages_econ as econ,
    steammessages_friendmessages as friend_messages,
    steammessages_gameservers as game_servers,
    steammessages_player as player,
)
from .trade import DescriptionDict, TradeOffer, TradeOfferDict
from .user import User

if TYPE_CHECKING:
    from .abc import Message
    from .client import Client
    from .gateway import SteamWebSocket
    from .http import HTTPClient
    from .protobufs import (
        steammessages_clientserver as client_server,
        steammessages_clientserver_2 as client_server_2,
        steammessages_clientserver_friends as client_server_friends,
        steammessages_clientserver_login as client_server_login,
    )

log = logging.getLogger(__name__)


class ConnectionState(Registerable):
    parsers: dict[EMsg, EventParser]

    def __init__(self, client: Client, **kwargs: Any):
        self.client = client
        self.dispatch = client.dispatch
        self.http: HTTPClient = client.http

        self.handled_friends = asyncio.Event()
        self.max_messages: int = kwargs.pop("max_messages", 1000)

        game = kwargs.get("game")
        games = kwargs.get("games")
        games = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games.append(game.to_dict())
        self._games: list[GameToDict] = games
        self._state: PersonaState = kwargs.get("state", PersonaState.Online)
        self._ui_mode: Optional[UIMode] = kwargs.get("ui_mode", UIMode.Desktop)
        flag: int = kwargs.get("flag")
        flags: list[int] = kwargs.get("flag", [0])
        if flag is not None:
            flags.append(flag)
        flag_value = 0
        for flag in flags:
            flag_value |= flag
        self._flags: int = flag_value
        self._force_kick: bool = kwargs.get("force_kick", False)

        self.clear()

    def clear(self) -> None:
        self._users: weakref.WeakValueDictionary[int, User] = weakref.WeakValueDictionary()
        self._trades: dict[int, TradeOffer] = {}
        self._groups: dict[int, Group] = {}
        self._clans: dict[int, Clan] = {}
        self._confirmations: dict[int, Confirmation] = {}
        self._confirmations_to_ignore: list[int] = []
        self._messages: deque[Message] = self.max_messages and deque(maxlen=self.max_messages)
        self.invites: dict[int, Union[UserInvite, ClanInvite]] = {}

        self._trades_task: Optional[asyncio.Task[None]] = None
        self._trades_to_watch: list[int] = []
        self._trades_received_cache: list[dict] = []
        self._trades_sent_cache: list[dict] = []
        self._descriptions_cache: list[dict] = []

        self.handled_friends.clear()
        self.handled_groups = False

        gc.collect()

    async def __ainit__(self) -> None:
        if self.http.api_key is not None:
            self._device_id = generate_device_id(self.client.user)

            await self.poll_trades()

    @property
    def ws(self) -> SteamWebSocket:
        return self.client.ws

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

    def get_user(self, id64: int) -> Optional[User]:
        return self._users.get(id64)

    async def fetch_user(self, user_id64: int) -> Optional[User]:
        data = await self.http.get_user(user_id64)
        return User(state=self, data=data) if data else None
        # return (await self.fetch_users([user_id64]))[0]

    async def fetch_users(self, user_id64s: list[int]) -> list[Optional[User]]:
        resp = await self.http.get_users(user_id64s)
        """
        msg: MsgProto[CMsgClientRequestFriendData] = MsgProto(
            EMsg.ClientRequestFriendData,
            persona_state_requested=863,  # 1 | 2 | 4 | 8 | 16 | 64 | 256 | 512  corresponds to EClientPersonaStateFlag
            friends=user_id64s,
        )
        await self.ws.send_as_proto(msg)
        """

        return [User(state=self, data=data) for data in resp]

    def _store_user(self, data: UserDict) -> User:
        try:
            user = self._users[int(data["steamid"])]
        except KeyError:
            user = User(state=self, data=data)
            self._users[user.id64] = user
        return user

    def get_confirmation(self, id: int) -> Optional[Confirmation]:
        return self._confirmations.get(id)

    async def fetch_confirmation(self, id: int) -> Optional[Confirmation]:
        await self._fetch_confirmations()
        return self.get_confirmation(id)

    def get_group(self, id: int) -> Optional[Group]:
        return self._groups.get(id)

    def get_clan(self, id: int) -> Optional[Clan]:
        return self._clans.get(id)

    async def fetch_clan(self, id64: int) -> Optional[Clan]:
        msg: MsgProto[chat.CClanChatRoomsGetClanChatRoomInfoResponse] = await self.ws.send_um_and_wait(
            "ClanChatRooms.GetClanChatRoomInfo", steamid=id64
        )
        if msg.result == Result.Busy:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        return await Clan._from_proto(self, msg.body)

    def get_trade(self, id: int) -> Optional[TradeOffer]:
        return self._trades.get(id)

    async def fetch_trade(self, id: int) -> Optional[TradeOffer]:
        resp = await self.http.get_trade(id)
        if resp.get("response"):
            trade = [resp["response"]["offer"]]
            descriptions = resp["response"].get("descriptions", [])
            trades = await self._process_trades(trade, descriptions)
            return trades[0]
        return None

    async def _store_trade(self, data: TradeOfferDict) -> TradeOffer:
        try:
            trade = self._trades[int(data["tradeofferid"])]
        except KeyError:
            log.info(f'Received trade #{data["tradeofferid"]}')
            trade = await TradeOffer._from_api(state=self, data=data)
            trade.partner = await self.client.fetch_user(trade.partner) or SteamID(trade.partner)
            self._trades[trade.id] = trade
            if trade.state not in (
                TradeOfferState.Active,
                TradeOfferState.ConfirmationNeed,
            ):
                return trade
            self.dispatch("trade_send" if trade.is_our_offer() else "trade_receive", trade)
            self._trades_to_watch.append(trade.id)
        else:
            before_state = trade.state
            trade._update(data)
            if trade.state != before_state:
                log.info(f"Trade #{trade.id} has updated its trade state to {trade.state}")
                event_name = trade.state.event_name
                if event_name:
                    self.dispatch(f"trade_{event_name}", trade)
                    self._trades_to_watch.remove(trade.id)
        return trade

    async def _process_trades(
        self, trades: list[TradeOfferDict], descriptions: list[DescriptionDict]
    ) -> list[TradeOffer]:
        ret = []
        for trade in trades:
            for item in descriptions:
                for asset in trade.get("items_to_receive", []):
                    if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                        asset.update(item)
                for asset in trade.get("items_to_give", []):
                    if item["classid"] == asset["classid"] and item["instanceid"] == asset["instanceid"]:
                        asset.update(item)
            ret.append(await self._store_trade(trade))
        return ret

    async def poll_trades(self) -> None:
        async def poll_trades_inner() -> None:
            try:
                # TODO this can probably be optimized using sets
                resp = await self.http.get_trade_offers()
                trades = resp["response"]
                descriptions = trades.get("descriptions", [])
                trades_received = trades.get("trade_offers_received", [])
                trades_sent = trades.get("trade_offers_sent", [])

                new_received_trades = [trade for trade in trades_received if trade not in self._trades_received_cache]
                new_sent_trades = [trade for trade in trades_sent if trade not in self._trades_sent_cache]
                new_descriptions = [item for item in descriptions if item not in self._descriptions_cache]
                await self._process_trades(new_received_trades, new_descriptions)
                await self._process_trades(new_sent_trades, new_descriptions)
                self._trades_received_cache = trades_received
                self._trades_sent_cache = trades_sent
                self._descriptions_cache = descriptions
            except Exception as exc:
                await asyncio.sleep(30)
                log.info("Error while polling trades", exc_info=exc)

        await poll_trades_inner()
        while self._trades_to_watch:  # watch trades for changes
            await asyncio.sleep(5)
            await poll_trades_inner()

    # confirmations

    def _create_confirmation_params(self, tag: str) -> dict:
        timestamp = int(time())
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
        if "Oh nooooooes!" in resp:
            raise AuthenticatorError

        soup = BeautifulSoup(resp, "html.parser")
        if soup.select("#mobileconf_empty"):
            return {}
        for confirmation in soup.select("#mobileconf_list .mobileconf_list_entry"):
            id = confirmation["id"]
            data_conf_id = confirmation["data-confid"]
            key = confirmation["data-key"]
            trade_id = int(confirmation.get("data-creator", 0))
            confirmation_id = id.split("conf")[1]
            if trade_id in self._confirmations_to_ignore:
                continue
            self._confirmations[trade_id] = Confirmation(
                self, confirmation_id, data_conf_id, key, trade_id, f"details{data_conf_id}"
            )
        for trade_id in self._confirmations_to_ignore:
            if trade_id in self._confirmations:
                del self._confirmations[trade_id]
        return self._confirmations

    def _generate_confirmation(self, tag: str, timestamp: int) -> str:
        return generate_confirmation_code(self.client.identity_secret, tag, timestamp)

    async def get_and_confirm_confirmation(self, trade_id: int) -> bool:
        if self.client.identity_secret:
            confirmation = self.get_confirmation(trade_id) or await self.fetch_confirmation(trade_id)
            if confirmation is not None:
                await confirmation.confirm()
                return True

        return False

    # ws stuff

    @property
    def _combined(self) -> ChainMap[int, Union[Group, Clan]]:
        return ChainMap(
            {clan.chat_id: clan for clan in self._clans.values()},
            self._groups,
        )

    async def send_user_message(self, user_id64: int, content: str) -> UserMessage:
        msg: MsgProto[friend_messages.CFriendMessagesSendMessageResponse] = await self.ws.send_um_and_wait(
            "FriendMessages.SendMessage",
            steamid=user_id64,
            message=content,
            chat_entry_type=ChatEntryType.Text,
            contains_bbcode=utils.contains_bbcode(content),
        )

        if msg.result == Result.LimitExceeded:
            raise WSForbidden(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        proto = friend_messages.CFriendMessagesIncomingMessageNotification(
            chat_entry_type=ChatEntryType.Text,
            message=content,
            rtime32_server_timestamp=int(time()),
            message_no_bbcode=msg.body.message_without_bb_code,
        )
        channel = DMChannel(state=self, participant=self.get_user(user_id64))
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

    async def send_group_message(self, destination: tuple[int, int], content: str) -> Union[ClanMessage, GroupMessage]:
        chat_id, group_id = destination
        msg: MsgProto[chat.CChatRoomSendChatMessageResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.SendChatMessage", chat_id=chat_id, chat_group_id=group_id, message=content
        )

        if msg.result == Result.LimitExceeded:
            raise WSForbidden(msg)
        if msg.result == Result.InvalidParameter:
            raise WSNotFound(msg)
        if msg.result != Result.OK:
            raise WSException(msg)

        proto = chat.CChatRoomIncomingChatMessageNotification(
            chat_id=chat_id,
            chat_group_id=group_id,
            steamid_sender=0,
            message=content,
            message_no_bbcode=msg.body.message_without_bb_code,
            timestamp=int(time()),
        )
        destination = self._combined.get(group_id)
        if isinstance(destination, Clan):
            channel = ClanChannel(state=self, channel=proto, clan=destination)
            message = ClanMessage(proto=proto, channel=channel, author=self.client.user)
        else:
            channel = GroupChannel(state=self, channel=proto, group=destination)
            message = GroupMessage(proto=proto, channel=channel, author=self.client.user)
        self._messages.append(message)
        self.dispatch("message", message)

        return message

    async def join_chat(self, chat_id: int, invite_code: Optional[str] = None) -> None:
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
    ) -> MsgProto[friend_messages.CFriendMessagesGetRecentMessagesResponse]:
        msg: MsgProto[friend_messages.CFriendMessagesGetRecentMessagesResponse] = await self.ws.send_um_and_wait(
            "FriendMessages.GetRecentMessages",
            steamid1=self.client.user.id64,
            steamid2=user_id64,
            rtime32_start_time=start,
            time_last=last,
            count=100,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_group_history(
        self, group_id: int, chat_id: int, start: int, last: int
    ) -> MsgProto[chat.CChatRoomGetMessageHistoryResponse]:
        msg: MsgProto[chat.CChatRoomGetMessageHistoryResponse] = await self.ws.send_um_and_wait(
            "ChatRoom.GetMessageHistory",
            chat_group_id=group_id,
            chat_id=chat_id,
            last_time=last,
            start_time=start,
            max_count=100,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg

    async def fetch_servers(self, query: str, limit: int) -> list[game_servers.CGameServersGetServerListResponseServer]:
        msg: MsgProto[game_servers.CGameServersGetServerListResponse] = await self.ws.send_um_and_wait(
            "GameServers.GetServerList",
            filter=query,
            limit=limit,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.servers

    async def fetch_server_ip_from_steam_id(
        self, *ids: int
    ) -> list[game_servers.CGameServersIPsWithSteamIDsResponseServer]:
        msg: MsgProto[game_servers.CGameServersIPsWithSteamIDsResponse] = await self.ws.send_um_and_wait(
            "GameServers.GetServerIPsBySteamID",
            server_steamids=list(ids),
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.servers

    # TODO use this in V.1
    async def fetch_user_games(self, user_id64: int) -> list[player.CPlayerGetOwnedGamesResponseGame]:
        msg: MsgProto[player.CPlayerGetOwnedGamesResponse] = await self.ws.send_um_and_wait(
            "Player.GetOwnedGames",
            steamid=user_id64,
            include_appinfo=True,
            include_played_free_games=True,
        )

        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body.games

    async def fetch_user_profile_info(
        self, user_id64: int
    ) -> client_server_friends.CMsgClientFriendProfileInfoResponse:
        await self.ws.send_as_proto(MsgProto(EMsg.ClientFriendProfileInfo, steamid_friend=user_id64))
        msg: MsgProto[client_server_friends.CMsgClientFriendProfileInfoResponse] = await self.ws.wait_for(
            EMsg.ClientFriendProfileInfoResponse, check=lambda m: m.body.steamid_friend == user_id64
        )
        if msg.result != Result.OK:
            raise WSException(msg)

        return msg.body

    async def get_trade_url(self, generate_new: bool) -> str:
        msg: MsgProto[econ.CEconGetTradeOfferAccessTokenResponse] = await self.ws.send_um_and_wait(
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
        try:
            await {
                "FriendMessagesClient.IncomingMessage": self.handle_user_message,
                "ChatRoomClient.NotifyIncomingChatMessage": self.handle_group_message,
                "ChatRoomClient.NotifyChatRoomHeaderStateChange": self.handle_group_update,
                "ChatRoomClient.NotifyChatGroupUserStateChanged": self.handle_group_user_action,
            }[msg.header.body.job_name_target](msg)
        except KeyError:
            pass

    async def handle_user_message(
        self, msg: MsgProto[friend_messages.CFriendMessagesIncomingMessageNotification]
    ) -> None:
        user_id64 = msg.body.steamid_friend
        partner = self.get_user(user_id64) or await self.fetch_user(user_id64) or SteamID(user_id64)
        author = self.client.user if msg.body.local_echo else partner  # local_echo is always us

        if msg.body.chat_entry_type == ChatEntryType.Text:
            channel = DMChannel(state=self, participant=partner)
            message = UserMessage(proto=msg.body, channel=channel)
            message.author = author
            self._messages.append(message)
            self.dispatch("message", message)

        if msg.body.chat_entry_type == ChatEntryType.Typing:
            when = datetime.utcfromtimestamp(msg.body.rtime32_server_timestamp)
            self.dispatch("typing", author, when)

    async def handle_group_message(self, msg: MsgProto[chat.CChatRoomIncomingChatMessageNotification]) -> None:
        destination = self._combined.get(msg.body.chat_group_id)
        if destination is None:
            return
        if isinstance(destination, Clan):
            channel = ClanChannel(state=self, channel=msg.body, clan=destination)
            user_id64 = msg.body.steamid_sender
            author = self.get_user(user_id64) or await self.fetch_user(user_id64)
            message = ClanMessage(proto=msg.body, channel=channel, author=author)
        else:
            channel = GroupChannel(state=self, channel=msg.body, group=destination)
            user_id64 = msg.body.steamid_sender
            author = self.get_user(user_id64) or await self.fetch_user(user_id64)
            message = GroupMessage(proto=msg.body, channel=channel, author=author)
        self._messages.append(message)
        self.dispatch("message", message)

    async def handle_group_update(self, msg: MsgProto[chat.CChatRoomChatRoomHeaderStateNotification]) -> None:
        destination = self._combined.get(msg.body.header_state.chat_group_id)
        if destination is None:
            return

        if isinstance(destination, Clan):
            await destination._from_proto(self, msg.body.header_state)
        else:
            destination._from_proto(msg.body.header_state)
            await destination.__ainit__()

    async def handle_group_user_action(
        self, msg: MsgProto[chat.ChatRoomClientNotifyChatGroupUserStateChangedNotification]
    ) -> None:
        if msg.body.user_action == "Joined":  # join group
            if msg.body.group_summary.clanid:
                clan = await Clan._from_proto(self, msg.body.group_summary)
                self._clans[clan.id] = clan
                self.dispatch("clan_join", clan)  # TODO test/doc
            else:
                group = Group(state=self, proto=msg.body.group_summary)
                self._groups[group.id] = group
                self.dispatch("group_join", group)

        elif msg.body.user_action == "Parted":  # leave group
            left = self._combined.pop(msg.body.chat_group_id, None)
            if left is None:
                return

            if isinstance(left, Clan):
                self.dispatch("clan_leave", left)  # TODO test/doc
            else:
                self.dispatch("group_leave", left)

    @register(EMsg.ServiceMethodResponse)
    async def parse_service_method_response(self, msg: MsgProto) -> None:
        if msg.header.body.job_name_target == "ChatRoom.GetMyChatRoomGroups":
            msg: MsgProto[chat.CChatRoomGetMyChatRoomGroupsResponse]
            for group in msg.body.chat_room_groups:
                if group.group_summary.clanid:  # received a clan
                    clan = await Clan._from_proto(self, group)
                    self._clans[clan.id] = clan
                else:  # else it's a group
                    group = Group(state=self, proto=group.group_summary)
                    await group.__ainit__()
                    self._groups[group.id] = group

            if not self.handled_groups:
                await self.handled_friends.wait()  # ensure friend cache is ready
                self.client._handle_ready()

    @register(EMsg.ClientCMList)
    async def parse_cm_list_update(self, msg: MsgProto[client_server.CMsgClientCmList]) -> None:
        log.debug("Updating CM list")
        cms = msg.body.cm_websocket_addresses
        cm_list = self.ws.cm_list
        cm_list.extend(cms)
        await cm_list.ping()  # ping all the cms, we have time.

    @register(EMsg.ClientPersonaState)
    async def parse_persona_state_update(self, msg: MsgProto[client_server_friends.CMsgClientPersonaState]) -> None:
        for friend in msg.body.friends:
            data: UserDict = friend.to_dict(do_nothing_case)
            if not data:
                continue
            user_id64 = friend.friendid
            after = self.get_user(user_id64)
            if after is None:  # they're private
                continue

            before = after.copy()

            try:
                data = self.patch_user_from_ws(data, friend)
            except (KeyError, TypeError):
                invitee = await self.fetch_user(user_id64) or SteamID(user_id64)
                invite = UserInvite(self, invitee, FriendRelationship.RequestRecipient)
                self.dispatch("user_invite", invite)

            after._update(data)
            old = [getattr(before, attr, None) for attr in User.__slots__]
            new = [getattr(after, attr, None) for attr in User.__slots__]
            if old != new:
                self.dispatch("user_update", before, after)

    def patch_user_from_ws(self, data: dict, friend: client_server_friends.CMsgClientPersonaStateFriend) -> dict:
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
        return data

    @register(EMsg.ClientFriendsList)
    async def process_friends(self, msg: MsgProto[client_server_friends.CMsgClientFriendsList]) -> None:
        elements = None

        if not self.handled_friends.is_set():
            self.client.user.friends = await self.fetch_users(
                [
                    friend.ulfriendid
                    for friend in msg.body.friends
                    if friend.efriendrelationship == FriendRelationship.Friend
                    and (friend.ulfriendid >> 52) & 0xF != Type.Clan
                ]
            )
            for friend in self.client.user.friends:
                try:
                    self._users[friend.id64] = friend
                except AttributeError:
                    pass
            self.handled_friends.set()

        for friend in msg.body.friends:
            if friend.efriendrelationship in (
                FriendRelationship.RequestInitiator,
                FriendRelationship.RequestRecipient,
            ):
                steam_id = SteamID(friend.ulfriendid)
                relationship = FriendRelationship(friend.efriendrelationship)
                if steam_id.type == Type.Individual:
                    invitee = await self.fetch_user(steam_id.id64) or steam_id
                    invite = UserInvite(state=self, invitee=invitee, relationship=relationship)
                    self.invites[invitee.id64] = invite
                    self.dispatch("user_invite", invite)
                if steam_id.type == Type.Clan:
                    if elements is None:
                        resp = await self.http.get(URL.COMMUNITY / "my/groups/pending", params={"ajax": "1"})
                        soup = BeautifulSoup(resp, "html.parser")
                        elements = soup.find_all("a", attrs={"class": "linkStandard"})
                    invitee_id = 0
                    for idx, element in enumerate(elements):
                        if str(steam_id.id64) in str(element):
                            invitee_id = elements[idx + 1]["data-miniprofile"]
                            break
                    invitee_steam_id = SteamID(invitee_id)
                    invitee = (
                        self.get_user(invitee_steam_id.id64)
                        or await self.fetch_user(invitee_steam_id.id64)
                        or invitee_steam_id
                    )
                    try:
                        clan = await asyncio.wait_for(self.fetch_clan(steam_id.id64), timeout=2)
                    except asyncio.TimeoutError:
                        clan = steam_id

                    invite = ClanInvite(state=self, invitee=invitee, clan=clan, relationship=relationship)
                    self.invites[clan.id64] = invite
                    self.dispatch("clan_invite", invite)

            if friend.efriendrelationship == FriendRelationship.Friend:
                steam_id = SteamID(friend.ulfriendid)
                try:
                    invite = self.invites.pop(steam_id.id64)
                except KeyError:
                    pass
                else:
                    if steam_id.type == Type.Individual:
                        self.dispatch("user_invite_accept", invite)
                    else:
                        self.dispatch("clan_invite_accept", invite)

    @register(EMsg.ClientCommentNotifications)
    async def handle_comments(self, _: MsgProto[client_server_2.CMsgClientCommentNotifications]) -> None:
        previous = None
        resp = await self.http.get(URL.COMMUNITY / "my/commentnotifications")
        soup = BeautifulSoup(resp, "html.parser")
        for attr in soup.find_all("div", attrs={"class": "commentnotification_click_overlay"}):
            steam_id = await SteamID.from_url(attr.contents[1]["href"], self.http._session)
            if steam_id is None:
                continue
            if steam_id != previous:
                obj = await (self.fetch_clan if steam_id.type == Type.Clan else self.fetch_user)(steam_id.id64)
                if obj is None:
                    continue
                index = 0
            else:
                obj = previous
                index += 1

            comments = await obj.comments(limit=index + 1)
            try:
                self.dispatch("comment", comments[index])
            except IndexError:
                pass

        await self.http.clear_notifications()

    @register(EMsg.ClientUserNotifications)
    async def parse_notification(self, msg: MsgProto[client_server_2.CMsgClientUserNotifications]) -> None:
        if msg.body.notifications and any(b.user_notification_type == 1 for b in msg.body.notifications):
            # 1 is a trade offer
            await self.poll_trades()

    @register(EMsg.ClientItemAnnouncements)
    async def parse_new_items(self, msg: MsgProto[client_server_2.CMsgClientItemAnnouncements]) -> None:
        if msg.body.count_new_items:
            await self.poll_trades()

    @register(EMsg.ClientAccountInfo)
    def parse_account_info(self, msg: MsgProto[client_server_login.CMsgClientAccountInfo]) -> None:
        if not self.client.user:
            return
        if msg.body.persona_name != self.client.user.name:
            before = self.client.user.copy()
            self.client.user.name = msg.body.persona_name or self.client.user.name
            self.dispatch("user_update", before, self.client.user)
