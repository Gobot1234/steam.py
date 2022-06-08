from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

import click
from sphinx.cmd.build import build_main

ROOT = Path(__file__).parent.parent
DOCS_STEAM_PY = ROOT / "docs"


@click.command()
@click.option("--tag", default=None)
@click.option("--sphinx-options")
@click.option("--push-path", type=Path)
def main(tag: str | None, push_path: Path):
    # (push_path / tag).unlink(missing_ok=True)
    GITHUB_PAGES = ROOT / "steam-py.github.io"
    GITHUB_PAGES_DOCS = GITHUB_PAGES / "docs"
    target_dir = GITHUB_PAGES_DOCS / tag or "latest"

    build_main(
        [
            str(DOCS_STEAM_PY),
            str(target_dir),
            *(str(p) for p in DOCS_STEAM_PY.rglob("*.rst|*.md")),
            "-b",
            "dirhtml",
            "-a",
            "-E",
            "-T",
        ]
    )

    # build_main(shlex.split(sphinx_options))

    if tag:
        try:
            (GITHUB_PAGES_DOCS / "stable").symlink_to(target_dir, target_is_directory=True)
        except FileExistsError:
            pass

    with (GITHUB_PAGES / "index.json").open("r") as fp:
        index = json.load(fp)
        if tag:
            index["docs"]["tags"].append(tag)

    with (GITHUB_PAGES / "index.json").open("w+") as fp:
        json.dump(index, fp, indent=2)


if __name__ == "__main__":
    main()
