# ruff: noqa: PTH100
# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from __future__ import annotations

import builtins
import os
import sys
from pathlib import Path

import sphinx.util.inspect

builtins.__sphinx__ = True  # type: ignore
from steam import Enum, __version__ as release, __version__ as version, version_info

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

sys.path.insert(0, os.path.abspath(".."))
sys.path.append(os.path.abspath("extensions"))
ROOT = Path("..").resolve()

# -- General configuration ------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinxcontrib_trio",
    "myst_parser",
    "sphinx_codeautolink",
    *(p.stem for p in Path("extensions").glob("*.py") if not p.stem.startswith("_")),
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"

# Links used for cross-referencing stuff in other documentation
intersphinx_mapping = {
    "py": ("https://docs.python.org/3", None),
    "aio": ("https://docs.aiohttp.org/en/stable", None),
}

rst_prolog = """
.. |coro| replace:: This function is a |coroutine_link|_.
.. |maybecoro| replace:: This function *could be a* |coroutine_link|_.
.. |coroutine_link| replace:: *coroutine*
.. _coroutine_link: https://docs.python.org/3/library/asyncio-task.html#coroutine
.. |maybecallabledeco| replace:: A decorator that *could be called*.
"""

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# The suffix of source filenames.
source_suffix = ".rst"

# The encoding of source files.
# source_encoding = 'utf-8-sig'

# The master toctree document.
master_doc = "index"

# General information about the project.
project = "steam.py"
copyright = "2020, Gobot1234"
branch = "master" if version_info.releaselevel != "final" else version

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ["_build"]

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "friendly"


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
html_theme = "lutra"

html_context = {
    "discord_invite": "https://discord.gg/MQ68WUS",
    "module_extensions": [
        ("steam.ext.commands", "ext/commands"),
        ("steam.ext.csgo", "ext/csgo"),
        ("steam.ext.tf2", "ext/tf2"),
    ],
    "repository": "https://github.com/Gobot1234/steam.py",
}

extlinks = {
    "issue": (f"{html_context['repository']}/%s", "GH-"),
    "works": ("https://partner.steamgames.com/doc/%s", None),
}

resource_links = {
    "discord": html_context["discord_invite"],
    "issues": f"{html_context['repository']}/issues",
    "examples": f"{html_context['repository']}/tree/{branch}/examples",
}

# The name of an image file (within the static path) to use as favicon of the
# docs.  This file should be a Windows icon file (.ico) being 16x16 or 32x32
# pixels large.
html_favicon = "images/favicon.ico"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# The name of a javascript file (relative to the configuration directory) that
# implements a search results scorer. If empty, the default will be used.
# html_search_scorer = "_static/scorer.js"

html_js_files = []


def isenumclass(x: object) -> bool:
    return isinstance(x, type) and issubclass(x, Enum)


def isenumattribute(x: object) -> bool:
    return isinstance(x, Enum)


sphinx.util.inspect.isenumclass = isenumclass
sphinx.util.inspect.isenumattribute = isenumattribute

codeautolink_global_preface = """\
import steam
from steam import utils, abc
from steam.ext import commands

client = steam.Client.__new__(steam.Client)
bot = commands.Bot.__new__(commands.Bot)

user = steam.User.__new__(steam.User)
chat_group = steam.chat.ChatGroup.__new__(steam.chat.ChatGroup)
clan = steam.Clan.__new__(steam.Clan)
group = steam.Group.__new__(steam.Group)
offer = trade = steam.TradeOffer.__new__(steam.TradeOffer)
inventory = steam.Inventory.__new__(steam.Inventory)
app = steam.PartialApp.__new__(steam.PartialApp)
message = msg = steam.UserMessage.__new__(steam.UserMessage)
channel = steam.UserChannel.__new__(steam.UserChannel)

ctx = commands.Context.__new__(commands.Context)
"""
