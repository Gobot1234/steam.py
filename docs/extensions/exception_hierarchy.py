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

from docutils import nodes
from docutils.parsers.rst import Directive


class exception_hierarchy(nodes.General, nodes.Element):
    pass


def visit_exception_hierarchy_node(self, node):
    self.body.append(self.starttag(node, "div", CLASS="exception-hierarchy-content"))


def depart_exception_hierarchy_node(self, node):
    self.body.append("</div>\n")


class ExceptionHierarchyDirective(Directive):
    has_content = True

    def run(self):
        self.assert_has_content()
        node = exception_hierarchy("\n".join(self.content))
        self.state.nested_parse(self.content, self.content_offset, node)
        return [node]


def setup(app):
    app.add_node(
        exception_hierarchy, html=(visit_exception_hierarchy_node, depart_exception_hierarchy_node),
    )
    app.add_directive("exception_hierarchy", ExceptionHierarchyDirective)
