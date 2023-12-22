# pyright: reportIncompatibleMethodOverride = none
"""A nice way to work with TF2's currencies."""

from __future__ import annotations

import math
from decimal import Decimal
from fractions import Fraction
from functools import reduce
from typing import TYPE_CHECKING, TypeAlias, overload

if TYPE_CHECKING:
    from collections.abc import Iterable

    from typing_extensions import Self

    from ...trade import Item


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
        fractional = Decimal().copy_sign(value)
    elif as_tuple.exponent < 0:
        integer = Decimal((as_tuple.sign, as_tuple.digits[: as_tuple.exponent], 0))
        fractional = Decimal((as_tuple.sign, as_tuple.digits[as_tuple.exponent :], as_tuple.exponent))
    else:
        raise AssertionError("shouldn't be reachable")  # you get rounding issues here either way

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

    def __new__(cls, value: SupportsMetal, /, *, _normalize: bool = True) -> Self:
        return super().__new__(cls, cls.extract_scrap(value), 9)

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
        rounded_fractional = round(fractional, 2)
        if not math.isclose(fractional - rounded_fractional, 0, abs_tol=1e-9):
            raise ValueError("metal value's last digits must be close to 0")

        digits = rounded_fractional.as_tuple().digits
        if len(digits) >= 2 and digits[0] != digits[1]:
            raise ValueError("metal value must be a multiple of 0.11")

        return int(integer) * 9 + (digits[0] if fractional >= 0 else -digits[0])

    def __add__(self, other: SupportsMetal) -> Metal:
        return Metal(super().__add__(Fraction(self.extract_scrap(other), 9)))

    def __sub__(self, other: SupportsMetal) -> Metal:
        return Metal(super().__sub__(Fraction(self.extract_scrap(other), 9)))

    def __mul__(self, other: SupportsMetal) -> Metal:
        return Metal(super().__mul__(Fraction(self.extract_scrap(other), 9)))

    def __truediv__(self, other: SupportsMetal) -> Metal:
        return Metal(super().__truediv__(Fraction(self.extract_scrap(other), 9)))

    __radd__ = __add__  # type: ignore
    __rsub__ = __sub__  # type: ignore
    __rmul__ = __mul__  # type: ignore
    __rtruediv__ = __truediv__  # type: ignore

    def __abs__(self) -> Metal:
        return Metal(super().__abs__())

    def __pos__(self) -> Metal:
        return Metal(super().__pos__())

    def __neg__(self) -> Metal:
        return Metal(super().__neg__())

    def __str__(self) -> str:
        return (
            f"{self.numerator // self.denominator}"
            "."
            f"{f'{(self.numerator % self.denominator) * 9 // self.denominator}' * 2}"
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({str(self)!r})"

    @classmethod
    def from_items(cls, items: Iterable[Item]) -> Metal:
        """The amount of metal in the items.

        Example
        -------

        .. code:: py

            their_inventory = await user.inventory(steam.TF2)
            their_metal = Metal.from_items(their_inventory)
            our_inventory = await client.user.inventory(steam.TF2)
            await user.send(f"I have {'more' if our_inventory.metal > their_metal else 'less'} metal than you")
        """
        return reduce(cls.__add__, (ITEM_VALUES[item.name] for item in items if item.name in ITEM_VALUES))


ITEM_VALUES = {
    "Refined Metal": Metal(1.00),
    "Reclaimed Metal": Metal(0.33),
    "Scrap Metal": Metal(0.11),
}
