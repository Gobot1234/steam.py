# An extension to copy the source for an object into the documentation, obviously don't put something massive here
# currently just used for one off namedtuples
from __future__ import annotations

import importlib
import inspect
from typing import TYPE_CHECKING

from docutils import nodes
from docutils.parsers.rst.directives.body import CodeBlock  # type: ignore
from sphinx.util.docutils import SphinxDirective

from docs.extensions import parse_name

if TYPE_CHECKING:
    from sphinx.application import Sphinx


class SourceDirective(SphinxDirective, CodeBlock):
    required_arguments = 1
    optional_arguments = 0

    def run(self) -> list[nodes.Node]:
        module_name, name = parse_name(self.arguments[0], self.env)
        self.arguments = ["python"]  # replace these now we have the value we care about
        object = getattr(importlib.import_module(module_name), name)
        self.content = [line.rstrip() for line in inspect.getsourcelines(object)[0]]

        return [nodes.Text(f"Source for {name}:\n"), *super().run()]


def setup(app: Sphinx) -> None:
    app.add_directive("source", SourceDirective)
