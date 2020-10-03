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

import sys
import traceback
from typing import TYPE_CHECKING, Optional

from typing_extensions import final

from .commands import Command, GroupCommand
from .context import Context

if TYPE_CHECKING:
    from steam.ext import commands

    from .cog import Cog

__all__ = ("HelpCommand",)


class HelpCommand(Command):
    """The default implementation of the help command.

    Attributes
    ----------
    context: :class:`~steam.ext.commands.Context`
        The context for the command's invocation.
    """

    context: Context

    def __init__(self, **kwargs):
        default = dict(name="help", help="Shows this message.", cog=self)
        default.update(kwargs)
        super().__init__(self.command_callback, **default)

    def __repr__(self) -> str:
        return "<default help-command>"

    def _get_doc(self, command: Command) -> str:
        try:
            return command.help.splitlines()[0]
        except (IndexError, AttributeError):
            return ""

    @final
    async def command_callback(self, ctx: Context, *, content: str = None) -> None:
        """The actual implementation of the help command.

        This method should not directly subclassed instead you should change the behaviour through the methods that
        actually get dispatched:

        - :meth:`send_cog_help`
        - :meth:`send_command_help`
        - :meth:`send_group_help`
        - :meth:`command_not_found`
        """
        self.context = ctx
        try:
            bot = ctx.bot
            if content is None:
                mapping = self.get_bot_mapping()
                return await self.send_help(mapping)
            # check if it's a cog
            cog = bot.get_cog(content)
            if cog is not None:
                return await self.send_cog_help(cog)
            command = bot.get_command(content)
            if command is not None:
                return await (
                    self.send_group_help(command)
                    if isinstance(command, GroupCommand)
                    else self.send_command_help(command)
                )

            await self.command_not_found(content)
        finally:
            del self.context

    def get_bot_mapping(self) -> "dict[Optional[str], list[Command]]":
        bot = self.context.bot
        mapping = {name: list(cog.commands) for name, cog in bot.__cogs__.items()}
        categorized_commands = []
        for l in mapping.values():
            for command in l:
                categorized_commands.append(command)
        mapping[None] = [c for c in bot.commands if c not in categorized_commands]
        return mapping

    async def send_help(self, mapping: "dict[Optional[commands.Cog], list[commands.Command]]") -> None:
        message = ["/pre"]
        for name, commands in mapping.items():
            if name is not None:
                message.append(f"{name}'s commands")
            else:
                message.append("Un-categorized commands")
            for command in commands:
                message.append(f'{command.name}{f": {self._get_doc(command)}" if command.help else ""}')
        await self.context.send("\n".join(message))

    async def send_cog_help(self, cog: "commands.Cog") -> None:
        message = [f"/pre {cog.qualified_name}'s commands"]
        for name, command in sorted(cog.__commands__.items()):
            message.append(f'{name}{f": {self._get_doc(command)}" if command.help else ""}')
        await self.context.send("\n".join(message))

    async def send_command_help(self, command: "commands.Command") -> None:
        await self.context.send(f"/pre Help with {command.name}:\n\n{command.help}")

    async def send_group_help(self, command: "commands.GroupCommand") -> None:
        msg = [f"/pre Help with {command.name}:\n\n{command.help}"]
        sub_commands = "\n".join(c.name for c in command.children)
        if sub_commands:
            msg.append(f"\nAnd its sub commands:\n{sub_commands}")
        await self.context.send("\n".join(msg))

    async def command_not_found(self, command: str) -> None:
        await self.context.send(f'The command "{command}" was not found.')

    async def on_error(self, ctx: "commands.Context", error: Exception) -> None:
        print(f"Ignoring exception in command {ctx.command.name}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    cog_command_error = on_error
