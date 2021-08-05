from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any, get_type_hints

ROOT = Path(__file__)
while ROOT.name != "steam.py":
    ROOT = ROOT.parent


def is_async_iterable(object: Any) -> bool:
    try:
        annotations = get_type_hints(object)
    except Exception:
        return False

    try:
        return issubclass(annotations.get("return"), AsyncIterable)
    except TypeError:
        return False
