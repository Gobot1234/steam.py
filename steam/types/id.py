"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""
# NB: this is the only types file that is expected to importable at runtime
#     these are internal types and user's shouldn't ever have to use them for the public API

from typing import NewType, SupportsIndex, SupportsInt

from typing_extensions import TypeAlias

Intable: TypeAlias = SupportsInt | SupportsIndex | str | bytes  # anything int(x) wouldn't normally fail on
ID64 = NewType("ID64", int)  # u64


AppID = NewType("AppID", int)  # u32
ContextID = NewType("ContextID", int)  # u64
PackageID = NewType("PackageID", int)  # u32
BundleID = NewType("BundleID", int)  # u32

AssetID = NewType("AssetID", int)  # u64
ClassID = NewType("ClassID", int)
InstanceID = NewType("InstanceID", int)
CacheKey: TypeAlias = tuple[ClassID, InstanceID]


class ChatGroupID(int):
    ...  # technically a u64 but we only use 32 bits for now and Steam treats it as a u32 (Group.id is a u32)


ChatID = NewType("ChatID", int)  # u64


# this relationship may seem a little weird but it makes type checking easier
class ID32(ChatGroupID):  # u32
    ...
