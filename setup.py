# -*- coding: utf-8 -*-

import pathlib
import re

from setuptools import setup

ROOT = pathlib.Path(__file__).parent


with open(ROOT / "steam" / "__init__.py") as f:
    try:
        VERSION = re.findall(r'^__version__\s*=\s*"([^"]*)"', f.read(), re.MULTILINE)[0]
    except IndexError:
        raise RuntimeError("Version is not set")

if VERSION.endswith(("a", "b")) or "rc" in VERSION:
    # try to find out the commit hash if checked out from git, and append
    # it to __version__ (since we use this value from setup.py, it gets
    # automatically propagated to an installed copy as well)
    try:
        import subprocess

        out = subprocess.getoutput("git rev-list --count HEAD")
        if out:
            version = f"{VERSION}{out.strip()}"
        out = subprocess.getoutput("git rev-parse --short HEAD")
        if out:
            version = f"{VERSION}+g{out.strip()}"
    except Exception:
        pass

with open(ROOT / "README.md", encoding="utf-8") as f:
    README = f.read()

EXTRA_REQUIRES = {}

for feature in (ROOT / "requirements").glob("*.txt"):
    with open(feature, "r", encoding="utf-8") as f:
        EXTRA_REQUIRES[feature.with_suffix("").name] = f.read().splitlines()

REQUIREMENTS = EXTRA_REQUIRES.pop("default")


setup(
    name="steamio",
    author="Gobot1234",
    url="https://github.com/Gobot1234/steam.py",
    project_urls={
        "Documentation": "https://steampy.readthedocs.io/en/latest",
        "Code": "https://github.com/Gobot1234/steam.py",
        "Issue tracker": "https://github.com/Gobot1234/steam.py/issues",
    },
    version=VERSION,
    packages=[
        "steam",
        "steam.protobufs",
        "steam.ext.commands",
    ],
    package_data={
        "steam": ["*.pyi", "py.typed"],
    },
    license="MIT",
    description="A Python wrapper for the Steam API",
    long_description=README,
    long_description_content_type="text/markdown",
    include_package_data=True,
    install_requires=REQUIREMENTS,
    extras_require=EXTRA_REQUIRES,
    python_requires=">=3.7.0",
    download_url=f"https://github.com/Gobot1234/steam.py/archive/{VERSION}.tar.gz",
    keywords="steam.py steam steamio steam-api",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Framework :: AsyncIO",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
