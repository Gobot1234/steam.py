from __future__ import annotations

import pytest

from steam.ext.commands.utils import MissingClosingQuotation, Shlex

test_strings = [
    ("foo bar baz", ["foo", "bar", "baz"]),
    ('foo "bar baz"', ["foo", "bar baz"]),
    ('foo \\"bar baz', ["foo", '"bar', "baz"]),
    ('foo bar baz\\"', ["foo", "bar", 'baz"']),
    ("foo     bar       baz     ", ["foo", "bar", "baz"]),
    ("'", ["'"]),
]


@pytest.mark.parametrize("input, expected_output", test_strings)
def test_posix(input: str, expected_output: list[str]) -> None:
    lex = Shlex(input)
    assert list(lex) == expected_output


@pytest.mark.parametrize("input, expected_output", test_strings)
def test_undo(input: str, expected_output: list[str]) -> None:
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
