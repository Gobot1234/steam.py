# fix return types

from __future__ import annotations

import re
from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Any, get_args

from sphinx.util.typing import restify

if TYPE_CHECKING:
    from sphinx.application import Sphinx

RETURN_HEADER = "Returns\n-------+\n"
RETURNS_WITH_TYPE_RE = re.compile(rf"{RETURN_HEADER}:[^:]+:`[^`]+`\n {{4}}.*", flags=re.S)  # do nothing to this
RETURNS_WITH_INFO_RE = re.compile(rf"{RETURN_HEADER}(?P<info>.+)", flags=re.S)


def add_return_type(app: Sphinx, what: str, fullname: str, object: Any, options: Any, docs: list[str]) -> None:
    if what not in {"function", "method"}:
        return

    # this part of the numpy doc spec doesn't make much sense for pep 484 and I don't want to maintain two signatures.
    doc = "\n".join(docs)
    return_type = object.__annotations__.get("return")  # full annotations should have been added by annotations.py
    if return_type in (None, "None") or "Yields" in doc or RETURNS_WITH_TYPE_RE.search(doc):
        return
    if re.search(RETURN_HEADER, doc) is not None:  # clear any previous return info
        for i in reversed(range(docs.index("Returns"), len(docs))):
            del docs[i]

    if isinstance(return_type, AsyncIterable):
        docs += (
            "Yields",
            "------",
            restify(get_args(return_type)[0]),
        )
    else:
        docs += (
            "Returns",
            "-------",
            restify(return_type),
        )
    if match := RETURNS_WITH_INFO_RE.search(doc):
        # append the info to the return type
        info = match["info"].replace("\n", " ").strip()
        docs.append(f"     {info}")


def setup(app: Sphinx) -> dict[str, bool]:
    app.connect("autodoc-process-docstring", add_return_type, priority=2)
    return {"parallel_read_safe": True}
