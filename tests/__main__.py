# -*- coding: utf-8 -*-

import pathlib

try:
    import black
    import click
    import isort.main
    import pytest
except ImportError as exc:
    print(f'Failed to import {exc.name} make sure you installed "steamio[dev]" to get extra dependencies.')

PATH = pathlib.Path(__file__)
STEAM_PY = PATH.parent.parent
STEAM = STEAM_PY / "steam"
TESTS = STEAM_PY / "tests"


@click.command()
@click.option("-t", "--test", is_flag=True, help="Whether or not to run the tests.")
@click.option("-f", "--format", is_flag=True, help="Whether or not to run the format code.")
@click.pass_context
def main(ctx: click.Context, test: bool, format: bool = True) -> None:
    if format:
        black.out("Starting formatting")
        isort.main.main(
            [
                "steam",
                "tests",
                "--combine-as",
                "--profile",
                "black",
                "-l120",
                "-n",
            ]
        )
        black_ctx = black.main.make_context(
            __file__,
            [
                ".",
                "-l120",
            ],
        )
        black.main.invoke(black_ctx)
        black.out("Done running formatting")
    if test:
        testable_files = [f.as_posix() for f in TESTS.iterdir() if "test" in f.name]
        ctx.exit(pytest.main(testable_files))


main: click.Command


if __name__ == "__main__":
    black.freeze_support()
    black.patch_click()
    main()
