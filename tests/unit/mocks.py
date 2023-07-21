"""A collection of custom mock objects"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
from unittest.mock import MagicMock

import steam
from steam.protobufs.chat import IncomingChatMessageNotification, State
from steam.protobufs.friends import CMsgClientPersonaStateFriend

from .test_bot import bot

USER_DATA = CMsgClientPersonaStateFriend(
    friendid=1234567890,
    player_name="a user",
    avatar_hash=b"\x00" * 20,
    last_logoff=0,
    game_name="Testing steam.py",
    gameid=1337,
    persona_state=1,
)


class DataclassesMock:
    if not TYPE_CHECKING:

        def __getattribute__(self, item: Any):
            try:
                return super().__getattribute__(item)
            except AttributeError:
                if item in self.__slots__:
                    return MagicMock(name=item)
                raise


class MockUser(steam.User, DataclassesMock):
    def __init__(self):
        super().__init__(bot._state, USER_DATA)


class MockGroup(steam.Group, DataclassesMock):
    def __init__(self):
        super().__init__(bot._state, 0)
        self.name = "a group"


class MockGroupChannel(steam.GroupChannel, DataclassesMock):
    def __init__(self, group: MockGroup):
        proto = State(
            chat_id=0,
            chat_name="a group channel",
        )
        super().__init__(bot._state, group=group, proto=proto)


class MockMessage(steam.Message, DataclassesMock):
    def __init__(self, channel: MockGroupChannel, content: str | None = None):
        proto = IncomingChatMessageNotification(message=content or "a message")
        steam.Message.__init__(self, channel, proto)
        self.author = USER


class MockDMMessage(MockMessage, steam.UserMessage):
    pass


class MockClanMessage(MockMessage, steam.ClanMessage):
    pass


class MockGroupMessage(MockMessage, steam.GroupMessage):
    pass


USER = MockUser()
GROUP = MockGroup()
GROUP_CHANNEL = MockGroupChannel(GROUP)
GROUP._channels = {GROUP_CHANNEL.id: GROUP_CHANNEL}
GROUP_MESSAGE = MockGroupMessage(GROUP_CHANNEL)

TEST_COMMAND_MESSAGE = MockGroupMessage(GROUP_CHANNEL, "!test command")
