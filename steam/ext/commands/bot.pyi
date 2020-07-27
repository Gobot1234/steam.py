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

from shlex import shlex as Shlex
from typing import (
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    final,
    overload,
)

from ...client import Client, EventType
from ...message import Message
from .cog import Cog, ExtensionType, InjectedListener
from .commands import Command
from .context import Context
from .help import HelpCommand

__all__ = ("Bot",)

StrOrIterStr = Union[str, Iterable[str]]
CommandPrefixType = Union[
    StrOrIterStr, Callable[["Bot", Message], Union[StrOrIterStr, Awaitable[StrOrIterStr]]],
]

class Bot(Client):
    __cogs__: Dict[str, Cog] = dict()
    __commands__: Dict[str, Command] = dict()
    __listeners__: Dict[str, List[Union[EventType, InjectedListener]]] = dict()
    __extensions__: Dict[str, ExtensionType] = dict()
    __inline_commands__: Dict[str, Command] = dict()
    help_command: HelpCommand
    command_prefix: CommandPrefixType
    owner_id: int
    owner_ids: Set[int]
    commands: Set[Command]
    cogs: Mapping[str, Cog]
    extensions: Mapping[str, ExtensionType]
    def __init__(
        self, *, command_prefix: CommandPrefixType, help_command: HelpCommand = HelpCommand(), **options,
    ): ...
    @final
    def add_cog(self, cog: Cog) -> None: ...
    @final
    def remove_cog(self, cog: Cog) -> None: ...
    @final
    def add_listener(self, func: Union[EventType, InjectedListener], name: Optional[str] = ...) -> None: ...
    @final
    def remove_listener(self, func: Union[EventType, InjectedListener], name: Optional[str] = ...) -> None: ...
    @final
    def listen(self, name: Optional[str] = ...) -> Callable[..., EventType]: ...
    @final
    def add_command(self, command: Command) -> None: ...
    @final
    def remove_command(self, command: Command) -> None: ...
    def command(self, *args, **kwargs) -> Callable[..., Command]: ...
    @final
    async def process_commands(self, message: Message) -> None: ...
    @final
    def get_command(self, name) -> Optional[Command]: ...
    @final
    def get_cog(self, name: str) -> Optional[Cog]: ...
    @final
    def get_extension(self, name: str) -> Optional[ExtensionType]: ...
    def load_extension(self, extension: str) -> None: ...
    def unload_extension(self, extension: str) -> None: ...
    def reload_extension(self, extension: str) -> None: ...
    async def invoke(self, ctx: Context) -> None: ...
    async def get_context(self, message: Message, *, cls: Type[Context] = ...) -> Context: ...
    async def get_prefix(self, message: Message) -> Optional[str]: ...
    async def close(self) -> None: ...
    async def on_message(self, message: Message): ...
    async def on_command_error(self, ctx: Context, error: Exception): ...
    async def on_command(self, ctx: Context): ...
    async def on_command_completion(self, ctx: Context): ...
    def dispatch(self, event: str, *args, **kwargs) -> None: ...
    @overload
    def wait_for(
        self,
        __event: Literal["command_error"],
        *,
        check: Optional[Callable[[Context, Exception], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Tuple[Context, Exception]]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["command"],
        *,
        check: Optional[Callable[[Context], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Context]: ...
    @overload
    def wait_for(
        self,
        __event: Literal["command_completion"],
        *,
        check: Optional[Callable[[Context], bool]] = ...,
        timeout: Optional[float] = ...,
    ) -> Awaitable[Context]: ...
