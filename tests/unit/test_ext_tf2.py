import pytest

from steam.ext import tf2

client = tf2.Client()


def test_metal_addition():
    assert tf2.Metal(1.11) + tf2.Metal(1) == tf2.Metal(2.11)


def test_metal_invalid_values():
    with pytest.raises(ValueError):
        tf2.Metal(1.12)
    with pytest.raises(ValueError):
        tf2.Metal(1.115)
