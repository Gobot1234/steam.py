from __future__ import annotations

from pathlib import Path
from typing import Generator

import csscompressor
import htmlmin
import rjsmin
from sphinx.application import Sphinx

ROOT = Path("../../").resolve()
DOCS = ROOT / "docs"

static = DOCS / "_static"
templates = DOCS / "_templates"


def get_files(suffix: str) -> Generator[Path, None, None]:
    yield from DOCS.glob(f"**/*{suffix}")


def extract_js_script_and_minimize(code: str, start: int, end: int) -> str:
    js_code = code[start:end][len("<script>") :]
    minimized_js = rjsmin.jsmin(js_code)

    return f"{code[:start]}<script>{minimized_js}{code[end:].lstrip()}"


def minimize_html() -> None:
    html_minimizer = htmlmin.Minifier(
        remove_comments=True,
        remove_empty_space=True,
        remove_all_empty_space=True,
        reduce_boolean_attributes=True,
    )

    for file in get_files(".html"):
        text = file.read_text()
        minimized = html_minimizer.minify(text)

        position = 0

        while True:
            script_start = minimized.find("<script>\n", position)
            if script_start == -1:
                break

            position = script_end = minimized.find("</script>", script_start)
            minimized = extract_js_script_and_minimize(minimized, script_start, script_end)

        file.write_text(minimized)


def minimize_js() -> None:
    for file in get_files(".js"):
        text = file.read_text()
        minimized = rjsmin.jsmin(text, keep_bang_comments=False)

        file.write_text(minimized)


def minimize_css() -> None:
    for file in get_files(".css"):
        text = file.read_text()
        minimized = csscompressor.compress(text, preserve_exclamation_comments=False)

        file.write_text(minimized)


def minimize() -> None:
    print(list(ROOT.glob(".html")))
    minimize_html()
    minimize_js()
    minimize_css()


def setup(app: Sphinx) -> None:
    pass
