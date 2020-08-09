# -*- coding: utf-8 -*-

import re

from setuptools import setup

with open("requirements.txt") as f:
    requirements = f.read().splitlines()
    f.close()

with open("steam/__init__.py") as f:
    search = re.search(r'^__version__\s*=\s*"([^"]*)"', f.read(), re.MULTILINE)

if search is None:
    raise RuntimeError("Version is not set")

version = search.group(1)

if version.endswith(("a", "b")) or "rc" in version:
    # try to find out the commit hash if checked out from git, and append
    # it to __version__ (since we use this value from setup.py, it gets
    # automatically propagated to an installed copy as well)
    try:
        import subprocess

        out = subprocess.getoutput("git rev-list --count HEAD")
        if out:
            version = f"{version}{out.strip()}"
        out = subprocess.getoutput("git rev-parse --short HEAD")
        if out:
            version = f"{version}+g{out.strip()}"
    except Exception:
        pass

with open("README.md") as f:
    readme = f.read()

extras_require = {"docs": ["sphinx==3.0.1", "sphinxcontrib_trio==1.1.1", "sphinxcontrib-websupport",]}

setup(
    name="steamio",
    author="Gobot1234",
    url="https://github.com/Gobot1234/steam.py",
    project_urls={
        "Documentation": "https://steampy.readthedocs.io/en/latest",
        "Issue tracker": "https://github.com/Gobot1234/steam.py/issues",
    },
    version=version,
    packages=["steam", "steam.protobufs", "steam.ext.commands",],
    license="MIT",
    description="A Python wrapper for the Steam API",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    install_requires=requirements,
    extras_require=extras_require,
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
