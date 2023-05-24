# Heavily based on https://github.com/ValvePython/csgo/blob/master/csgo/sharecode.py

import itertools
import re
from collections.abc import Mapping
from functools import reduce
from typing import Final, NamedTuple, cast

CHARS = cast(
    Mapping[str, int], dict(zip("ABCDEFGHJKLMNOPQRSTUVWXYZabcdefhijkmnopqrstuvwxyz23456789", itertools.count()))
)


def _swap_endianness(number: int, ns: list[int] = list(range(0, 144, 8)), /) -> int:
    return reduce(lambda result, n: (result << 8) + ((number >> n) & 0xFF), ns, 0)


SHARE_CODE_RE: Final = re.compile(rf"^(CSGO)?(-?[{''.join(CHARS)}]{{5}}){{5}}$")


class ShareCode(NamedTuple):
    match_id: int
    outcome_id: int
    token: int


def decode_sharecode(code: str) -> ShareCode:
    """Decodes a match share code.

    Returns
    -------
    .. source:: ShareCode
    """
    if SHARE_CODE_RE.match(code) is None:
        raise ValueError("Invalid share code")

    full_code = _swap_endianness(
        reduce(
            lambda bits, char: (bits * len(CHARS)) + CHARS[char],
            code.removeprefix("CSGO-").replace("-", "")[::-1],
            0,
        )
    )

    return ShareCode(
        full_code & 0xFFFFFFFFFFFFFFFF,
        full_code >> 64 & 0xFFFFFFFFFFFFFFFF,
        full_code >> 128 & 0xFFFF,
    )
