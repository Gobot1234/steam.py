import re
from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any, get_type_hints

from sphinx.environment import BuildEnvironment

ROOT = Path(__file__)
while ROOT.name != "steam.py":
    ROOT = ROOT.parent


def is_async_iterable(object: Any) -> bool:
    try:
        annotations = get_type_hints(object)
    except Exception:
        return False

    try:
        return issubclass(annotations["return"], AsyncIterable)
    except (TypeError, KeyError):
        return False


_name_parser_regex = re.compile(r"(?P<module>[\w.]+\.)?(?P<name>\w+)")


def parse_name(content: str, env: BuildEnvironment) -> tuple[str, str]:
    match = _name_parser_regex.match(content)
    if match is None:
        raise RuntimeError(f"content {content} somehow doesn't match regex in {env.docname}.")
    path, name = match.groups()
    if path:
        modulename = path.rstrip(".")
    else:
        modulename = env.temp_data.get("autodoc:module")
        if not modulename:
            modulename = env.ref_context.get("py:module")
    if modulename is None:
        raise RuntimeError(f"modulename somehow None for {content} in {env.docname}.")

    return modulename, name
