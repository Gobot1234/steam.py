"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""
# NB: this is the only types file that is expected to importable at runtime
#     these are internal types and user's shouldn't ever have to use them for the public API

from typing import (
    NewType as _NewType,
    SupportsIndex as _SupportsIndex,
    SupportsInt as _SupportsInt,
    TypeAlias as _TypeAlias,
)

Intable: _TypeAlias = _SupportsInt | _SupportsIndex | str | bytes  # anything int(x) wouldn't normally fail on
ID64 = _NewType("ID64", int)  # u64


AppID = _NewType("AppID", int)  # u32
ContextID = _NewType("ContextID", int)  # u64
PackageID = _NewType("PackageID", int)  # u32
BundleID = _NewType("BundleID", int)  # u32

AssetID = _NewType("AssetID", int)  # u64
ClassID = _NewType("ClassID", int)
InstanceID = _NewType("InstanceID", int)
CacheKey: _TypeAlias = tuple[ClassID, InstanceID]
TradeOfferID = _NewType("TradeOfferID", int)  # u64


class ChatGroupID(int):
    ...  # technically a u64 but we only use 32 bits for now and Steam treats it as a u32 (Group.id is a u32)


ChatID = _NewType("ChatID", int)  # u64
RoleID = _NewType("RoleID", int)  # u32


# this relationship may seem a little weird but it makes type checking easier
class ID32(ChatGroupID):  # u32
    ...


PostID = _NewType("PostID", int)  # u64
CommentID = _NewType("CommentID", int)  # u64
PublishedFileID = _NewType("PublishedFileID", int)  # u64

ManifestID = _NewType("ManifestID", int)
DepotID = _NewType("DepotID", int)

LeaderboardID = _NewType("LeaderboardID", int)
