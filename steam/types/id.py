"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""
# NB: this is the only types file that is expected to importable at runtime

from typing import NewType, SupportsIndex, SupportsInt

from typing_extensions import TypeAlias

Intable: TypeAlias = SupportsInt | SupportsIndex | str | bytes  # anything int(x) wouldn't normally fail on
ID64 = NewType("ID64", int)  # u64
ID32 = NewType("ID32", int)  # u32
AppID = NewType("AppID", int)  # u32

ChatGroupID: TypeAlias = int
ChannelID: TypeAlias = int
