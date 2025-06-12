"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from ..._const import DOCS_BUILDING
from ..._gc import Client as Client_
from ...app import DEADLOCK
from ...ext import commands
from .models import ClientUser, PartialUser
from .state import GCState  # noqa: TCH001

if TYPE_CHECKING:
    from ...types.id import Intable
    from ...utils import cached_property
    from .models import User


__all__ = (
    "Client",
    "Bot",
)


class Client(Client_):
    """Represents a client connection that connects to Steam. This class is used to interact with the Steam API, CMs
    and the Deadlock Game Coordinator.

    :class:`Client` is a subclass of :class:`steam.Client`, so whatever you can do with :class:`steam.Client` you can
    do with :class:`Client`.
    """

    _APP: Final = DEADLOCK
    _ClientUserCls = ClientUser
    _state: GCState  # type: ignore  # PEP 705

    if TYPE_CHECKING:

        @cached_property
        def user(self) -> ClientUser: ...

    if TYPE_CHECKING or DOCS_BUILDING:

        def get_user(self, id: Intable) -> User | None: ...

        async def fetch_user(self, id: Intable) -> User: ...

    # TODO: maybe this should exist as a part of the whole lib (?)
    def instantiate_partial_user(self, id: Intable) -> PartialUser:
        return self._state.get_partial_user(id)


class Bot(commands.Bot, Client):
    """Represents a Steam bot.

    :class:`Bot` is a subclass of :class:`~steam.ext.commands.Bot`, so whatever you can do with
    :class:`~steam.ext.commands.Bot` you can do with :class:`Bot`.
    """
