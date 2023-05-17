"""A nice way to work with TF2's currencies."""

from __future__ import annotations

from fractions import Fraction
from typing import Final, SupportsRound, overload

from typing_extensions import Self

__all__ = ("Metal",)


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
    def __new__(cls, value: float | str | SupportsRound[int], /) -> Self:  # type: ignore
        ...

    def __new__(cls, value: float | str | SupportsRound[int], /, *, _normalize: bool = ...) -> Self:
        if isinstance(value, str):  # '1.22'
            value = float(value)

        self = object.__new__(cls)
        try:
            numerator = round(value, 2)
        except (ValueError, TypeError):
            raise TypeError("non-int passed to Metal.__new__, that could not be cast") from None

        stred = (
            f"{numerator:.2f}"  # TODO find a reliable way to check for random digits at the end cause they should raise
        )
        if stred[-1] != stred[-2]:
            raise ValueError("metal value must be a multiple of 0.11")

        self._numerator = round(numerator * 9)
        return self

    denominator: Final = 9  # type: ignore
    _numerator: int
    _denominator: Final = 9

    def __str__(self) -> str:
        return f"{self._numerator / 9:.2f}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)})"
