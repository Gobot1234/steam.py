from __future__ import annotations

from typing import TYPE_CHECKING

from sphinx.ext import autodoc

from docs.extensions import is_async_iterable

if TYPE_CHECKING:
    from sphinx.application import Sphinx


def add_directive_header(self: autodoc.Documenter, sig: str) -> None:
    """Add the directive header and options to the generated content."""
    domain = getattr(self, "domain", "py")
    directive = getattr(self, "directivetype", self.objtype)
    name = self.format_name()
    source_name = self.get_sourcename()

    # one signature per line, indented by column
    prefix = f".. {domain}:{directive}:: "
    for i, sig_line in enumerate(sig.split("\n")):
        self.add_line(f"{prefix}{name}{sig_line}", source_name)
        if i == 0:
            prefix = " " * len(prefix)

    if self.options.noindex:
        self.add_line("   :noindex:", source_name)
    if self.objpath:
        # Be explicit about the module, this is necessary since .. class::
        # etc. don't support a prepended module name
        self.add_line(f"   :module: {self.modname}", source_name)

    if self.objtype not in ("function", "method"):
        return

    if (self.object.__doc__ or "").startswith(("|maybecallabledeco|", "A decorator")):
        self.add_line("   :decorator:", source_name)

    if is_async_iterable(self.object):
        self.add_line("   :async-for:", source_name)


def setup(app: Sphinx) -> None:
    autodoc.Documenter.add_directive_header = add_directive_header
