# -*- coding: utf-8 -*-

from __future__ import annotations

import contextlib
import sys
from typing import Union

import pytest

from steam.ext import commands

from .mocks import *


def test_command():
    with pytest.raises(TypeError):

        @commands.command()
        def not_valid(ctx):
            pass

    with pytest.raises(TypeError):

        @commands.command(name=123)
        async def _123(ctx):
            pass

    with pytest.raises(TypeError):

        @commands.command(aliases=[1, 2, 3])
        async def _123(ctx):
            pass


def test_greedy():
    with pytest.raises(TypeError):

        @commands.command()
        async def greedy(ctx, param: commands.Greedy[None]):
            pass

    with pytest.raises(TypeError):

        @commands.command()
        async def greedy(ctx, param: commands.Greedy[str]):
            pass


events: dict[str, Exception] = {}


@contextlib.asynccontextmanager
async def raises_command_error(
    expected_exception: Union[type[commands.CommandError], tuple[type[commands.CommandError]], ...],
):
    yield
    error = events.pop(sys._getframe(2).f_locals["message"].content, None)
    if not isinstance(error, expected_exception):
        pytest.fail(f"DID NOT RAISE {expected_exception}")


@pytest.mark.asyncio
async def test_commands():
    message = MockGroupMessage(GROUP_CHANNEL)
    bot = commands.Bot(command_prefix="!")

    @bot.event
    async def on_command_error(ctx: commands.Context, error: Exception):
        if isinstance(error, AssertionError):
            raise
        events[ctx.message.content] = error

    @bot.command()
    async def test_positional(ctx, number: int):
        assert isinstance(number, int)

    message.content = "!test_positional"
    async with raises_command_error(commands.MissingRequiredArgument):
        await bot.process_commands(message)

    message.content = "!test_positional 1234"
    await bot.process_commands(message)
    message.content = "!test_positional 123 123"
    await bot.process_commands(message)

    message.content = "!test_positional string"
    async with raises_command_error(commands.BadArgument):
        await bot.process_commands(message)

    # VARIADIC

    @bot.command()
    async def test_var(ctx, *numbers: int):
        assert isinstance(numbers, tuple)
        for number in numbers:
            assert isinstance(number, int)

    message.content = "!test_var"
    await bot.process_commands(message)

    message.content = "!test_var 123"
    await bot.process_commands(message)

    message.content = "!test_var 123 123 123 123"
    await bot.process_commands(message)

    message.content = "!test_var 123 string"
    async with raises_command_error(commands.BadArgument):
        await bot.process_commands(message)

    # POSITIONAL ONLY

    @bot.command()
    async def test_consume_rest(ctx, *, number: int):
        assert isinstance(number, int)

    message.content = "!test_consume_rest"
    async with raises_command_error(commands.MissingRequiredArgument):
        await bot.process_commands(message)

    message.content = "!test_consume_rest 123_123"
    await bot.process_commands(message)

    message.content = "!test_var 123_string"
    async with raises_command_error(commands.BadArgument):
        await bot.process_commands(message)

    bot.remove_command("test_consume_rest")

    @bot.command()
    async def test_consume_rest(ctx, *, string: str):
        assert isinstance(string, str)
        assert len(string.split()) == 3

    message.content = "!test_consume_rest string string string'"
    await bot.process_commands(message)

    @bot.group()
    async def test_sub(ctx):
        pass

    @test_sub.command()
    async def sub(ctx, *, string):
        assert string == "cool string string string"

    message.content = "!test_sub"
    await bot.process_commands(message)

    message.content = "!test_sub sub cool string string string"
    await bot.process_commands(message)

    if events:
        pytest.fail("An error wasn't processed")
