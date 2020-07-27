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

import asyncio
from datetime import datetime
from typing import Any, Awaitable, Callable, Coroutine, Dict, List, Literal, Optional, Tuple, Union, final, overload

from .clan import Clan
from .comment import Comment
from .enums import EPersonaState, EUIMode
from .game import Game
from .gateway import SteamWebSocket
from .group import Group
from .http import HTTPClient
from .invite import ClanInvite, UserInvite
from .iterators import TradesIterator
from .message import Message
from .protobufs import Msg, MsgProto
from .state import ConnectionState
from .trade import TradeOffer
from .user import ClientUser, User

__all__ = ("Client",)

Msgs: Union[Msg, MsgProto] = Union[Msg, MsgProto]
EventType: Callable[..., Coroutine[None, Any, None]]  # basic event, shouldn't yield or return anything

class Client:
    loop: asyncio.AbstractEventLoop
    http: HTTPClient
    _connection: ConnectionState
    ws: SteamWebSocket
    username: Optional[str]
    api_key: Optional[str]
    password: Optional[str]
    shared_secret: Optional[str]
    identity_secret: Optional[str]
    shared_secret: Optional[str]
    token: Optional[str]
    @property
    def user(self) -> "ClientUser": ...
    @property
    def users(self) -> List["User"]: ...
    @property
    def trades(self) -> List["TradeOffer"]: ...
    @property
    def groups(self) -> List["Group"]: ...
    @property
    def clans(self) -> List["Clan"]: ...
    @property
    def latency(self) -> float: ...
    @final
    async def code(self) -> str: ...
    @final
    def is_ready(self) -> bool: ...
    @final
    def is_closed(self) -> bool: ...
    def clear(self) -> None: ...
    def run(self, *args, **kwargs) -> None: ...
    async def login(self, username: str, password: str, shared_secret: Optional[str] = ...) -> None: ...
    async def close(self) -> None: ...
    async def start(self, *args, **kwargs) -> None: ...
    async def connect(self) -> None: ...
    @final
    def get_user(self, *args, **kwargs) -> Optional["User"]: ...
    @final
    async def fetch_user(self, *args, **kwargs) -> Optional["User"]: ...
    @final
    async def fetch_users(self, *ids: List[int]) -> List[Optional["User"]]: ...
    @final
    async def fetch_user_named(self, name: str) -> Optional["User"]: ...
    @final
    def get_trade(self, id: int) -> Optional["TradeOffer"]: ...
    @final
    async def fetch_trade(self, id: int) -> Optional["TradeOffer"]: ...
    @final
    def get_group(self, id: int) -> Optional["Group"]: ...
    @final
    def get_clan(self, *args, **kwargs) -> Optional["Clan"]: ...
    @final
    async def fetch_clan(self, *args, **kwargs) -> Optional["Clan"]: ...
    @final
    async def fetch_clan_named(self, name: str) -> Optional["Clan"]: ...
    @final
    def trade_history(
        self,
        limit: Optional[int] = ...,
        before: Optional[datetime] = ...,
        after: Optional[datetime] = ...,
        active_only: bool = ...,
    ) -> TradesIterator: ...
    @final
    async def change_presence(
        self,
        *,
        game: Optional["Game"] = ...,
        games: Optional[List["Game"]] = ...,
        state: Optional["EPersonaState"] = ...,
        ui_mode: Optional["EUIMode"] = ...,
        force_kick: bool = ...,
    ) -> None: ...
    @final
    async def wait_until_ready(self) -> None: ...
    async def on_connect(self): ...
    async def on_disconnect(self): ...
    async def on_ready(self): ...
    async def on_login(self): ...
    async def on_error(self, event: str, error: Exception, *args, **kwargs): ...
    async def on_message(self, message: Message): ...
    async def on_comment(self, comment: Comment): ...
    async def on_user_update(self, before: User, after: User): ...
    async def on_typing(self, user: User, when: datetime): ...
    async def on_trade_receive(self, trade: TradeOffer): ...
    async def on_trade_send(self, trade: TradeOffer): ...
    async def on_trade_accept(self, trade: TradeOffer): ...
    async def on_trade_decline(self, trade: TradeOffer): ...
    async def on_trade_cancel(self, trade: TradeOffer): ...
    async def on_trade_expire(self, trade: TradeOffer): ...
    async def on_trade_counter(self, trade: TradeOffer): ...
    async def on_user_invite(self, invite: UserInvite): ...
    async def on_clan_invite(self, invite: ClanInvite): ...
    async def on_socket_receive(self, msg: Union[Msg, MsgProto]): ...
    async def on_socket_raw_receive(self, message: bytes): ...
    async def on_socket_send(self, msg: Union[Msg, MsgProto]): ...
    async def on_socket_raw_send(self, message: bytes): ...
    def dispatch(self, __event: str, *args, **kwargs) -> None: ...
    @final
    def event(self, coro: EventType) -> EventType: ...
    @final
    @overload
    def wait_for(
        self, __event: str, *, check: Optional[Callable[..., bool]] = ..., timeout: Optional[float] = ...
    ) -> Awaitable[Any]: ...
    @overload
    def wait_for(
        self, __event: Literal["connect"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> Awaitable[None]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["disconnect"],
        *,
        check: Optional[Callable[[], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[None]: ...
    @overload  # don't know why you'd do this
    def wait_for(
        self, __event: Literal["ready"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> Awaitable[None]: ...
    @overload
    def wait_for(
        self, __event: Literal["login"], *, check: Optional[Callable[[], bool]] = ..., timeout: Optional[float] = ...
    ) -> Awaitable[None]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["error"],
        *,
        check: Optional[Callable[[str, Exception, Tuple[Any, ...], Dict[str, Any]], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Tuple[str, Exception, Tuple[Any, ...], Dict[str, Any]]]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["message"],
        *,
        check: Optional[Callable[[Message], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Message]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["comment"],
        *,
        check: Optional[Callable[[Comment], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Comment]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["user_update"],
        *,
        check: Optional[Callable[[User, User], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Tuple[User, User]]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["typing"],
        *,
        check: Optional[Callable[[User, datetime], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Tuple[User, datetime]]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_receive"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_send"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_accept"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_decline"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_cancel"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_expire"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["trade_counter"],
        *,
        check: Optional[Callable[[TradeOffer], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[TradeOffer]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["user_invite"],
        *,
        check: Optional[Callable[[UserInvite], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[UserInvite]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["clan_invite"],
        *,
        check: Optional[Callable[[ClanInvite], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[ClanInvite]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["socket_receive"],
        *,
        check: Optional[Callable[[Msgs], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Msgs]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["socket_raw_receive"],
        *,
        check: Optional[Callable[[bytes], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[bytes]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["socket_send"],
        *,
        check: Optional[Callable[[Msgs], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Msgs]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["socket_raw_send"],
        *,
        check: Optional[Callable[[bytes], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[bytes]: ...
