"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import abc
import sys
import traceback
from copy import copy
from typing import TYPE_CHECKING, cast

from typing_extensions import Unpack, final

from .commands import Command, CommandKwargs, Group
from .context import Context  # noqa: TCH001

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from steam.ext import commands


__all__ = (
    "HelpCommand",
    "DefaultHelpCommand",
)


class HelpCommand(Command[None, ..., None]):
    """The base implementation of the help command."""

    context: Context
    """The context for the command's invocation."""

    def __init__(self, **kwargs: Unpack[CommandKwargs]):
        default = cast(CommandKwargs, {"name": "help", "help": "Shows this message."} | kwargs)
        super().__init__(self.command_callback, **default)

    async def invoke(self, ctx: Context) -> None:
        self = copy(self)
        ctx.command = self
        return await Command.invoke(self, ctx)  # type: ignore

    @final
    async def command_callback(self, ctx: Context, *, content: str | None = None) -> None:
        """The actual implementation of the help command.

        This method should not directly subclassed instead you should change the behaviour through the methods that
        actually get dispatched:

            - :meth:`send_cog_help`
            - :meth:`send_command_help`
            - :meth:`send_group_help`
            - :meth:`command_not_found`
        """
        self.context = ctx
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
                self.send_group_help(command) if isinstance(command, Group) else self.send_command_help(command)
            )

        await self.command_not_found(content)

    def get_bot_mapping(self) -> Mapping[str | None, Sequence[commands.Command]]:
        """
        Generate a mapping of the bot's commands. It's not normally necessary to subclass this. This is passed to
        :meth:`send_help`.
        """
        bot = self.context.bot
        return {cog.qualified_name: list(cog.commands) for cog in bot.cogs.values() if cog.commands} | {
            None: [c for c in bot.commands if c.cog is None]
        }

    @abc.abstractmethod
    async def send_help(self, mapping: Mapping[str | None, Sequence[commands.Command]]) -> None:
        """Send the basic help message for the bot's command.

        Parameters
        ----------
        mapping
            The mapping from :meth:`get_bot_mapping`.
        """

    @abc.abstractmethod
    async def send_cog_help(self, cog: commands.Cog) -> None:
        """The method called with a cog is passed as an argument.

        Note
        ----
        Cog names are case-sensitive.

        Parameters
        ----------
        cog
            The cog that was passed as an argument.
        """

    @abc.abstractmethod
    async def send_command_help(self, command: commands.Command) -> None:
        """The method called when a normal command is passed as an argument.

        Parameters
        ----------
        command
            The command that was passed as an argument.
        """

    @abc.abstractmethod
    async def send_group_help(self, command: commands.Group) -> None:
        """The method called when a group command is passed as an argument.

        Parameters
        ----------
        command
            The command that was passed as an argument.
        """

    @abc.abstractmethod
    async def command_not_found(self, command: str) -> None:
        """The default implementation for when a command isn't found.

        This by default sends "The command {command} was not found."

        Parameters
        ----------
        command
            The command that was not found.
        """

    async def on_error(self, ctx: commands.Context, error: Exception) -> None:
        """The default error handler for the help command. This performs the functionality as
        :meth:`steam.ext.commands.Bot.on_command_error`.

        Parameters
        ----------
        ctx
            The context for the invocation.
        error
            The error that was raised.
        """
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


class DefaultHelpCommand(HelpCommand):
    """The default implementation of the help command."""

    def __repr__(self) -> str:
        return "<default_help_command>"

    def _get_doc(self, command: Command) -> str:
        if command.help:
            try:
                return command.help.splitlines()[0]
            except IndexError:
                pass
        return ""

    async def send_help(self, mapping: Mapping[str | None, Sequence[commands.Command]]) -> None:
        message = ["/pre"]
        for cog_name, commands in mapping.items():
            (
                message.append(f"\n{cog_name}'s commands")
                if cog_name is not None
                else message.append("\nUn-categorized commands")
            )
            message += (
                f'{command.name}{f": {self._get_doc(command)}" if command.help else ""}' for command in commands
            )

        await self.context.send("\n".join(message))

    async def send_cog_help(self, cog: commands.Cog) -> None:
        message = [f"/pre {cog.qualified_name}'s commands"]
        for name in sorted(c.name for c in cog.commands):
            command = cog.__commands__[name]
            message.append(f'{name}{f": {self._get_doc(command)}" if command.help else ""}')
        await self.context.send("\n".join(message))

    async def send_command_help(self, command: commands.Command) -> None:
        await self.context.send(f"/pre Help with {command.name}:\n\n{command.help}")

    async def send_group_help(self, command: commands.Group) -> None:
        msg = [f"/pre Help with {command.name}:\n\n{command.help}"]
        if sub_commands := "\n".join(c.name for c in command.children):
            msg.append(f"\nAnd its sub commands:\n{sub_commands}")
        await self.context.send("\n".join(msg))

    async def command_not_found(self, command: str) -> None:
        """The default implementation for when a command isn't found.

        This by default sends "The command {command} was not found."

        Parameters
        ----------
        command
            The command that was not found.
        """
        await self.context.send(f"The command {command!r} was not found.")
