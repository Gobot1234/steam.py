"""A nice way to work with TF2's currencies."""

from __future__ import annotations

import math
from fractions import Fraction
from typing import Final, SupportsFloat, SupportsIndex, SupportsRound, TypeAlias, overload

from typing_extensions import Self

__all__ = ("Metal",)


class SupportsRoundOrFloat(SupportsRound[int], SupportsFloat):
    ...


class SupportsRoundOrIndex(SupportsRound[int], SupportsIndex):
    ...


SupportsMetal: TypeAlias = float | str | SupportsRoundOrFloat | SupportsRoundOrIndex


# TODO look into the discuss post about returning Self() in subclasses instead of concrete instances
class Metal(Fraction):
    """A class to represent some metal in TF2.

    The value used as the denominator corresponds to one scrap metal.

    Examples
    --------

    .. code:: python

        Metal("1.22") == Metal(1.22)
        Metal(1.22) == Metal(1.22)
        Metal(1) == Metal(1.00)
    """

    __slots__ = ()

    @overload
    def __new__(cls, value: SupportsMetal, /) -> Self:  # type: ignore
        ...

    def __new__(cls, value: SupportsMetal, /, *, _normalize: bool = ...) -> Self:
        if isinstance(value, str):  # '1.22'
            value = float(value)

        self = object.__new__(cls)

        try:
            true_value = round(value, 2)
        except (ValueError, TypeError):
            raise TypeError("non-int passed to Metal.__new__, that could not be cast") from None

        if not math.isclose(value, true_value):
            raise ValueError("metal value's last digits must be close to 0")

        stred = f"{true_value:.2f}"
        if stred[-1] != stred[-2]:
            raise ValueError("metal value must be a multiple of 0.11")

        self._numerator = round(true_value * 9)
        return self

    denominator: Final = 9  # type: ignore
    _numerator: int
    _denominator: Final = 9

    def __str__(self) -> str:
        return f"{self._numerator / 9:.2f}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"
