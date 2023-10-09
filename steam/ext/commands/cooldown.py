"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, cast

from typing_extensions import Self

from ...chat import PartialMember
from ...enums import IntEnum
from .errors import CommandOnCooldown

if TYPE_CHECKING:
    from .context import Context

__all__ = (
    "BucketType",
    "Cooldown",
)


class BucketTypeType:
    def __new__(cls, *values: int | None) -> Self:
        return cast(Self, values)


class BucketType(IntEnum):
    """A enumeration that handles cooldowns.

    Each attribute operates on a per x basis. So :attr:`User` operates on a per :class:`~steam.User` basis.
    """

    # fmt: off
    Default   = 0
    """The default :class:`BucketType` this operates on a global basis."""
    User      = 1
    """The :class:`BucketType` for a :class:`steam.User`."""
    Member    = 2
    """The :class:`BucketType` for a :class:`steam.User` and a :class:`steam.Clan`."""
    Role      = 5
    """The :class:`BucketType` for a :class:`steam.Role`."""
    Channel   = 6
    """The :class:`BucketType` for a :class:`steam.Channel`."""
    Admin     = 7
    """The :class:`BucketType` for a :class:`steam.Clan`'s :attr:`steam.Clan.admins`."""
    ChatGroup = 8
    """The :class:`BucketType` for a :class:`steam.ChatGroup`."""
    # fmt: on

    def get_bucket(self, ctx: Context) -> BucketTypeType:
        """Get a bucket key for a message or context.

        Parameters
        ----------
        ctx
            The message or context to get the bucket for.
        """
        match self:
            case BucketType.Default:
                return BucketTypeType(0)
            case BucketType.User:
                return BucketTypeType(ctx.author.id)
            case BucketType.Member:
                if ctx.clan or ctx.group:
                    return BucketTypeType(ctx._chat_group.id64, ctx.author.id)
                return BucketTypeType(0, ctx.author.id)
            case BucketType.Role:
                assert isinstance(ctx.author, PartialMember)
                return BucketTypeType((ctx.clan and ctx.author.top_role and ctx.author.top_role.id), ctx.author.id)
            case BucketType.Channel:
                if hasattr(ctx.channel, "id"):
                    return BucketTypeType(ctx.channel.id)  # type: ignore
                return BucketTypeType(ctx.author.id)
            case BucketType.Admin:
                return BucketTypeType((ctx.clan and (ctx.author in ctx.clan.officers)), ctx.author.id)
            case BucketType.ChatGroup:
                return BucketTypeType((ctx.clan or ctx.group or ctx.author).id)


class Cooldown:
    """The class that holds a command's cooldown."""

    bucket: BucketType
    """The bucket that should be used to determine this command's cooldown."""

    def __init__(self, rate: int, per: float, bucket: BucketType):
        self._rate = rate
        self._per = per
        self.bucket = bucket
        self.reset()

    def reset(self) -> None:
        """Reset the command's cooldown."""
        self._queue: dict[float, BucketTypeType] = {}

    def _calls(self, bucket: BucketTypeType) -> list[tuple[float, BucketTypeType]]:
        return [(t, b) for t, b in self._queue.items() if b == bucket]

    async def expire_cache(self, bucket: BucketTypeType, now: float) -> None:
        self._queue[now] = bucket
        await asyncio.sleep(self._per)
        self._queue.pop(now, None)

    def get_retry_after(self, bucket: BucketTypeType, now: float) -> float:
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

    def __call__(self, ctx: Context) -> None:
        """Invoke the command's cooldown properly and raise if the command is on cooldown.

        Parameters
        ----------
        ctx
            The context for invocation to check for a cooldown on.
        """
        bucket = self.bucket.get_bucket(ctx)
        now = time.time()
        ctx._state._tg.create_task(self.expire_cache(bucket, now))
        if retry_after := self.get_retry_after(bucket, now):
            raise CommandOnCooldown(retry_after)
