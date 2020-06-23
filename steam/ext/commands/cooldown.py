import time as _time
from typing import TYPE_CHECKING

from steam.enums import IntEnum
from steam.ext.commands.errors import CommandOnCooldown

if TYPE_CHECKING:
    from .context import Context


__all__ = (
    'BucketType',
    'Cooldown',
)


class BucketType(IntEnum):
    User = 1
    Member = 2
    Group = 3
    Clan = 4
    Role = 5
    Channel = 6
    Officer = 7

    def get_bucket(self, ctx: 'Context'):
        if self == self.User:
            return ctx.author.id
        if self is self.Member:
            return (ctx.clan and ctx.clan.id), ctx.author.id
        if self == self.Group:
            return (ctx.group or ctx.author).id
        if self is self.Role:
            return
        if self == self.Clan:
            return (ctx.clan or ctx.author).id
        if self == self.Channel:
            return (ctx.channel or ctx.author).id
        if self is self.Officer:
            return


class Cooldown:
    def __init__(self, rate: int, per: float, bucket):
        self._rate = rate
        self._per = per
        self.bucket = bucket
        self._last_update = 0
        self._last_called_by = []

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
