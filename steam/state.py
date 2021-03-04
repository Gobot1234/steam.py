# -*- coding: utf-8 -*-

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
from typing import TYPE_CHECKING, Any, MutableMapping, Optional, Union

from betterproto import snake_case
from bs4 import BeautifulSoup

from . import utils
from .abc import SteamID, UserDict
from .channel import ClanChannel, DMChannel, GroupChannel
from .clan import Clan
from .enums import *
from .errors import *
from .game import GameToDict
from .group import Group
from .guard import *
from .invite import ClanInvite, UserInvite
from .message import *
from .message import ClanMessage
from .models import EventParser, Registerable, community_route, register
from .protobufs import EMsg, MsgProto
from .protobufs.steammessages_chat import (
    CChatRoomGetMessageHistoryResponse as GroupChannelHistory,
    CChatRoomIncomingChatMessageNotification as GroupMessageNotification,
    CClanChatRoomsGetClanChatRoomInfoResponse as FetchGroupResponse,
)
from .protobufs.steammessages_friendmessages import (
    CFriendMessagesGetRecentMessagesResponse as DMChannelHistory,
    CFriendMessagesIncomingMessageNotification as UserMessageNotification,
    CFriendMessagesSendMessageResponse as SendUserMessageResponse,
)
from .protobufs.steammessages_gameservers import (
    CGameServersGetServerListResponse as GetGameServers,
    CGameServersGetServerListResponseServer as GameServersMessage,
    CGameServersIPsWithSteamIDsResponse as GetServerIPs,
    CGameServersIPsWithSteamIDsResponseServer as GetServerIPsServer,
)
from .trade import DescriptionDict, TradeOffer, TradeOfferDict
from .user import User

if TYPE_CHECKING:
    from .abc import Message
    from .client import Client
    from .gateway import SteamWebSocket
    from .protobufs.steammessages_chat import (
        CChatRoomChatRoomHeaderStateNotification as GroupStateUpdate,
        CChatRoomGetMyChatRoomGroupsResponse as MyChatRooms,
        ChatRoomClientNotifyChatGroupUserStateChangedNotification as GroupAction,
    )
    from .protobufs.steammessages_clientserver import CMsgClientCMList
    from .protobufs.steammessages_clientserver_2 import (
        CMsgClientCommentNotifications as CommentNotifications,
        CMsgClientUserNotifications as GeneralNotifications,
    )
    from .protobufs.steammessages_clientserver_friends import (
        CMsgClientFriendsList,
        CMsgClientFriendsListFriend,
        CMsgClientPersonaState,
        CMsgClientPersonaStateFriend,
        CMsgClientRequestFriendData,
    )
    from .protobufs.steammessages_clientserver_login import CMsgClientAccountInfo

log = logging.getLogger(__name__)


class ConnectionState(Registerable):
    parsers: dict[EMsg, EventParser[EMsg]] = {}

    __slots__ = (
        "http",
        "request",
        "client",
        "dispatch",
        "handled_friends",
        "handled_groups",
        "invites",
        "max_messages",
        "_users",
        "_trades",
        "_groups",
        "_clans",
        "_confirmations",
        "_confirmations_to_ignore",
        "_trades_task",
        "_trades_to_watch",
        "_trades_received_cache",
        "_trades_sent_cache",
        "_descriptions_cache",
        "_id64",
        "_device_id",
        "_messages",
        "_games",
        "_state",
        "_ui_mode",
        "_flags",
        "_force_kick",
    )

    def __init__(self, client: Client, **kwargs: Any):
        self.client = client
        self.loop = client.loop
        self.dispatch = client.dispatch
        self.http = client.http
        self.request = self.http.request

        self.handled_friends = asyncio.Event()
        self.max_messages: int = kwargs.pop("max_messages", 1000)

        game = kwargs.get("game")
        games = kwargs.get("games")
        games = [game.to_dict() for game in games] if games is not None else []
        if game is not None:
            games.append(game.to_dict())
        self._games: list[GameToDict] = games
        self._state: EPersonaState = kwargs.get("state", EPersonaState.Online)
        self._ui_mode: Optional[EUIMode] = kwargs.get("ui_mode")
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
        self._users: MutableMapping[int, User] = weakref.WeakValueDictionary()
        self._trades: dict[int, TradeOffer] = {}
        self._groups: dict[int, Group] = {}
        self._clans: dict[int, Clan] = {}
        self._confirmations: dict[int, Confirmation] = {}
        self._confirmations_to_ignore: list[int] = []
        self._messages: deque[Message] = self.max_messages and deque(maxlen=self.max_messages)
        self.invites: dict[int, Union[UserInvite, ClanInvite]] = {}

        self._trades_task: Optional[asyncio.Task] = None
        self._trades_to_watch: list[int] = []
        self._trades_received_cache: list[dict] = []
        self._trades_sent_cache: list[dict] = []
        self._descriptions_cache: list[dict] = []

        self.handled_friends.clear()
        self.handled_groups = False
        self._obj = None
        self._previous_iteration = 0

        gc.collect()

    async def __ainit__(self) -> None:
        if self.http.api_key is not None:
            self._id64 = self.client.user.id64
            self._device_id = generate_device_id(str(self._id64))

            await self._poll_trades()

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
        msg: MsgProto[FetchGroupResponse] = await self.ws.send_um_and_wait(
            "ClanChatRooms.GetClanChatRoomInfo#1", steamid=id64
        )
        if msg.eresult == EResult.Busy:
            raise WSNotFound(msg)
        if msg.eresult != EResult.OK:
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
                ETradeOfferState.Active,
                ETradeOfferState.ConfirmationNeed,
            ):
                return trade
            self.dispatch("trade_send" if trade.is_our_offer() else "trade_receive", trade)
            self._trades_to_watch.append(trade.id)
        else:
            before_state = trade.state
            trade._update(data)
            if trade.state != before_state:
                log.info(f"Trade #{trade.id} has updated its trade state to {trade.state}")
                try:
                    event_name = {
                        ETradeOfferState.Accepted: "accept",
                        ETradeOfferState.Countered: "counter",
                        ETradeOfferState.Expired: "expire",
                        ETradeOfferState.Canceled: "cancel",
                        ETradeOfferState.Declined: "decline",
                        ETradeOfferState.CanceledBySecondaryFactor: "cancel",
                    }[trade.state]
                except KeyError:
                    pass
                else:
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

    async def _poll_trades(self) -> None:
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

    # confirmations

    def _create_confirmation_params(self, tag: str) -> dict:
        timestamp = int(time())
        return {
            "p": self._device_id,
            "a": self._id64,
            "k": self._generate_confirmation(tag, timestamp),
            "t": timestamp,
            "m": "android",
            "tag": tag,
        }

    async def _fetch_confirmations(self) -> dict[int, Confirmation]:
        params = self._create_confirmation_params("conf")
        headers = {"X-Requested-With": "com.valvesoftware.android.steam.community"}
        resp = await self.request("GET", community_route("mobileconf/conf"), params=params, headers=headers)

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
        msg: MsgProto[SendUserMessageResponse] = await self.ws.send_um_and_wait(
            "FriendMessages.SendMessage#1",
            steamid=user_id64,
            message=content,
            chat_entry_type=EChatEntryType.Text,
            contains_bbcode=utils.contains_bbcode(content),
        )

        if msg.eresult == EResult.LimitExceeded:
            raise WSForbidden(msg)
        if msg.eresult != EResult.OK:
            raise WSException(msg)

        proto = UserMessageNotification(
            chat_entry_type=EChatEntryType.Text,
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
            "FriendMessages.SendMessage#1",
            steamid=user_id64,
            chat_entry_type=EChatEntryType.Typing,
        )
        self.dispatch("typing", self.client.user, datetime.utcnow())

    async def send_group_message(self, destination: tuple[int, int], content: str) -> Union[ClanMessage, GroupMessage]:
        chat_id, group_id = destination
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.SendChatMessage#1", chat_id=chat_id, chat_group_id=group_id, message=content
        )

        if msg.eresult == EResult.LimitExceeded:
            raise WSForbidden(msg)
        if msg.eresult == EResult.InvalidParameter:
            raise WSNotFound(msg)
        if msg.eresult != EResult.OK:
            raise WSException(msg)

        proto = GroupMessageNotification(
            chat_id=chat_id, chat_group_id=group_id, steamid_sender=0, message=content, timestamp=int(time())
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
            "ChatRoom.JoinChatRoomGroup#1", chat_group_id=chat_id, invite_code=invite_code or ""
        )

        if msg.eresult == EResult.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.eresult != EResult.OK:
            raise WSException(msg)

    async def leave_chat(self, chat_id: int) -> None:
        msg = await self.ws.send_um_and_wait("ChatRoom.LeaveChatRoomGroup#1", chat_group_id=chat_id)

        if msg.eresult == EResult.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.eresult != EResult.OK:
            raise WSException(msg)

    async def invite_user_to_group(self, user_id64: int, group_id: int) -> None:
        msg = await self.ws.send_um_and_wait("InviteFriendToChatRoomGroup#1", chat_group_id=group_id, steamid=user_id64)

        if msg.eresult == EResult.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.eresult != EResult.OK:
            raise WSException(msg)

    async def edit_role(self, group_id: int, role_id: int, *, name: str) -> None:
        msg = await self.ws.send_um_and_wait(
            "ChatRoom.RenameRole#1", chat_group_id=group_id, role_id=role_id, name=name
        )
        if msg.eresult == EResult.InvalidParameter:
            raise WSNotFound(msg)
        elif msg.eresult != EResult.OK:
            raise WSException(msg)

    async def get_user_history(self, user_id64: int, start: int, last: int) -> Optional[MsgProto[DMChannelHistory]]:
        msg: MsgProto[DMChannelHistory] = await self.ws.send_um_and_wait(
            "FriendMessages.GetRecentMessages#1",
            steamid1=self.client.user.id64,
            steamid2=user_id64,
            rtime32_start_time=start,
            time_last=last,
            count=100,
        )

        if msg.eresult != EResult.OK:
            raise WSException(msg)

        return msg

    async def get_group_history(
        self, group_id: int, chat_id: int, start: int, last: int
    ) -> Optional[MsgProto[GroupChannelHistory]]:
        msg: MsgProto[GroupChannelHistory] = await self.ws.send_um_and_wait(
            "ChatRoom.GetMessageHistory#1",
            chat_group_id=group_id,
            chat_id=chat_id,
            last_time=last,
            start_time=start,
            max_count=100,
        )

        if msg.eresult != EResult.OK:
            raise WSException(msg)

        return msg

    async def fetch_servers(self, query: str, limit: int) -> list[GameServersMessage]:
        msg: MsgProto[GetGameServers] = await self.ws.send_um_and_wait(
            "GameServers.GetServerList#1",
            filter=query,
            limit=limit,
        )

        if msg.eresult != EResult.OK:
            raise WSException(msg)

        return msg.body.servers

    async def fetch_server_ip_from_steam_id(self, *ids: int) -> list[GetServerIPsServer]:
        msg: MsgProto[GetServerIPs] = await self.ws.send_um_and_wait(
            "GameServers.GetServerIPsBySteamID#1",
            server_steamids=list(ids),
        )

        if msg.eresult != EResult.OK:
            raise WSException(msg)

        return msg.body.servers

    # parsers

    @register(EMsg.ServiceMethod)
    async def parse_service_method(self, msg: MsgProto) -> None:
        if msg.header.body.job_name_target == "FriendMessagesClient.IncomingMessage#1":
            msg: MsgProto[UserMessageNotification]
            user_id64 = msg.body.steamid_friend
            partner = self.get_user(user_id64) or await self.fetch_user(user_id64) or SteamID(user_id64)
            author = self.client.user if msg.body.local_echo else partner  # local_echo is always us

            if msg.body.chat_entry_type == EChatEntryType.Text:
                channel = DMChannel(state=self, participant=partner)
                message = UserMessage(proto=msg.body, channel=channel)
                message.author = author
                self._messages.append(message)
                self.dispatch("message", message)

            if msg.body.chat_entry_type == EChatEntryType.Typing:
                when = datetime.utcfromtimestamp(msg.body.rtime32_server_timestamp)
                self.dispatch("typing", author, when)

        elif msg.header.body.job_name_target == "ChatRoomClient.NotifyIncomingChatMessage#1":
            msg: MsgProto[GroupMessageNotification]
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

        elif msg.header.body.job_name_target == "ChatRoomClient.NotifyChatRoomHeaderStateChange#1":  # group update
            msg: MsgProto[GroupStateUpdate]
            destination = self._combined.get(msg.body.header_state.chat_group_id)
            if destination is None:
                return

            if isinstance(destination, Clan):
                await destination._from_proto(self, msg.body.header_state)
            else:
                destination._from_proto(msg.body.header_state)

        elif msg.header.body.job_name_target == "ChatRoomClient.NotifyChatGroupUserStateChanged#1":
            msg: MsgProto[GroupAction]
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
        if msg.header.body.job_name_target == "ChatRoom.GetMyChatRoomGroups#1":
            msg: MsgProto[MyChatRooms]
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
    def parse_cm_list_update(self, msg: MsgProto[CMsgClientCMList]) -> None:
        log.debug("Updating CM list")
        cms = msg.body.cm_websocket_addresses
        self.ws.cm_list.merge_list(cms)
        self.loop.create_task(self.ws.cm_list.ping_cms(to_ping=len(cms)))
        # ping all the cms, we have time.

    @register(EMsg.ClientPersonaState)
    async def parse_persona_state_update(self, msg: MsgProto[CMsgClientPersonaState]) -> None:
        for friend in msg.body.friends:
            data: UserDict = friend.to_dict(snake_case)
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
                steam_id = SteamID(user_id64)
                invitee = await self.fetch_user(steam_id.id64) or steam_id
                invite = UserInvite(self, invitee, EFriendRelationship.RequestRecipient)
                self.dispatch("user_invite", invite)

            after._update(data)
            old = [getattr(before, attr, None) for attr in User.__slots__]
            new = [getattr(after, attr, None) for attr in User.__slots__]
            if old != new:
                self.dispatch("user_update", before, after)

    def patch_user_from_ws(self, data: dict, friend: CMsgClientPersonaStateFriend) -> dict:
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
    async def process_friends(self, msg: MsgProto[CMsgClientFriendsList]) -> None:
        elements = None

        if not self.handled_friends.is_set():
            self.client.user.friends = await self.fetch_users(
                [
                    friend.ulfriendid
                    for friend in msg.body.friends
                    if friend.efriendrelationship == EFriendRelationship.Friend
                    and (friend.ulfriendid >> 52) & 0xf != EType.Clan
                ]
            )
            for friend in self.client.user.friends:
                try:
                    self._users[friend.id64] = friend
                except AttributeError:
                    pass
            self.handled_friends.set()

        async def gather_invites(friend: CMsgClientFriendsListFriend) -> None:
            if friend.efriendrelationship in (
                EFriendRelationship.RequestInitiator,
                EFriendRelationship.RequestRecipient,
            ):
                steam_id = SteamID(friend.ulfriendid)
                relationship = EFriendRelationship(friend.efriendrelationship)
                if steam_id.type == EType.Individual:
                    invitee = await self.fetch_user(steam_id.id64) or steam_id
                    invite = UserInvite(state=self, invitee=invitee, relationship=relationship)
                    self.invites[invitee.id64] = invite
                    self.dispatch("user_invite", invite)
                if steam_id.type == EType.Clan:
                    nonlocal elements
                    if elements is None:
                        resp = await self.request("GET", community_route("my/groups/pending"), params={"ajax": "1"})
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

            if friend.efriendrelationship == EFriendRelationship.Friend:
                steam_id = SteamID(friend.ulfriendid)
                try:
                    invite = self.invites.pop(steam_id.id64)
                except KeyError:
                    pass
                else:
                    if steam_id.type == EType.Individual:
                        self.dispatch("user_invite_accept", invite)
                    else:
                        self.dispatch("clan_invite_accept", invite)

        await asyncio.gather(*(gather_invites(f) for f in msg.body.friends))

    @register(EMsg.ClientCommentNotifications)
    async def handle_comments(self, _: MsgProto[CommentNotifications]) -> None:
        previous = None
        resp = await self.request("GET", community_route("my/commentnotifications"))
        soup = BeautifulSoup(resp, "html.parser")
        for attr in soup.find_all("div", attrs={"class": "commentnotification_click_overlay"}):
            steam_id = await SteamID.from_url(attr.contents[1]["href"], self.http._session)
            if steam_id is None:
                continue
            if steam_id != previous:
                obj = await (self.fetch_clan if steam_id.type == EType.Clan else self.fetch_user)(steam_id.id64)
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
    async def parse_notification(self, msg: MsgProto[GeneralNotifications]) -> None:
        for notification in msg.body.notifications:
            if notification.user_notification_type == 1:  # received a trade offer

                async def poll_trades() -> None:
                    while self._trades_to_watch:
                        await asyncio.sleep(1)
                        try:
                            await self._poll_trades()
                        except Exception as exc:
                            await asyncio.sleep(10)
                            log.info("Error while polling trades", exc_info=exc)

                if self._trades_task is None or self._trades_task.done():
                    await self._poll_trades()
                    self._trades_task = self.loop.create_task(poll_trades())  # watch trades for changes

    @register(EMsg.ClientAccountInfo)
    def parse_account_info(self, msg: MsgProto[CMsgClientAccountInfo]) -> None:
        if msg.body.persona_name != self.client.user.name:
            before = self.client.user.copy()
            self.client.user.name = msg.body.persona_name or self.client.user.name
            self.dispatch("user_update", before, self.client.user)
