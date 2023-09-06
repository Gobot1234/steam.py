# ruff: noqa: F811
import contextlib
import traceback
from collections.abc import AsyncGenerator
from contextvars import ContextVar
from copy import copy
from typing import Any, TypeAlias, TypeVar, cast

import pytest

import steam
from steam._const import TaskGroup
from steam.ext import commands
from tests.unit.mocks import GROUP_MESSAGE

T = TypeVar("T")
IsInstanceable: TypeAlias = type[T] | tuple[type[T], ...]
SomeCoolType = int
UserTypes = steam.User | int | str
FAILS: list[Exception] = []


@pytest.mark.asyncio
async def test_commands():
    with pytest.raises(TypeError):

        @commands.command  # type: ignore
        def not_valid(_):
            ...

    with pytest.raises(TypeError):

        @commands.command(name=123)  # type: ignore
        async def _123(_) -> None:
            ...

    with pytest.raises(TypeError):

        @commands.command(aliases=[1, 2, 3])  # type: ignore
        async def _123(_) -> None:
            ...

    with pytest.raises(TypeError):

        @commands.command  # type: ignore
        async def not_valid() -> None:
            ...

    class MyCog(commands.Cog):
        with pytest.raises(TypeError):

            @commands.command  # type: ignore
            async def not_even_close() -> None:
                ...

    async with TheTestBot() as bot:

        class MyCog2(commands.Cog):
            @commands.command  # type: ignore
            async def not_valid(self) -> None:
                ...

    with pytest.raises(TypeError):
        await bot.add_cog(MyCog())


def test_annotations() -> None:
    @commands.command
    async def some_cool_command(_, cool_type: SomeCoolType) -> None:
        ...

    assert some_cool_command.clean_params.popitem()[1].annotation is SomeCoolType  # should be evaluated

    @commands.command
    async def get_an_user(_, user: "UserTypes") -> None:
        ...

    assert get_an_user.clean_params.popitem()[1].annotation == UserTypes


class CustomConverter(commands.Converter[tuple[Any, ...]]):
    async def convert(self, ctx: commands.Context, argument: str) -> tuple[Any, ...]:
        ...


@pytest.mark.parametrize(
    "param_type, expected",
    [
        (None, TypeError),
        (str, TypeError),
        (int, int),
        (CustomConverter, CustomConverter),
        ("None", TypeError),
        ("str", TypeError),
        ("int", int),
    ],
)
def test_greedy(param_type: type | str, expected: type) -> None:
    global param_type_  # hack to make typing.get_type_hints work with locals
    param_type_ = param_type
    if issubclass(expected, Exception):
        with pytest.raises(expected):

            @commands.command
            async def greedy(_, param: commands.Greedy[param_type_]) -> None:  # type: ignore
                ...

    else:

        @commands.command
        async def greedy(_, param: commands.Greedy[param_type_]) -> None:  # type: ignore
            ...

        assert greedy.params["param"].annotation.converter is expected


class TheTestBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="")
        self.MESSAGE = GROUP_MESSAGE
        self.to_finish: list[str] = []
        self._tg = TaskGroup()
        self.entered_tg = False

    @contextlib.asynccontextmanager
    async def raises_command_error(
        self, expected_errors: type[commands.CommandError] | tuple[type[commands.CommandError], ...], content: str
    ) -> AsyncGenerator[None, None]:
        if not isinstance(expected_errors, tuple):
            expected_errors = (expected_errors,)

        async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
            if ctx.message.content == content:
                if type(error) not in expected_errors:
                    raise error

                self.to_finish.remove(content)

        async def on_command_completion(ctx: commands.Context) -> None:
            if ctx.message.content == content:
                self.to_finish.remove(content)

        self.add_listener(on_command_error)
        self.add_listener(on_command_completion)

        yield

        self.remove_listener(on_command_error)
        self.remove_listener(on_command_completion)

    @contextlib.asynccontextmanager
    async def returns_command_completion(self, content: str) -> AsyncGenerator[None, None]:
        async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
            if ctx.message.content == content:
                raise error

        async def on_command_completion(ctx: commands.Context) -> None:
            if ctx.message.content == content:
                self.to_finish.remove(content)

        self.add_listener(on_command_error)
        self.add_listener(on_command_completion)

        yield

        self.remove_listener(on_command_error)
        self.remove_listener(on_command_completion)

    async def process_commands(  # type: ignore
        self,
        arguments: str | None = None,
        exception: type[commands.CommandError] | None = None,
        command: commands.Command | None = None,
    ) -> None:
        command = command or list(self.__commands__.values())[-1]
        message = copy(self.MESSAGE)
        message.content = message.clean_content = steam.utils.BBCodeStr(
            f"{command.qualified_name} {arguments or ''}".strip(), []
        )
        self.to_finish.append(message.content)

        if exception is not None:
            async with self.raises_command_error(exception, message.content):
                await super().process_commands(message)

        else:
            async with self.returns_command_completion(message.content):
                await super().process_commands(message)

    async def on_error(self, event: str, error: Exception, *args: Any, **kwargs: Any) -> None:
        FAILS.append(error)

    def __del__(self):
        if self.to_finish:
            FAILS.append(
                Exception(f"{len(self.to_finish)} commands still being processed: {', '.join(self.to_finish)}")
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input, excepted_exception",
    [
        ("", commands.MissingRequiredArgument),
        ("1234", None),
        ("1234 1234", None),
        ("string", commands.BadArgument),
    ],
)
async def test_positional_or_keyword_commands(
    input: str, excepted_exception: type[commands.CommandError] | None
) -> None:
    async with TheTestBot() as bot:

        @bot.command
        async def test_positional(_, number: int) -> None:
            assert isinstance(number, int)
            assert len(str(number)) == 4

        await bot.process_commands(input, excepted_exception)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "input, expected_exception",
    [
        ("", None),
        ("1234", None),
        ("1234 1234", None),
        ("1234        1234        1234        1234        1234", None),
        ("string", commands.BadArgument),
    ],
)
async def test_variadic_commands(input: str, expected_exception: type[commands.CommandError] | None) -> None:
    async with TheTestBot() as bot:

        @bot.command
        async def test_var(_, *numbers: int) -> None:
            assert isinstance(numbers, tuple)
            for number in numbers:
                assert isinstance(number, int)
                assert len(str(number)) == 4

        await bot.process_commands(input, expected_exception)


@pytest.mark.asyncio
async def test_positional_only_commands():
    async with TheTestBot() as bot:

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
    async with TheTestBot() as bot:
        context = ContextVar[Any]("context")

        async def call(command: commands.Command):
            await bot.process_commands(command=command)
            assert context.get() == command

        @bot.group
        async def parent(_) -> None:
            context.set(parent)

        @parent.group
        async def child(_) -> None:
            context.set(child)

        @child.command
        async def grand_child(_) -> None:
            context.set(grand_child)

        @parent.group
        async def other_child(_) -> None:
            context.set(other_child)

        assert bot.get_command("parent") is parent
        await call(parent)

        assert bot.get_command("child") is None
        assert bot.get_command("parent child") is child
        await call(child)

        assert bot.get_command("grand_child") is None
        assert bot.get_command("child grand_child") is None
        assert bot.get_command("parent child grand_child") is grand_child
        await call(grand_child)

        assert bot.get_command("other_child") is None
        assert bot.get_command("parent other_child") is other_child
        await call(other_child)


called_image_converter = False
called_command_converter = False


@commands.converter
def command_converter(argument: str) -> commands.Command:
    global called_command_converter
    called_command_converter = True
    return cast(commands.Command, None)


class MediaConverter(commands.Converter[steam.Media]):
    async def convert(self, ctx: commands.Context, argument: str) -> steam.Media:
        global called_image_converter
        called_image_converter = True
        return cast(steam.Media, None)


@pytest.mark.asyncio
async def test_converters() -> None:
    async with TheTestBot() as bot:

        @bot.command
        async def source(_, command: commands.Command):
            ...

        assert command_converter.converter_for == commands.Command
        assert commands.Command in bot.converters
        await bot.process_commands("not a command", None)
        assert called_command_converter

        @bot.command
        async def set_avatar(_, image: steam.Media):
            ...

        assert MediaConverter.converter_for is steam.Media
        assert steam.Media in bot.converters
        await bot.process_commands("https://not_an_image.com", None)
        assert called_image_converter


def teardown_module(_) -> None:
    for error in FAILS:
        traceback.print_exception(error)
    if FAILS:
        pytest.fail("failed to finish tests")
