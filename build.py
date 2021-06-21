from __future__ import annotations

import pathlib
import re
import subprocess
from typing import TYPE_CHECKING

import tomli

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

ROOT = pathlib.Path(".").resolve()
PYPROJECT = tomli.load(open(ROOT / "pyproject.toml"))
try:
    VERSION: str = PYPROJECT["tool"]["poetry"]["version"]
except KeyError:
    raise RuntimeError("Version is not set") from None


RELEASE_LEVELS = {
    "a": "alpha",
    "b": "beta",
    "rc": "candidate",
}

try:
    end_char = re.findall(r"\d+.\d+.\d+([^\d]+).*", VERSION)[0]
except IndexError:
    release_level = "final"
    end_char = " "  # if this was empty, it would raise a ValueError
else:
    release_level = RELEASE_LEVELS[end_char]

    # try to find out the commit hash if checked out from git, and append it to __version__ (since we use this value
    # from setup.py, it gets automatically propagated to an installed copy as well)
    try:
        commit_count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"]).decode("utf-8").strip()
        if commit_count:
            commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("utf-8").strip()
            if commit_hash:
                VERSION = f"{VERSION}{commit_count}+g{commit_hash}"
    except Exception:
        pass


major, minor, micro = VERSION.split(".")
micro = micro.split(end_char, maxsplit=1)[0]
# TypeAlias to allow for syntax highlighting
file: TypeAlias = f"""\
from typing import NamedTuple

from typing_extensions import Literal

__all__ = (
    "__title__",
    "__author__",
    "__license__",
    "__version__",
    "version_info",
)


class VersionInfo(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: Literal["alpha", "beta", "candidate", "final"]


__title__ = "steam"
__author__ = "Gobot1234"
__license__ = "MIT"
__version__ = "{VERSION}"
version_info = VersionInfo(major={major}, minor={minor}, micro={micro}, releaselevel="{release_level}")
"""


metadata = ROOT / "steam" / "__metadata__.py"
metadata.write_text(file)
