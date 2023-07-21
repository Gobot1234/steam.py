# An extension to copy the source for an object into the documentation, obviously don't put something massive here
# currently just used for one off namedtuples
from __future__ import annotations

import importlib
import inspect
from typing import TYPE_CHECKING

from docutils import nodes
from docutils.parsers.rst import directives
from docutils.parsers.rst.directives.body import CodeBlock  # type: ignore
from sphinx.util import docutils
from sphinx.util.docutils import SphinxDirective

if TYPE_CHECKING:
    from sphinx.application import Sphinx


class SourceDirective(SphinxDirective, CodeBlock):
    required_arguments = 1
    optional_arguments = 0

    def run(self) -> list[nodes.Node]:
        qualified_name: str = self.arguments[0]
        module_name, _, name = qualified_name.rpartition(".")
        if not module_name:
            module_name: str = self.env.ref_context["py:module"]
        self.arguments = ["python3"]  # replace these now we have the value we care about
        object = getattr(importlib.import_module(module_name), name)
        self.content = [line.rstrip() for line in inspect.getsourcelines(object)[0]]

        return [nodes.Text(f"Source for {qualified_name}:\n"), *super().run()]


def setup(app: Sphinx) -> None:
    app.add_directive("source", SourceDirective)
