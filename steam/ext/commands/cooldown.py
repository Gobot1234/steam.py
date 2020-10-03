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

from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING, Tuple, TypeVar, Union

from ...enums import IntEnum
from .errors import CommandOnCooldown

if TYPE_CHECKING:
    from ...message import Message
    from .context import Context


__all__ = (
    "BucketType",
    "Cooldown",
)
T_Bucket = TypeVar("T_Bucket", Tuple[int, ...], int)


class BucketType(IntEnum):
    """A enumeration that handles cooldowns.

    Each attribute operates on a per-x basis. So :attr:`User` operates on a per :class:`~steam.User` basis.
    """

    # fmt: off
    Default = 0  #: The default :class:`BucketType` this operates on a global basis.
    User    = 1  #: The :class:`BucketType` for a :class:`steam.User`.
    Member  = 2  #: The :class:`BucketType` for a :class:`steam.User`.
    Group   = 3  #: The :class:`BucketType` for a :class:`steam.User` in a :class:`steam.Clan` / :class:`steam.Group`.
    Clan    = 4  #: The :class:`BucketType` for a :class:`steam.Clan`.
    Role    = 5  #: The :class:`BucketType` for a :class:`steam.Role`.
    Channel = 6  #: The :class:`BucketType` for a :class:`steam.Channel`.
    Admin   = 7  #: The :class:`BucketType` for a :class:`steam.Clan`'s :attr:`steam.Clan.admins`.
    # fmt: on

    def get_bucket(self, message_or_context: Union[Message, Context]) -> T_Bucket:
        """Get a bucket for a message or context.

        Parameters
        ----------
        message_or_context: Union[:class:`steam.Message`, :class:`steam.ext.commands.Context`]
            The message or context to get the bucket for.

        Returns
        -------
        Union[:class:`int`, tuple[:class:`int`, ...]]
            The key for the bucket.
        """
        ctx = message_or_context
        if self == BucketType.Default:
            return 0
        elif self == BucketType.User:
            return ctx.author.id
        elif self == BucketType.Member:
            return (ctx.clan and ctx.clan.id), ctx.author.id
        elif self == BucketType.Group:
            return (ctx.group or ctx.author).id
        elif self == BucketType.Role:
            return (ctx.clan and ctx.author.top_role.id), ctx.author.id
        elif self == BucketType.Clan:
            return (ctx.clan or ctx.author).id
        elif self == BucketType.Channel:
            return (ctx.channel or ctx.author).id
        elif self == BucketType.Admin:
            return (ctx.clan and (ctx.author in ctx.clan.admins)), ctx.author.id


class Cooldown:
    def __init__(self, rate: int, per: float, bucket: BucketType):
        self._rate = rate
        self._per = per
        self.bucket = bucket
        self._last_update = 0.0
        self._last_called_by: list[tuple[T_Bucket, float]] = []

    def reset(self) -> None:
        self._last_update = 0.0
        self._last_called_by = []

    def __call__(self, message_or_context: Union[Message, Context]) -> None:
        bucket = self.bucket.get_bucket(message_or_context)
        now = _time.time()

        for _, time in self._last_called_by:
            if now >= time + self._per:
                self._last_called_by.pop(0)

        if self._last_update + self._per >= now:
            if len(self._last_called_by) >= self._rate:
                if bucket in (b for b, t in self._last_called_by):
                    retry_after = self._last_update + self._per - now
                    raise CommandOnCooldown(retry_after)

        self._last_called_by.append((bucket, now))
        self._last_update = _time.time()
