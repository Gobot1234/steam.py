# pyright: reportUnusedExpression = false
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import given, strategies as st

from steam.ext import tf2

client = tf2.Client()
bot = tf2.Bot(command_prefix="!")


def test_metal_initializations():
    assert tf2.Metal("0.77") == tf2.Metal(0.77)
    assert tf2.Metal(Fraction(7, 9)) == tf2.Metal(0.77)
    assert tf2.Metal(Decimal(0.77)) == tf2.Metal(0.77)
    assert tf2.Metal(Fraction(18, 9)) == tf2.Metal(2)
    assert tf2.Metal(1.99) == tf2.Metal(2)


def test_metal_addition():  # TODO this can cmp against adding 2 Fractions? Decimals?
    assert tf2.Metal(1.11) + tf2.Metal(1) == tf2.Metal(2.11)
    assert tf2.Metal(1.88) + tf2.Metal(1.11) == tf2.Metal(3)
    assert tf2.Metal(1.11) + tf2.Metal(1.11) == tf2.Metal(2.22)
    assert tf2.Metal(1.88) + tf2.Metal(1.88) == tf2.Metal(3.77)
    assert tf2.Metal(1.00) + tf2.Metal(0) == tf2.Metal(1)
    # TODO test inf prec


def test_metal_subtraction():
    assert tf2.Metal(1.11) - tf2.Metal(1) == tf2.Metal(0.11)
    assert tf2.Metal(1.11) - tf2.Metal(0) == tf2.Metal(1.11)

    assert tf2.Metal(1) - tf2.Metal(1.11) == tf2.Metal(-0.11)


def test_metal_multiplication():
    assert tf2.Metal(3) * 3 == tf2.Metal(9)
    assert tf2.Metal(0) * 3 == tf2.Metal(0)

    assert tf2.Metal(3) * -1 == tf2.Metal(-3)


def test_metal_division():
    assert tf2.Metal(2) / 2 == tf2.Metal(1)
    assert tf2.Metal(2) / -2 == tf2.Metal(-1)

    with pytest.raises(ValueError):
        tf2.Metal(5) / 2
    with pytest.raises(ValueError):
        tf2.Metal(5) / -2
    with pytest.raises(ValueError):
        -tf2.Metal(5) / 2

    with pytest.raises(ZeroDivisionError):
        tf2.Metal(2) / 0


def test_metal_invalid_values():
    with pytest.raises(ValueError):
        tf2.Metal(1.12)
    with pytest.raises(ValueError):
        tf2.Metal(1.115)
    with pytest.raises(ValueError):
        tf2.Metal(Fraction(1, 10))


def test_str():
    assert str(tf2.Metal(1.22)) == "1.22"
    assert str(tf2.Metal(1.33)) == "1.33"
    assert str(tf2.Metal(1000)) == "1000.00"


# some property tests
@given(st.integers(), st.integers())
def test_ints_are_commutative(x: int, y: int):
    assert tf2.Metal(x) + tf2.Metal(y) == tf2.Metal(y) + tf2.Metal(x)


@given(x=st.integers(), y=st.integers())
def test_ints_cancel(x: int, y: int):
    assert (tf2.Metal(x) + tf2.Metal(y)) - tf2.Metal(y) == tf2.Metal(x)
