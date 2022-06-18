from __future__ import annotations

import os
from functools import partial
from pathlib import Path
from typing import Generator

import csscompressor
import htmlmin
import rjsmin
from sphinx.application import Sphinx


def get_files(output_dir, suffix: str) -> Generator[Path, None, None]:
    yield from Path(output_dir, "docs").rglob(f"*{suffix}")


def extract_js_script_and_minimize(code: str, start: int, end: int) -> str:
    js_code = code[start:end][len("<script>") :]
    minimized_js = rjsmin.jsmin(js_code)

    return f"{code[:start]}<script>{minimized_js}{code[end:].lstrip()}"


def minimize_html(output_dir: str) -> None:
    html_minimizer = htmlmin.Minifier(
        remove_comments=True,
        remove_empty_space=True,
        remove_all_empty_space=True,
        reduce_boolean_attributes=True,
    )

    for file in get_files(output_dir, ".html"):
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


def minimize_js(output_dir: str) -> None:
    for file in get_files(output_dir, ".js"):
        text = file.read_text()
        minimized = rjsmin.jsmin(text, keep_bang_comments=False)

        file.write_text(minimized)


def minimize_css(output_dir: str) -> None:
    for file in get_files(output_dir, ".css"):
        text = file.read_text()
        minimized = csscompressor.compress(text, preserve_exclamation_comments=False)

        file.write_text(minimized)


def minimize(app: Sphinx, exception: Exception, output_dir: str) -> None:
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        minimize_html(output_dir)
        minimize_js(output_dir)
        minimize_css(output_dir)


def setup(app: Sphinx) -> None:
    app.connect("build-finished", partial(minimize, output_dir=app.outdir))
