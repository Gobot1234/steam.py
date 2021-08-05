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
import contextlib
import importlib
import inspect
import re
from collections import OrderedDict, namedtuple
from contextlib import AbstractAsyncContextManager

import sphinxcontrib_trio
from docutils import nodes
from sphinx import addnodes
from sphinx.locale import _
from sphinx.util.docutils import SphinxDirective

from docs.extensions import is_async_iterable


class attributetable(nodes.General, nodes.Element):
    pass


class attributetablecolumn(nodes.General, nodes.Element):
    pass


class attributetabletitle(nodes.TextElement):
    pass


class attributetableplaceholder(nodes.General, nodes.Element):
    pass


class attributetablebadge(nodes.TextElement):
    pass


class attributetable_item(nodes.Part, nodes.Element):
    pass


def visit_attributetable_node(self, node):
    class_ = node["python-class"]
    self.body.append(f'<div class="py-attribute-table" data-move-to-id="{class_}">')


def visit_attributetablecolumn_node(self, node):
    self.body.append(self.starttag(node, "div", CLASS="py-attribute-table-column"))


def visit_attributetabletitle_node(self, node):
    self.body.append(self.starttag(node, "span"))


def visit_attributetablebadge_node(self, node):
    attributes = {
        "class": "py-attribute-table-badge",
        "title": node["badge-type"],
    }
    self.body.append(self.starttag(node, "span", **attributes))


def visit_attributetable_item_node(self, node):
    self.body.append(self.starttag(node, "li", CLASS="py-attribute-table-entry"))


def depart_attributetable_node(self, node):
    self.body.append("</div>")


def depart_attributetablecolumn_node(self, node):
    self.body.append("</div>")


def depart_attributetabletitle_node(self, node):
    self.body.append("</span>")


def depart_attributetablebadge_node(self, node):
    self.body.append("</span>")


def depart_attributetable_item_node(self, node):
    self.body.append("</li>")


_name_parser_regex = re.compile(r"(?P<module>[\w.]+\.)?(?P<name>\w+)")


class PyAttributeTable(SphinxDirective):
    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {}

    def parse_name(self, content):
        path, name = _name_parser_regex.match(content).groups()
        if path:
            modulename = path.rstrip(".")
        else:
            modulename = self.env.temp_data.get("autodoc:module")
            if not modulename:
                modulename = self.env.ref_context.get("py:module")
        if modulename is None:
            raise RuntimeError("modulename somehow None for %s in %s." % (content, self.env.docname))

        return modulename, name

    def run(self):
        """If you're curious on the HTML this is meant to generate:

        <div class="py-attribute-table">
            <div class="py-attribute-table-column">
                <span>_('Attributes')</span>
                <ul>
                    <li>
                        <a href="...">
                    </li>
                </ul>
            </div>
            <div class="py-attribute-table-column">
                <span>_('Methods')</span>
                <ul>
                    <li>
                        <a href="..."></a>
                        <span class="py-attribute-badge" title="decorator">D</span>
                    </li>
                </ul>
            </div>
        </div>

        However, since this requires the tree to be complete
        and parsed, it'll need to be done at a different stage and then
        replaced.
        """
        content = self.arguments[0].strip()
        node = attributetableplaceholder("")
        modulename, name = self.parse_name(content)
        node["python-doc"] = self.env.docname
        node["python-module"] = modulename
        node["python-class"] = name
        node["python-full-name"] = f"{modulename}.{name}"
        return [node]


def build_lookup_table(env):
    # Given an environment, load up a lookup table of
    # full-class-name: objects
    result = {}
    domain = env.domains["py"]

    ignored = {
        "data",
        "exception",
        "module",
        "class",
    }

    for fullname, _, objtype, docname, _, _ in domain.get_objects():
        if objtype in ignored:
            continue

        classname, _, child = fullname.rpartition(".")
        try:
            result[classname].append(child)
        except KeyError:
            result[classname] = [child]

    return result


TableElement = namedtuple("TableElement", "fullname label badge")


def process_attributetable(app, doctree, fromdocname):
    env = app.builder.env

    lookup = build_lookup_table(env)
    for node in doctree.traverse(attributetableplaceholder):
        modulename, classname, fullname = node["python-module"], node["python-class"], node["python-full-name"]
        groups = get_class_results(lookup, modulename, classname, fullname)
        table = attributetable("")
        for label, subitems in groups.items():
            if not subitems:
                continue
            table.append(class_results_to_node(label, sorted(subitems, key=lambda c: c.label)))

        table["python-class"] = fullname

        if not table:
            node.replace_self([])
        else:
            node.replace_self([table])


def get_class_results(lookup, modulename, name, fullname):
    module = importlib.import_module(modulename)
    cls = getattr(module, name)

    groups = OrderedDict(
        [
            (_("Attributes"), []),
            (_("Methods"), []),
        ]
    )

    try:
        members = lookup[fullname]
    except KeyError:
        return groups

    for attr in members:
        attrlookup = f"{fullname}.{attr}"
        key = _("Attributes")
        badge = None
        label = attr
        value = None

        for base in cls.__mro__:
            value = base.__dict__.get(attr)
            if value is not None:
                break

        if value is not None:
            doc = value.__doc__ or ""
            if inspect.iscoroutinefunction(value) or doc.startswith("|coro|"):
                key = _("Methods")
                badge = attributetablebadge("async", "async")
                badge["badge-type"] = _("coroutine")
            elif isinstance(value, classmethod):
                key = _("Methods")
                label = f"{name}.{attr}"
                badge = attributetablebadge("cls", "cls")
                badge["badge-type"] = _("classmethod")
            elif inspect.isfunction(value):
                if doc.startswith(("A decorator", "A shortcut decorator", "|maybecallabledeco|")):
                    # finicky but surprisingly consistent
                    key = _("Methods")
                    badge = attributetablebadge("@", "@")
                    badge["badge-type"] = _("decorator")
                elif value.__code__ in sphinxcontrib_trio.ACM_CODES or isinstance(
                    value, contextlib.AbstractAsyncContextManager
                ):
                    key = _("Methods")
                    badge = attributetablebadge("async with", "async with")
                    badge["badge-type"] = _("async context manager")
                elif is_async_iterable(value):  # TODO traverse mro?
                    key = _("Methods")
                    badge = attributetablebadge("async for", "async for")
                    badge["badge-type"] = _("async iterable")
                else:
                    key = _("Methods")
                    badge = attributetablebadge("def", "def")
                    badge["badge-type"] = _("method")

        groups[key].append(TableElement(fullname=attrlookup, label=label, badge=badge))

    return groups


def class_results_to_node(key, elements):
    title = attributetabletitle(key, key)
    ul = nodes.bullet_list("")
    for element in elements:
        ref = nodes.reference(
            "", "", internal=True, refuri="#" + element.fullname, anchorname="", *[nodes.Text(element.label)]
        )
        para = addnodes.compact_paragraph("", "", ref)
        if element.badge is not None:
            ul.append(attributetable_item("", element.badge, para))
        else:
            ul.append(attributetable_item("", para))

    return attributetablecolumn("", title, ul)


def setup(app):
    app.add_directive("attributetable", PyAttributeTable)
    app.add_node(attributetable, html=(visit_attributetable_node, depart_attributetable_node))
    app.add_node(attributetablecolumn, html=(visit_attributetablecolumn_node, depart_attributetablecolumn_node))
    app.add_node(attributetabletitle, html=(visit_attributetabletitle_node, depart_attributetabletitle_node))
    app.add_node(attributetablebadge, html=(visit_attributetablebadge_node, depart_attributetablebadge_node))
    app.add_node(attributetable_item, html=(visit_attributetable_item_node, depart_attributetable_item_node))
    app.add_node(attributetableplaceholder)
    app.connect("doctree-resolved", process_attributetable)
