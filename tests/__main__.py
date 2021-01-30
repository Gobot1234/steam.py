# -*- coding: utf-8 -*-

import subprocess
import sys

try:
    import black
    import isort
    import pytest
    import pytest_asyncio
    import typer
except ImportError as exc:
    print(f'Failed to import {exc.name} make sure you installed "steamio[dev]" to get extra dependencies.')

app = typer.Typer()


@app.command()
def main(
    test: bool = typer.Option(False, "-t", "--test", help="Whether or not to run the tests."),
    format: bool = typer.Option(True, "-f", "--format", help="Whether or not to run the format code."),
) -> None:
    if format:
        subprocess.run([sys.executable, "-m", "isort", "."])
        subprocess.run([sys.executable, "-m", "black", "."])
    if test:
        subprocess.run([sys.executable, "-m", "pytest"])


if __name__ == "__main__":
    app()
