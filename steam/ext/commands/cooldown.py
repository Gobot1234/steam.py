# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2020 James

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import time as _time
from typing import TYPE_CHECKING, List, Tuple

from ...enums import IntEnum as IntEnumBase
from .errors import CommandOnCooldown

if TYPE_CHECKING:
    from enum import IntEnum

    from .context import Context


__all__ = (
    "BucketType",
    "Cooldown",
)


class BucketType(IntEnumBase):
    User: "IntEnum" = 1
    Member: "IntEnum" = 2
    Group: "IntEnum" = 3
    Clan: "IntEnum" = 4
    Role: "IntEnum" = 5
    Channel: "IntEnum" = 6
    Officer: "IntEnum" = 7

    def get_bucket(self, ctx: "Context"):
        if self == self.User:
            return ctx.author.id
        elif self is self.Member:
            return (ctx.clan and ctx.clan.id), ctx.author.id
        elif self == self.Group:
            return (ctx.group or ctx.author).id
        elif self is self.Role:
            return
        elif self == self.Clan:
            return (ctx.clan or ctx.author).id
        elif self == self.Channel:
            return (ctx.channel or ctx.author).id
        elif self is self.Officer:
            return


class Cooldown:
    def __init__(self, rate: int, per: float, bucket: BucketType):
        self._rate = rate
        self._per = per
        self.bucket = bucket
        self._last_update = 0
        self._last_called_by: List[Tuple[int, int]] = []

    def reset(self):
        self._last_update = 0
        self._last_called_by = []

    def __call__(self, bucket):
        now = _time.time()

        for (_, time) in self._last_called_by:
            if now >= time + self._per:
                self._last_called_by.pop(0)  # FIFO makes this fine

        if self._last_update + self._per >= now:
            if len(self._last_called_by) >= self._rate:
                if bucket in [b for b, n in self._last_called_by]:
                    retry_after = now - self._last_update + self._per
                    raise CommandOnCooldown(retry_after)

        self._last_called_by.append((bucket, now))
        self._last_update = _time.time()
