# -*- coding: utf-8 -*-

import contextlib
import traceback
from copy import copy
from io import StringIO
from typing import Any, Generator, Optional, TypeVar, Union

import pytest
from typing_extensions import TypeAlias

import steam
from steam.ext import commands
from tests.mocks import GROUP_MESSAGE

CE = TypeVar("CE", bound=commands.CommandError)
T = TypeVar("T")
IsInstanceable: TypeAlias = "Union[type[T], tuple[type[T], ...]]"
SomeCoolType = int
UserTypes = Union[steam.User, int, str]
FAILS: "list[Exception]" = []


@pytest.mark.asyncio
async def test_commands():
    with pytest.raises(TypeError):

        @commands.command
        def not_valid(_):
            ...

    with pytest.raises(TypeError):

        @commands.command(name=123)
        async def _123(_) -> None:
            ...

    with pytest.raises(TypeError):

        @commands.command(aliases=[1, 2, 3])
        async def _123(_) -> None:
            ...

    with pytest.raises(steam.ClientException):

        @commands.command
        async def not_valid() -> None:
            ...

    class MyCog(commands.Cog):
        with pytest.raises(steam.ClientException):

            @commands.command
            async def not_even_close() -> None:  # noqa
                ...

    bot = TheTestBot()

    class MyCog(commands.Cog):
        @commands.command
        async def not_valid(self) -> None:
            ...

    with pytest.raises(steam.ClientException):
        bot.add_cog(MyCog())


def test_annotations() -> None:
    @commands.command
    async def some_cool_command(_, cool_type: SomeCoolType) -> None:
        ...

    assert some_cool_command.clean_params.popitem()[1].annotation is SomeCoolType  # should be evaluated

    @commands.command
    async def get_an_user(_, user: "UserTypes") -> None:
        ...

    assert get_an_user.clean_params.popitem()[1].annotation == UserTypes


class CustomConverter(commands.Converter[tuple]):
    async def convert(self, ctx: commands.Context, argument: str) -> tuple:
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
def test_greedy(param_type: Union[type, str], expected: Union[int, "type[Exception]"]):
    global param_type_  # hack to make typing.get_type_hints work with locals
    param_type_ = param_type
    if issubclass(expected, Exception):
        with pytest.raises(expected):

            @commands.command
            async def greedy(_, param: commands.Greedy[param_type_]) -> None:
                ...

    else:

        @commands.command
        async def greedy(_, param: commands.Greedy[param_type_]) -> None:
            ...

        assert greedy.params["param"].annotation.converter is expected


class TheTestBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="")
        self.MESSAGE = GROUP_MESSAGE
        self.to_finish: "list[str]" = []

    @contextlib.asynccontextmanager
    async def raises_command_error(
        self, expected_errors: "IsInstanceable[type[CE]]", content: str
    ) -> "contextlib.AbstractAsyncContextManager[None]":
        expected_errors = (expected_errors,) if not isinstance(expected_errors, tuple) else expected_errors

        async def on_command_error(ctx: commands.Context, error: CE) -> None:
            error = error.__class__ if isinstance(error, Exception) else error
            if ctx.message.content == content:
                if error not in expected_errors:
                    raise error

                self.to_finish.remove(content)

        async def on_command_completion(ctx: commands.Context) -> None:
            if ctx.message.content == content:
                self.to_finish.remove(content)

        self.add_listener(on_command_error)
        self.add_listener(on_command_completion)

        yield

    @contextlib.asynccontextmanager
    async def returns_command_completion(self, content: str) -> "contextlib.AbstractAsyncContextManager[None]":
        async def on_command_error(ctx: commands.Context, error: CE) -> None:
            if ctx.message.content == content:
                raise error

        async def on_command_completion(ctx: commands.Context) -> None:
            if ctx.message.content == content:
                self.to_finish.remove(content)

        self.add_listener(on_command_error)
        self.add_listener(on_command_completion)

        yield

    async def process_commands(
        self,
        arguments: Optional[str] = None,
        exception: Optional["type[CE]"] = None,
        command: Optional[commands.Command] = None,
    ) -> None:
        command = command or list(self.__commands__.values())[-1]
        message = copy(self.MESSAGE)
        message.content = message.clean_content = f"{command.qualified_name} {arguments or ''}".strip()
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
            FAILS.append(Exception(f"{len(self.to_finish)} commands still being processed: {', '.join(self.to_finish)}"))


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
    input: str, excepted_exception: Optional["type[commands.CommandError]"]
) -> None:
    bot = TheTestBot()

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
async def test_variadic_commands(input: str, expected_exception: commands.CommandError) -> None:
    bot = TheTestBot()

    @bot.command
    async def test_var(_, *numbers: int) -> None:
        assert isinstance(numbers, tuple)
        for number in numbers:
            assert isinstance(number, int)
            assert len(str(number)) == 4

    await bot.process_commands(input, expected_exception)


@pytest.mark.asyncio
async def test_positional_only_commands():
    bot = TheTestBot()

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
    bot = TheTestBot()

    @contextlib.contextmanager
    def writes_to_console(msg: str) -> Generator[None, None, None]:
        stdout = StringIO()
        with contextlib.redirect_stdout(stdout):
            yield

        assert msg == stdout.getvalue().strip()

    @bot.group
    async def parent(_) -> None:
        print("In parent")

    @parent.group
    async def child(_) -> None:
        print("In child")

    @child.command
    async def grand_child(_) -> None:
        print("In grand child")

    @parent.group
    async def other_child(_) -> None:
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


called_image_converter = False
called_command_converter = False


@commands.converter_for(commands.Command)
def command_converter(argument: str) -> None:
    global called_command_converter
    called_command_converter = True


class ImageConverter(commands.Converter[steam.Image]):
    async def convert(self, ctx: commands.Context, argument: str) -> None:
        global called_image_converter
        called_image_converter = True


@pytest.mark.asyncio
async def test_converters() -> None:
    bot = TheTestBot()

    @bot.command
    async def source(_, command: commands.Command):
        ...

    assert command_converter.converter_for == commands.Command
    assert commands.Command in bot.converters
    await bot.process_commands("not a command", None)
    assert called_command_converter

    @bot.command
    async def set_avatar(_, image: steam.Image):
        ...

    assert ImageConverter.converter_for is steam.Image
    assert steam.Image in bot.converters
    await bot.process_commands("https://not_an_image.com", None)
    assert called_image_converter


def teardown_module(_) -> None:
    for error in FAILS:
        traceback.print_exception(error.__class__, error, error.__traceback__)
    if FAILS:
        pytest.fail("failed to finish tests")
