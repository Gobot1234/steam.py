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
) -> int:
    codes = []

    def run(*args: str) -> None:
        process = subprocess.run([sys.executable, "-m", *args])
        codes.append(process.returncode)

    if format:
        run("isort", ".")
        run("black", ".")
    if test:
        run("pytest")

    return max(codes or [0])


if __name__ == "__main__":
    exit(app())
