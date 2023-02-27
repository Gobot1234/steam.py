"""
Shim for the perfect storm of a combination poe and blacken-docs are:
- blacken-docs refuses to support a --check flag so, the error code is always non-zero even if formatting occurred
- poe doesn't support "|| exit 0" at the end of a task
So we need a custom script for this

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""


import re
from pathlib import Path
from typing import Any

import blacken_docs
from black import mode
from black.const import DEFAULT_EXCLUDES, DEFAULT_LINE_LENGTH
from black.files import find_project_root

try:
    import tomllib
except ImportError:
    import tomli as tomllib

ROOT = Path(__file__).parent
DEFAULT_INCLUDES = r"(.md|.rst|.tex|.py)$"
INCLUDES_RE = re.compile(DEFAULT_INCLUDES)
EXCLUDES_RE = re.compile(DEFAULT_EXCLUDES[1:-1])  # this is probably meant to be compiled with regex


def main() -> None:
    project_root, _ = find_project_root((str(ROOT),))
    with project_root.joinpath("pyproject.toml").open("rb") as fp:
        PYPROJECT = tomllib.load(fp)

    section: dict[str, Any] = PYPROJECT.get("tool", {}).get("blacken-docs", {})
    line_length = section.get("line-length", DEFAULT_LINE_LENGTH)
    target_version = {mode.TargetVersion[val.upper()] for val in section.get("target-version", ())}
    file_mode = mode.Mode(target_version, line_length)

    for file in project_root.rglob("**/*"):
        if INCLUDES_RE.search(str(file)) and not EXCLUDES_RE.search(str(file)):
            blacken_docs.format_file(str(file), file_mode, skip_errors=False, rst_literal_blocks=True)


if __name__ == "__main__":
    main()
