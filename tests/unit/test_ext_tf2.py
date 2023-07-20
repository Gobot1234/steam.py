from decimal import Decimal
from fractions import Fraction

import pytest

from steam.ext import tf2

client = tf2.Client()


def test_metal_initializations():
    assert tf2.Metal("0.77") == tf2.Metal(0.77)
    assert tf2.Metal(Fraction(7, 9)) == tf2.Metal(0.77)
    assert tf2.Metal(Decimal(0.77)) == tf2.Metal(0.77)
    assert tf2.Metal(Fraction(18, 9)) == tf2.Metal(2)
    assert tf2.Metal(1.00) == tf2.Metal(1)


def test_metal_addition():
    assert tf2.Metal(1.11) + tf2.Metal(1) == tf2.Metal(2.11)
    assert tf2.Metal(1.88) + tf2.Metal(1.11) == tf2.Metal(3)
    assert tf2.Metal(1.11) + tf2.Metal(1.11) == tf2.Metal(2.22)
    assert tf2.Metal(1.88) + tf2.Metal(1.88) == tf2.Metal(3.77)


def test_metal_subtraction():
    assert tf2.Metal(1.11) - tf2.Metal(1) == tf2.Metal(0.11)
    assert tf2.Metal(1.11) - tf2.Metal(0) == tf2.Metal(1.11)

    with pytest.raises(ValueError):
        _ = tf2.Metal(1) - tf2.Metal(1.11)


def test_metal_multiplication():
    assert tf2.Metal(3) * 3 == tf2.Metal(9)
    assert tf2.Metal(0) * 3 == tf2.Metal(0)

    with pytest.raises(ValueError):
        _ = tf2.Metal(3) * -1


def test_metal_invalid_values():
    with pytest.raises(ValueError):
        tf2.Metal(1.12)
    with pytest.raises(ValueError):
        tf2.Metal(1.115)
