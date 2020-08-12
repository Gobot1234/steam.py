# -*- coding: utf-8 -*-

import pathlib
import pytest
import click
import black
import isort.main
import yaml

__FILE__ = pathlib.Path(__file__)
STEAM_PY = __FILE__.parent.parent
STEAM = STEAM_PY / "steam"
EXAMPLES = STEAM_PY / "examples"
TESTS = STEAM_PY / "tests"
WORKFLOWS = STEAM_PY / ".github" / "workflows"

with open(WORKFLOWS / "blacken.yml") as f:
    BLACK_SETTINGS = yaml.safe_load(f)

with open(WORKFLOWS / "isort.yml") as f:
    ISORT_SETTINGS = yaml.safe_load(f)


def prepare_args(args: dict) -> list:
    final_steps: str = args["jobs"]["check-formatting"]["steps"][-1:][0]["run"]
    return (
        final_steps.split("--diff")[0]
        .strip("isort")
        .strip("black")
        .replace("steam", str(STEAM.absolute()))
        .replace("examples", str(EXAMPLES.absolute()))
        .replace("tests", str(TESTS.absolute()))
        .strip()
        .split()
    )


@click.command()
@click.option(
    "-t", "--test", is_flag=True, help="Whether or not to run the tests.",
)
@click.option(
    "-f", "--format", is_flag=True, help="Whether or not to run the format code.",
)
@click.pass_context
def main(
    ctx: click.Context, test: bool, format: bool,
):
    if format:
        print("Starting formatting")
        isort.main.main(prepare_args(ISORT_SETTINGS))
        black_ctx = black.main.make_context(__file__, prepare_args(BLACK_SETTINGS))
        black.main.invoke(black_ctx)
        print("Done running formatting")
    if test:
        ctx.exit(pytest.main())


if __name__ == "__main__":
    black.freeze_support()
    black.patch_click()
    main()
