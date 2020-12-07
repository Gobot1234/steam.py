# -*- coding: utf-8 -*-

import pytest

import steam


@pytest.mark.parametrize("attribute", ["__version__", "version_info", "__author__"])
def test_meta(attribute: str) -> None:
    assert getattr(steam, attribute, None)
