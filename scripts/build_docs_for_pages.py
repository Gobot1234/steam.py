"""
A script to build the docs for GitHub pages.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from sphinx.cmd.build import build_main

ROOT = Path(__file__).parent.parent
DOCS_STEAM_PY = ROOT / "docs"


@click.command()
@click.option("--tag", default=None)
def main(tag: str | None = None):
    GITHUB_PAGES = ROOT / "steam-py.github.io"
    GITHUB_PAGES_DOCS = GITHUB_PAGES / "docs"
    target_dir = GITHUB_PAGES_DOCS / (tag or "latest")

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

    if tag:
        STABLE = GITHUB_PAGES_DOCS / "stable"
        try:
            STABLE.unlink(missing_ok=True)
        except OSError:
            pass
        STABLE.symlink_to(target_dir.relative_to(GITHUB_PAGES_DOCS), target_is_directory=True)

        index = json.loads((GITHUB_PAGES / "index.json").read_text())

        if tag not in index["docs"]["tags"]:
            index["docs"]["tags"].append(tag)

        (GITHUB_PAGES / "index.json").write_text(json.dumps(index, indent=2))


if __name__ == "__main__":
    main()
