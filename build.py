from __future__ import annotations

import os
import pathlib
import re
import subprocess
from typing import TYPE_CHECKING

import tomlkit

if TYPE_CHECKING:
    from typing_extensions import TypeAlias

ROOT = pathlib.Path(".").resolve()
PYPROJECT = tomlkit.loads((ROOT / "pyproject.toml").read_text("utf-8"))
try:
    VERSION: str = PYPROJECT["tool"]["poetry"]["version"].value  # noqa
except KeyError:
    raise RuntimeError("Version is not set") from None


RELEASE_LEVELS = {
    "a": "alpha",
    "b": "beta",
    "rc": "candidate",
}

try:
    end_char = re.findall(r"\d+.\d+.\d+([^\d]*).*", VERSION)[0]
except IndexError:
    end_char = ""
    release_level = "final"
else:
    release_level = RELEASE_LEVELS[end_char]

if release_level != "final":
    # try to find out the commit hash if checked out from git, and append it to __version__ (since we use this value
    # from setup.py, it gets automatically propagated to an installed copy as well)
    try:
        commit_count = subprocess.check_output(["git", "rev-list", "--count", "HEAD"]).decode("utf-8").strip()
        if commit_count:
            commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("utf-8").strip()
            if commit_hash:
                VERSION = f"{VERSION}{commit_hash}+g{commit_hash}"
    except Exception:
        pass


major, minor, micro = VERSION.split(".")
micro = micro.split(end_char, maxsplit=1)[0]
# TypeAlias to allow for syntax highlighting
file: TypeAlias = f"""
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
""".strip()


metadata = ROOT / "steam" / "__metadata__.py"
metadata.write_text(file)

build = lambda *args, **kwargs: open("/Users/James/pip-install-stuff", "w+").write(
    f"hi, {VERSION}, {end_char}, {release_level}, {globals().get('commit_count')}, {globals().get('commit_hash')} {args} {kwargs}"
)

open("/Users/James/pip-install-stuff", "w+").write(
    f"hi, {VERSION}, {end_char}, {release_level}, {globals().get('commit_count')}, {globals().get('commit_hash')}"
)
