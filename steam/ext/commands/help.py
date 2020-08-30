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

from typing import TYPE_CHECKING, Dict, List, Optional

from .commands import Command
from .context import Context

if TYPE_CHECKING:
    from steam.ext import commands

    from .cog import Cog

__all__ = ("HelpCommand",)


class HelpCommand(Command):
    """The default implementation of the help command."""

    def __init__(self):
        super().__init__(self.command_callback, name="help", help="Shows this message.")
        self.context: Optional["Context"] = None
        self.cog: Optional["Cog"]

    def __repr__(self) -> str:
        return "<default help-command>"

    def _get_doc(self, command: "Command") -> str:
        try:
            return command.help.splitlines()[0]
        except (IndexError, AttributeError):
            return ""

    async def _parse_arguments(self, ctx: "Context"):
        # Make the parser think we don't have a cog so it doesn't
        # inject the parameter into `ctx.args`.
        original_cog = self.cog
        self.cog = None
        try:
            await super()._parse_arguments(ctx)
        finally:
            self.cog = original_cog

    async def command_callback(self, ctx: Context, *, content: str = None) -> None:
        """The actual implementation of the help command."""
        self.context = ctx
        bot = ctx.bot
        if content is None:
            mapping = self.get_bot_mapping()
            return await self.send_help(mapping)
        # check if it's a cog
        cog = bot.get_cog(content.capitalize())
        if cog is not None:
            return await self.send_cog_help(cog)
        command = bot.get_command(content)
        if command is not None:
            return await self.send_command_help(command)

        await self.command_not_found(content)

    def get_bot_mapping(self) -> Dict[Optional[str], List[Command]]:
        bot = self.context.bot
        mapping = {name: list(set(cog.__commands__.values())) for (name, cog) in bot.__cogs__.items()}
        categorized_commands = []
        for l in mapping.values():
            for command in l:
                categorized_commands.append(command)
        mapping[None] = [c for c in set(bot.commands) if c not in categorized_commands]
        return mapping

    async def send_help(self, mapping: Dict[Optional["commands.Cog"], List["commands.Command"]]) -> None:
        message = []
        for name, commands in mapping.items():
            if name is not None:
                message.append(f"--= {name}'s commands =--")
            else:
                message.append("--= Un-categorized commands =--")
            for command in commands:
                message.append(f'{command.name}{f": {self._get_doc(command)}" if command.help else ""}')
        await self.context.send("\n".join(message))

    async def send_cog_help(self, cog: "commands.Cog"):
        message = [f"--= {cog.qualified_name}'s commands =--"]
        for name, command in sorted(cog.__commands__.items()):
            message.append(f'{name}{f": {self._get_doc(command)}" if command.help else ""}')
        await self.context.send("\n".join(message))

    async def send_command_help(self, command: "commands.Command"):
        await self.context.send(f"Help with {command.name}:\n\n{command.help}")

    async def command_not_found(self, command: str):
        await self.context.send(f'The command "{command}" was not found.')
