"""A nice way to work with TF2's currencies."""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from typing import TypeAlias, overload

from typing_extensions import Self

__all__ = ("Metal",)


SupportsMetal: TypeAlias = int | str | float | Fraction | Decimal


def modf(value: Decimal) -> tuple[Decimal, Decimal]:
    # can't just use divmod(value, 1) as both raise for large Decimals because lol,
    # so we need this whole song and dance
    as_tuple = value.as_tuple()
    if not isinstance(as_tuple.exponent, int):
        raise ValueError(f"invalid exponent {as_tuple.exponent!r}")

    if not as_tuple.exponent:
        integer = value
        fractional = Decimal()
    elif as_tuple.exponent < 0:
        integer = Decimal((as_tuple.sign, as_tuple.digits[: as_tuple.exponent], 0))
        fractional = Decimal((as_tuple.sign, as_tuple.digits[as_tuple.exponent :], as_tuple.exponent))
    else:
        raise AssertionError("shouldn't be reachable")

    return fractional, integer


# TODO use https://github.com/python/cpython/pull/106223 when it's merged
class Metal(Fraction):
    """A class to represent some metal in TF2.

    The value used as the denominator corresponds to one scrap metal.

    Examples
    --------

    .. code:: python

        Metal("1.22") == Metal(1.22)
        Metal(1.22) == Metal(1.22)
        Metal(1) == Metal(1.00)

    Note
    ----
    When working with large floating point numbers, it's recommended to pass a :class:`str` to avoid precision loss.
    """

    __slots__ = ()

    @overload
    def __new__(cls, value: SupportsMetal, /) -> Self:  # type: ignore
        ...

    def __new__(cls, value: SupportsMetal, /, *, _normalize: bool = ...) -> Self:
        scrap = cls.extract_scrap(value)

        if scrap < 0:
            raise ValueError(f"Metal value cannot be negative")

        return super().__new__(cls, scrap, 9)

    @classmethod
    def extract_scrap(cls, value: SupportsMetal) -> int:
        if isinstance(value, Fraction):
            if value.denominator in {9, 3, 1}:
                return value.numerator * (9 // value.denominator)
            raise ValueError("cannot convert Fraction to Metal, denominator isn't 1, 3 or 9")

        try:
            value = Decimal(value)
        except (ValueError, TypeError):
            raise TypeError("non-int passed to Metal.__new__, that could not be cast") from None

        fractional, integer = modf(value)
        if not math.isclose(fractional - round(fractional, 2), 0, abs_tol=1e-9):
            raise ValueError("metal value's last digits must be close to 0")

        digits = round(fractional, 2).as_tuple().digits
        if len(digits) >= 2 and digits[0] != digits[1]:
            raise ValueError("metal value must be a multiple of 0.11")

        return int(integer) * 9 + digits[0]

    def __add__(self, other: SupportsMetal) -> Fraction:
        scrap = Metal.extract_scrap(other)
        return Metal(Fraction(self.numerator + scrap, 9))

    def __sub__(self, other: SupportsMetal) -> Fraction:
        scrap = Metal.extract_scrap(other)
        return Metal(Fraction(self.numerator - scrap, 9))

    def __mul__(self, other: SupportsMetal) -> Fraction:
        scrap = Metal.extract_scrap(other)
        return Metal(Fraction(self.numerator * scrap, 9))

    def __div__(self, other: SupportsMetal) -> Fraction:
        scrap = Metal.extract_scrap(other)

        if self.numerator % scrap != 0:
            raise ValueError(f"{self.numerator} scrap cannot be divided by {scrap}")

        return Metal(Fraction(self.numerator // scrap, 9))

    def __str__(self) -> str:
        return f"{self.numerator // self.denominator}.{f'{(self.numerator % self.denominator) * 9 // self.denominator}' * 2}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)!r})"
