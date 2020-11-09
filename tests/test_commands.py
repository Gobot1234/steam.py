# -*- coding: utf-8 -*-

from __future__ import annotations

import contextlib
from copy import copy
from io import StringIO
from typing import AsyncGenerator, Generator, Optional, TypeVar, Union

import pytest

import steam
from steam.ext import commands
from tests.mocks import GROUP_CHANNEL, MockGroupMessage

CE = TypeVar("CE", bound=commands.CommandError)
T = TypeVar("T")
IsInstanceable = Union["type[T]", "tuple[type[T], ...]"]


@pytest.mark.asyncio
async def test_commands():
    with pytest.raises(TypeError):

        @commands.command
        def not_valid(ctx):
            ...

    with pytest.raises(TypeError):

        @commands.command(name=123)
        async def _123(ctx) -> None:
            ...

    with pytest.raises(TypeError):

        @commands.command(aliases=[1, 2, 3])
        async def _123(ctx) -> None:
            ...

    with pytest.raises(steam.ClientException):

        @commands.command
        async def not_valid() -> None:
            ...

    class MyCog(commands.Cog):
        with pytest.raises(steam.ClientException):

            @commands.command
            async def not_even_close() -> None:
                ...

    bot = TestBot()

    class MyCog(commands.Cog):
        @commands.command
        async def not_valid(self) -> None:
            ...

    with pytest.raises(steam.ClientException):
        bot.add_cog(MyCog())


def test_greedy():
    with pytest.raises(TypeError):

        @commands.command()
        async def greedy(ctx, param: commands.Greedy[None]):
            pass

    with pytest.raises(TypeError):

        @commands.command()
        async def greedy(ctx, param: commands.Greedy[str]):
            pass


class TestBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="")
        self.message = MockGroupMessage(GROUP_CHANNEL)

    @contextlib.asynccontextmanager
    async def raises_command_error(
        self, expected_errors: IsInstanceable[type[CE]], content: str
    ) -> AsyncGenerator[None, None]:
        expected_errors = (expected_errors,) if not isinstance(expected_errors, tuple) else expected_errors

        async def on_command_error(ctx: commands.Context, error: CE) -> None:
            error = error.__class__ if isinstance(error, Exception) else error
            if ctx.message.content == content:
                if error not in expected_errors:
                    raise error

        self.add_listener(on_command_error)

        yield

    @contextlib.asynccontextmanager
    async def returns_command_completion(self, content: str) -> AsyncGenerator[None, None]:
        async def on_command_error(ctx: commands.Context, error: CE) -> None:
            if ctx.message.content == content:
                raise error

        self.add_listener(on_command_error)

        yield

    async def process_commands(
        self,
        arguments: Optional[str] = None,
        exception: Optional[type[CE]] = None,
        command: Optional[commands.Command] = None,
    ) -> None:
        command = command or list(self.__commands__.values())[-1]
        self.message = copy(self.message)
        self.message.content = f"{command.qualified_name} {arguments or ''}".strip()

        if exception is not None:

            async with self.raises_command_error(exception, self.message.content):
                await super().process_commands(self.message)

        else:

            async with self.returns_command_completion(self.message.content):
                await super().process_commands(self.message)

    async def on_error(self, event: str, error: Exception, *args, **kwargs):
        ctx: commands.Context = args[0]
        lex = ctx.lex
        message = ctx.message
        command = ctx.command
        raise SystemExit  # we need to propagate a SystemExit for pytest to be able to pick up errors


@pytest.mark.asyncio
async def test_positional_or_keyword_commands() -> None:
    bot = TestBot()

    @bot.command
    async def test_positional(_, number: int) -> None:
        assert isinstance(number, int)
        assert len(str(number)) == 4

    inputs = [
        ("", commands.MissingRequiredArgument),
        ("1234", None),
        ("1234 1234", None),
        ("string", commands.BadArgument),
    ]

    for args, excepted_exception in inputs:
        await bot.process_commands(args, excepted_exception)


@pytest.mark.asyncio
async def test_variadic_commands() -> None:
    bot = TestBot()

    @bot.command
    async def test_var(_, *numbers: int) -> None:
        assert isinstance(numbers, tuple)
        for number in numbers:
            assert isinstance(number, int)
            assert len(str(number)) == 4

    inputs = [
        ("", None),
        ("1234", None),
        ("1234 1234", None),
        ("1234        1234        1234        1234        1234", None),
        ("string", commands.BadArgument),
    ]

    for args, excepted_exception in inputs:
        await bot.process_commands(args, excepted_exception)


@pytest.mark.asyncio
async def test_positional_only_commands():
    bot = TestBot()

    @bot.command
    async def test_consume_rest_int(_, *, number: int) -> None:
        assert isinstance(number, int)

    inputs = [
        ("", commands.MissingRequiredArgument),
        ("1234", None),
        ("123412341234", None),
        ("string", commands.BadArgument),
    ]

    for args, excepted_exception in inputs:
        await bot.process_commands(args, excepted_exception)

    @bot.command
    async def test_consume_rest_str(_, *, string: str) -> None:
        assert isinstance(string, str)
        assert len(string.split()) == 3

    inputs = [
        ("", commands.MissingRequiredArgument),
        ("string string string", None),
        ("1234 1234 1234", None),
    ]

    for args, excepted_exception in inputs:
        await bot.process_commands(args, excepted_exception)

    @bot.group
    async def test_sub(_) -> None:
        pass

    inputs = [
        ("", None),
        ("string string string", None),
        ("1234123412134", None),
        ("string", None),
    ]

    for args, excepted_exception in inputs:
        await bot.process_commands(args, excepted_exception)

    @test_sub.command
    async def sub(_, *, string: str) -> None:
        assert string == "cool string string string"

    inputs = [
        ("", commands.MissingRequiredArgument),
        ("cool string string string", None),
    ]

    for args, excepted_exception in inputs:
        await bot.process_commands(args, excepted_exception, command=sub)


@pytest.mark.asyncio
async def test_group_commands() -> None:
    bot = TestBot()

    @contextlib.contextmanager
    def writes_to_console(msg: str) -> Generator[None, None, None]:
        stdout = StringIO()
        with contextlib.redirect_stdout(stdout):
            yield

        assert msg == stdout.getvalue().strip()

    @bot.group
    async def parent(ctx):
        print("In parent")

    @parent.group
    async def child(ctx):
        print("In child")

    @child.command
    async def grand_child(ctx):
        print("In grand child")

    @parent.group
    async def other_child(ctx):
        print("In other child")

    assert bot.get_command("parent") is parent

    with writes_to_console("In parent"):
        await bot.process_commands(command=parent)

    assert bot.get_command("child") is None
    assert bot.get_command("parent child") is child

    with writes_to_console("In child"):
        await bot.process_commands(command=child)

    assert bot.get_command("grand_child") is None
    assert bot.get_command("child grand_child") is None
    assert bot.get_command("parent child grand_child") is grand_child

    with writes_to_console("In grand child"):
        await bot.process_commands(command=grand_child)

    assert bot.get_command("other_child") is None
    assert bot.get_command("parent other_child") is other_child

    with writes_to_console("In other child"):
        await bot.process_commands(command=other_child)
