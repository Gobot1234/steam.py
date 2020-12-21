"""
The MIT License (MIT)

Copyright (c) 2015-2020 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from typing import Any, Dict, List, Tuple

import sphinx
from docutils import nodes, utils
from docutils.nodes import Node, system_message
from docutils.parsers.rst.states import Inliner
from sphinx.application import Sphinx
from sphinx.util.nodes import split_explicit_title
from sphinx.util.typing import RoleFunction


def make_link_role(resource_links: Dict[str, str]) -> RoleFunction:
    def role(
        typ: str,
        rawtext: str,
        text: str,
        lineno: int,
        in_liner: Inliner,
        options: Dict = {},  # noqa
        content: List[str] = [],  # noqa
    ) -> Tuple[List[Node], List[system_message]]:

        text = utils.unescape(text)
        has_explicit_title, title, key = split_explicit_title(text)
        full_url = resource_links[key]
        if not has_explicit_title:
            title = full_url
        pnode = nodes.reference(title, title, internal=False, refuri=full_url)
        return [pnode], []

    return role


def add_link_role(app: Sphinx) -> None:
    app.add_role("resource", make_link_role(app.config.resource_links))


def setup(app: Sphinx) -> Dict[str, Any]:
    app.add_config_value("resource_links", {}, "env")
    app.connect("builder-inited", add_link_role)
    return {"version": sphinx.__display_version__, "parallel_read_safe": True}
