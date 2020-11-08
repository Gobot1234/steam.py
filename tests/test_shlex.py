from __future__ import annotations

import pytest

from steam.ext.commands.utils import Shlex, MissingClosingQuotation


test_strings: list[tuple[str, list[str]]] = [
    ("foo bar baz", ["foo", "bar", "baz"]),
    ('foo "bar baz"', ["foo", "bar baz"]),
    ('foo \\"bar baz', ["foo", '"bar', "baz"]),
    ('foo bar baz\\"', ["foo", "bar", 'baz"']),
    ("foo     bar       baz     ", ["foo", "bar", "baz"]),
    ("'", ["'"]),
]


def test_posix() -> None:
    for input, expected_output in test_strings:
        lex = Shlex(input)
        assert list(lex) == expected_output


def test_undo() -> None:
    for input, expected_output in test_strings:
        lex = Shlex(input)
        list(lex)
        for i in reversed(range(len(expected_output))):
            lex.undo()
            assert lex.read() == expected_output[i]
            lex.undo()
        assert list(lex) == expected_output


def test_empty() -> None:
    lex = Shlex("")
    assert not list(lex)
    lex.undo()
    assert lex.read() is None


def test_bad_quotes() -> None:
    lex = Shlex('oh no where does " end?')
    with pytest.raises(MissingClosingQuotation):
        list(lex)
