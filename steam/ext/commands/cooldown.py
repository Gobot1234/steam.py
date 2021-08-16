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

import asyncio
import time
from typing import TYPE_CHECKING, Generic, TypeVar, Union

from ...enums import IntEnum
from .errors import CommandOnCooldown

if TYPE_CHECKING:
    from ...abc import Message, Messageable

__all__ = (
    "BucketType",
    "Cooldown",
)
T_Bucket = TypeVar("T_Bucket", "tuple[int, ...]", int)


class BucketType(IntEnum):
    """A enumeration that handles cooldowns.

    Each attribute operates on a per x basis. So :attr:`User` operates on a per :class:`~steam.User` basis.
    """

    # fmt: off
    Default = 0  #: The default :class:`BucketType` this operates on a global basis.
    User    = 1  #: The :class:`BucketType` for a :class:`steam.User`.
    Member  = 2  #: The :class:`BucketType` for a :class:`steam.User` and a :class:`steam.Clan`.
    Group   = 3  #: The :class:`BucketType` for a :class:`steam.User` in a :class:`steam.Clan` / :class:`steam.Group`.
    Clan    = 4  #: The :class:`BucketType` for a :class:`steam.Clan`.
    Role    = 5  #: The :class:`BucketType` for a :class:`steam.Role`.
    Channel = 6  #: The :class:`BucketType` for a :class:`steam.Channel`.
    Admin   = 7  #: The :class:`BucketType` for a :class:`steam.Clan`'s :attr:`steam.Clan.admins`.
    # fmt: on

    def get_bucket(self, ctx: Message | Messageable) -> int | tuple[int, ...]:
        """Get a bucket key for a message or context.

        Parameters
        ----------
        ctx
            The message or context to get the bucket for.
        """
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


class Cooldown(Generic[T_Bucket]):
    """The class that holds a command's cooldown."""

    bucket: BucketType  #: The bucket that should be used to determine this command's cooldown.

    def __init__(self, rate: int, per: float, bucket: BucketType):
        self._rate = rate
        self._per = per
        self.bucket = bucket
        self.reset()

    def reset(self) -> None:
        """Reset the command's cooldown."""
        self._queue: dict[float, T_Bucket] = {}

    def _calls(self, bucket: T_Bucket) -> list[tuple[float, T_Bucket], ...]:
        return [(t, b) for t, b in self._queue.items() if b == bucket]

    async def expire_cache(self, bucket: T_Bucket, now: float) -> None:
        self._queue[now] = bucket
        await asyncio.sleep(self._per)
        self._queue.pop(now, None)

    def get_retry_after(self, bucket: T_Bucket, now: float) -> float:
        """Get the retry after for a command.

        Parameters
        ----------
        bucket
            The bucket to find in the cache.
        now
            The UNIX timestamp to find times after.
        """
        calls = self._calls(bucket)
        if not calls:
            return 0.0
        last_call = calls[0][0]
        if last_call + self._per >= now and len(calls) >= self._rate:
            return last_call + self._per - now
        return 0.0

    def __call__(self, ctx: Message | Messageable) -> None:
        """Invoke the command's cooldown properly and raise if the command is on cooldown.

        Parameters
        ----------
        ctx
            The context for invocation to check for a cooldown on.
        """
        bucket = self.bucket.get_bucket(ctx)
        now = time.time()
        asyncio.create_task(self.expire_cache(bucket, now))
        retry_after = self.get_retry_after(bucket, now)
        if retry_after:
            raise CommandOnCooldown(retry_after)
