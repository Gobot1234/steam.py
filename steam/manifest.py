"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import asyncio
import errno
import logging
import lzma
import struct
import sys
from base64 import b64decode
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from operator import attrgetter, methodcaller
from typing import TYPE_CHECKING, Any, Sequence, TypeVar, overload
from zipfile import BadZipFile, ZipFile
from zlib import crc32

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from multidict import MultiDict
from typing_extensions import Final, Never, Self
from yarl import URL

from . import utils
from ._const import VDF_LOADS, VDFDict
from .abc import SteamID
from .enums import AppFlag, BillingType, DepotFileFlag, Language, LicenseType, PackageStatus, ReviewType
from .game import StatefulGame
from .models import _IOMixin
from .package import StatefulPackage
from .protobufs import app_info
from .protobufs.content_manifest import Metadata, Payload, PayloadFileMapping, PayloadFileMappingChunkData, Signature
from .utils import DateTime

if sys.platform == "win32":
    from pathlib import PureWindowsPath as PurePathBase
else:
    from pathlib import PurePosixPath as PurePathBase


if TYPE_CHECKING:
    from .state import ConnectionState
    from .types import manifest
    from .types.vdf import VDFInt


__all__ = (
    "Manifest",
    "ManifestPath",
    "Branch",
    "ManifestInfo",
    "PrivateManifestInfo",
    "HeadlessDepot",
    "Depot",
    "GameInfo",
    "PackageInfo",
)

log = logging.getLogger(__name__)
NameT = TypeVar("NameT", bound="str | None", covariant=True)


def unzip(data: bytes) -> bytes:
    if data[:2] == b"VZ":
        if data[-2:] != b"zv":
            raise RuntimeError(f"VZ: Invalid footer: {data[-2:]!r}")
        if data[2:3] != b"a":
            raise RuntimeError(f"VZ: Invalid version: {data[2:3]!r}")

        filters = (lzma._decode_filter_properties(lzma.FILTER_LZMA1, data[7:12]),)  # type: ignore
        decompressor = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=filters)
        checksum, decompressed_size = struct.unpack("<II", data[-10:-2])
        data = decompressor.decompress(data[12:-9], max_length=decompressed_size)

        if crc32(data) != checksum:
            raise RuntimeError("VZ: CRC32 checksum doesn't match for decompressed data")

    else:
        try:
            with ZipFile(BytesIO(data)) as zf:
                data = zf.read(zf.filelist[0])
        except BadZipFile:
            pass

    return data


@dataclass
class ManifestPathParents(Sequence["ManifestPath"]):
    # this class is mostly a copy and paste from pathlib.py
    __slots__ = ("path",)
    path: ManifestPath  # we don't care about reference cycles

    def __len__(self) -> int:
        if self.path.drive or self.path.root:  # this should never be True but w/e
            return len(self.path.parts) - 1
        else:
            return len(self.path.parts)

    @overload
    def __getitem__(self, idx: int) -> ManifestPath:
        ...

    @overload
    def __getitem__(self, idx: slice) -> tuple[ManifestPath, ...]:
        ...

    def __getitem__(self, idx: int | slice) -> ManifestPath | tuple[ManifestPath, ...]:
        if isinstance(idx, slice):
            return tuple(self[i] for i in range(*idx.indices(len(self))))

        if idx >= len(self) or idx < -len(self):
            raise IndexError(idx)

        return self.path._from_parsed_parts(self.path.drive, self.path.root, self.path.parts[: -idx - 1])

    def __repr__(self) -> str:
        return f"<{self.path!r}.parents>"


class ManifestPath(PurePathBase, _IOMixin):
    """A :class:`pathlib.PurePath` subclass representing a binary file in a Manifest. This class is broadly compatible
    with :class:`pathlib.Path`.

    .. container:: operations

        .. describe:: x == y

            Checks if two paths are equal.

        .. describe:: hash(x)

            Hashes this path.

        .. describe:: x < y

            Checks if one path is less than the other.
    """

    __slots__ = ("_manifest", "_mapping", "_flags_cs")

    _manifest: Manifest
    _mapping: PayloadFileMapping

    def __new__(cls, manifest: Manifest, mapping: PayloadFileMapping) -> Self:
        # super().__new__ breaks
        self: Self = super()._from_parts(mapping.filename.rstrip("\x00 \n\t").split("\\"))  # type: ignore
        self._mapping = mapping
        self._manifest = manifest
        return self

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {str(self)!r}>"

    if not TYPE_CHECKING:

        def __getattr__(self, name: str) -> Never:
            if name in self.__annotations__:  # give a more helpful error
                raise AttributeError("Attempting operations on a non-existent file")
            raise AttributeError(f"{self.__class__.__name__!r} object has no attribute {name!r}")

    def _select_from_manifest(self, new_self: Self) -> Self:
        try:
            # try and return the actual path if exists
            return self._manifest._paths[new_self.parts]
        except KeyError:
            # else attach the manifest and return, this will not support most operations
            new_self._manifest = self._manifest
            return new_self

    def _from_parts(self, args: tuple[str, ...]) -> Self:
        new_self = super()._from_parts(args)  # type: ignore
        return self._select_from_manifest(new_self)

    def _from_parsed_parts(self, drv: str, root: str, parts: tuple[str, ...]) -> Self:
        new_self = super()._from_parsed_parts(drv, root, parts)  # type: ignore
        return self._select_from_manifest(new_self)

    @property
    def parents(self) -> ManifestPathParents:
        # cannot use the default implementation as it calls _from_parsed_parts as a classmethod
        return ManifestPathParents(self)

    @property
    def size(self) -> int:
        """This path's size in bytes."""
        return self._mapping.size

    @property
    def chunks(self) -> Sequence[PayloadFileMappingChunkData]:
        """A read-only version of this path's chunks instances."""
        return self._mapping.chunks

    @utils.cached_slot_property
    def flags(self) -> DepotFileFlag:
        """This path's flags."""
        return DepotFileFlag.try_value(self._mapping.flags)

    def is_dir(self) -> bool:
        """Whether the path is a directory."""
        return self.flags & DepotFileFlag.Directory > 0

    def is_symlink(self) -> bool:
        """Whether this path is a symlink."""
        return self.flags & DepotFileFlag.Symlink > 0

    def is_file(self) -> bool:
        """Whether this path is a file or symlink."""
        return not self.is_dir()

    def is_executable(self) -> bool:
        """Whether this file is executable."""
        return self.flags & DepotFileFlag.Executable > 0

    def is_hidden(self) -> bool:
        """Whether this file is hidden."""
        return self.flags & DepotFileFlag.Hidden > 0

    def readlink(self) -> Self:
        """If this path is a symlink where it points to. Similar to :meth:`pathlib.Path.readlink`

        Raises
        ------
        OSError
            this path isn't a symlink.
        """
        if not self.is_symlink():
            raise OSError(errno.EINVAL, f"Invalid argument: {str(self)!r}")

        link_parts = tuple(self._mapping.linktarget.rstrip("\x00 \n\t").split("\\"))
        return self._manifest._paths[link_parts]

    def iterdir(self) -> Generator[Self, None, None]:
        """Iterate over this path. Similar to :meth:`pathlib.Path.iterdir`."""
        for path in self._manifest._paths.values():
            if path.parent == self:
                yield path

    def glob(self, pattern: str) -> Generator[Self, None, None]:
        """Perform a glob operation on this path. Similar to :meth:`pathlib.Path.glob`."""
        if not pattern:
            raise ValueError(f"Unacceptable pattern: {pattern!r}")

        # str.removeprefix
        yield from filter(
            methodcaller("match", f"{self.as_posix().rstrip('/')}/{pattern}"), self._manifest._paths.values()
        )

    def rglob(self, pattern: str) -> Generator[Self, None, None]:
        """Perform a recursive glob operation on this path. Similar to :meth:`pathlib.Path.rglob`."""
        yield from self.glob(f"**/{pattern}")

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[BytesIO, None]:
        """Reads the entire contents of the file into a :class:`io.BytesIO` object.

        Raises
        ------
        IsADirectoryError
            This path is a directory and cannot be opened.
        RuntimeError
            The depot cannot be decrypted as no key for its manifest was found.
        """
        if self.is_dir():
            raise IsADirectoryError(errno.EISDIR, f"Is a directory: {str(self)!r}")

        key = self._manifest._key
        if key is None:
            raise RuntimeError("Cannot decrypt this depot as we have no key.")

        with BytesIO() as buffer:
            for resp in await asyncio.gather(
                *(
                    self._manifest.server.get(f"depot/{self._manifest.depot_id}/chunk/{chunk.sha.hex()}")
                    for chunk in self.chunks
                )
            ):
                data = utils.symmetric_decrypt(resp, key)
                buffer.write(unzip(data))

            buffer.seek(0)
            yield buffer

    read_bytes = _IOMixin.read
    """Read the contents of the file. Similar to :meth:`pathlib.Path.read_bytes`"""

    async def read(self) -> Never:
        raise NotImplementedError("use read_bytes() instead of read()")

    async def read_text(self, encoding: str | None = None) -> str:
        """Read the contents of the file. Similar to :meth:`pathlib.Path.read_text`"""
        contents = await self.read_bytes()
        return contents.decode() if encoding is None else contents.decode(encoding)

    async def read_vdf(self, encoding: str | None = None) -> VDFDict:
        """Read the contents of the file into a VDFDict."""
        return VDF_LOADS(await self.read_text(encoding))


PAYLOAD_MAGIC: Final = 0x71F617D0
METADATA_MAGIC: Final = 0x1F4812BE
SIGNATURE_MAGIC: Final = 0x1B81B817
END_OF_MANIFEST_MAGIC: Final = 0x32C415AB


class Manifest:
    """Represents a manifest which is a collection of files included with a depot build on Steam's CDN.

    .. container:: operations

        .. describe:: x == y

            Checks if two manifests are equal.

        .. describe:: len(x)

            Returns the number of files this manifest holds.

    Attributes
    ----------
    name
        The name of the manifest.
    game
        The game that this manifest was fetched from.
    created_at
        The time at which the depot was created at.
    """

    __slots__ = (
        "name",
        "game",
        "server",
        "created_at",
        "_key",
        "_metadata",
        "_payload",
        "_signature",
        "_paths",
        "_state",
    )

    def __init__(self, state: ConnectionState, server: ContentServer, game_id: int, data: bytes):
        self._state = state
        self.name: str | None = None
        self.game = StatefulGame(state, id=game_id)
        self.server = server
        self._key: bytes | None = None
        self._paths: dict[tuple[str, ...], ManifestPath] = {}

        with utils.StructIO(unzip(data)) as io:
            if io.read_u32() != PAYLOAD_MAGIC:
                raise RuntimeError("Expecting protobuf payload")
            length = io.read_u32()
            self._payload = Payload().parse(io.read(length))

            if io.read_u32() != METADATA_MAGIC:
                raise RuntimeError("Expecting protobuf metadata")
            length = io.read_u32()
            self._metadata = Metadata().parse(io.read(length))

            if io.read_u32() != SIGNATURE_MAGIC:
                raise RuntimeError("Expecting protobuf signature")
            length = io.read_u32()
            self._signature = Signature().parse(io.read(length))

            if io.read_u32() != END_OF_MANIFEST_MAGIC:
                raise RuntimeError("Expecting end of manifest")

        self.created_at = DateTime.from_timestamp(self._metadata.creation_time)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id} depot_id={self.depot_id}>"

    def __eq__(self, other: object) -> bool:
        return self.id == other.id if isinstance(other, self.__class__) else NotImplemented

    def __len__(self) -> int:
        return len(self._payload.mappings)

    @property
    def paths(self) -> Sequence[ManifestPath]:
        """The depot's files."""
        if self._paths:
            return list(self._paths.values())

        paths = self._paths
        for mapping in self._payload.mappings:
            path = ManifestPath(self, mapping)
            self._paths[path.parts] = path
        return list(paths.values())

    @property
    def id(self) -> int:
        """The ID of this manifest. This is randomly generated by Steam."""
        return self._metadata.gid_manifest

    @property
    def depot_id(self) -> int:
        """The ID of this manifest's depot."""
        return self._metadata.depot_id

    @property
    def size_original(self) -> int:
        """The size of the original depot file."""
        return self._metadata.cb_disk_original

    @property
    def size_compressed(self) -> int:
        """The size of the compressed depot file."""
        return self._metadata.cb_disk_compressed

    @property
    def compressed(self) -> bool:
        """Whether the depot is compressed."""
        return self.size_original != self.size_compressed if self.size_compressed else False


@dataclass
class ContentServer(SteamID):  # is there any point having this inherit steamid?
    _state: ConnectionState
    url: URL
    weighted_load: float

    async def get(self, path: str) -> bytes:
        async with self._state.http._session.get(self.url / path) as r:
            return await r.read()

    async def fetch_manifest(
        self,
        game_id: int,
        id: int,
        depot_id: int,
        name: str | None = None,
        branch: str = "public",
        password_hash: str = "",
    ) -> Manifest:
        branch = branch if branch != "public" else ""
        code = await self._state.fetch_manifest_request_code(id, depot_id, game_id, branch, password_hash)
        data = await self.get(f"depot/{depot_id}/manifest/{id}/5{f'/{code}' if code else ''}")

        manifest = Manifest(self._state, self, game_id, data)
        encrypted = manifest._metadata.filenames_encrypted
        if encrypted:
            key = manifest._key = await self._state.fetch_depot_key(game_id, depot_id)
        for mapping in manifest._payload.mappings:
            if encrypted:
                mapping.filename = utils.symmetric_decrypt(b64decode(mapping.filename), key).decode()  # type: ignore # key is never unbound
                if mapping.linktarget:
                    mapping.linktarget = utils.symmetric_decrypt(b64decode(mapping.linktarget), key).decode()  # type: ignore

            mapping.chunks.sort(key=attrgetter("offset"), reverse=False)

        manifest.name = name
        return manifest


class Branch:
    """Represents a branch on for a Steam app. Branches are specific builds of an application that have made available
    publicly or privately through Steam.

    Read more on `steamworks <https://partner.steamgames.com/doc/store/application/branches>`_.

    Attributes
    ----------
    name
        The name of the branch.
    build_id
        The branch's build ID. This is a globally incrementing number. Build IDs are updated when a new build of an
        application is pushed.
    password_required
        Whether a password is required to access this branch.
    updated_at
        The time this branch was last updated. This can be ``None`` if the branch is ancient and hasn't been updated
        in ages.
    description
        This branch's description.
    depots
        This branch's depots.
    password
        This branch's password.
    """

    __slots__ = (
        "name",
        "build_id",
        "password_required",
        "updated_at",
        "description",
        "depots",
        "password",
    )

    def __init__(
        self,
        name: str,
        build_id: int,
        updated_at: datetime | None,
        password_required: bool,
        description: str | None,
    ):
        self.name = name
        self.build_id = build_id
        self.password_required = password_required
        self.updated_at = updated_at
        self.description = description
        self.depots: list[Depot] = []
        self.password: str | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} build_id={self.build_id}>"

    @property
    def manifests(self) -> list[ManifestInfo]:
        """This branch's manifests."""
        return [depot.manifest for depot in self.depots]

    async def fetch_manifests(self) -> list[Manifest]:
        """Fetch this branch's manifests. Similar to :meth:`StatefulGame.manifests`."""
        return await asyncio.gather(*(manifest.fetch() for manifest in self.manifests))  # type: ignore  # typeshed lies


class ManifestInfo:
    """Represents information about a manifest.

    Attributes
    ----------
    id
        The manifest's ID.
    branch
        The branch this manifest is for.
    depot
        The depot this manifest is for.
    """

    __slots__ = ("_state", "id", "branch", "depot")
    depot: Depot

    def __init__(
        self,
        state: ConnectionState,
        id: int,
        branch: Branch,
    ):
        self._state = state
        self.id = id
        self.branch = branch

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id}>"

    @property
    def name(self) -> str | None:
        """The manifest's name."""
        return self.depot.name

    async def fetch(self) -> Manifest:
        """Resolves this manifest info into a full :class:`Manifest`."""
        return await self._state.fetch_manifest(self.depot.game.id, self.id, self.depot.id, self.name)


class PrivateManifestInfo(ManifestInfo):
    __slots__ = ("encrypted_id",)

    def __init__(self, state: ConnectionState, encrypted_id: str, branch: Branch):
        self._state = state
        self.encrypted_id = encrypted_id
        self.branch = branch

    @property
    def id(self) -> int:
        if self.branch.password is None:
            raise ValueError("Cannot access the id of this depot as the password is not set.")
        cipher = Cipher(algorithms.AES(self.branch.password.encode("UTF-8")), modes.ECB())
        decryptor = cipher.decryptor()
        to_unpack = utils.unpad(decryptor.update(bytes.fromhex(self.encrypted_id) + decryptor.finalize()))
        return struct.unpack("<Q", to_unpack)[0]

    @staticmethod
    def _get_id(depots: manifest.Depot, branch: Branch) -> VDFInt | None:
        try:
            return depots["encryptedmanifests"][branch.name]["encrypted_gid_2"]
        except KeyError:
            return None


@dataclass
class HeadlessDepot:
    """Represents a depot without a branch."""

    __slots__ = ("id", "name", "game", "max_size", "config", "shared_install", "system_defined")
    id: int
    """The depot's ID."""
    name: str
    """The depot's name."""
    game: GameInfo
    """The depot's game."""
    max_size: int
    """The depot's maximum size."""
    config: MultiDict[str]
    """The depot's configuration settings."""
    shared_install: bool
    """Whether this depot supports shared installs"""
    system_defined: bool
    """Whether this depot is system defined."""

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} id={self.id} game={self.game!r}>"

    def __eq__(self, other: object) -> bool:
        return self.id == other.id if isinstance(other, self.__class__) else NotImplemented


@dataclass
class Depot(HeadlessDepot):
    """Represents a depot which is a grouping of files.

    Read more on `steamworks <https://partner.steamgames.com/doc/store/application/depots>`_.
    """

    __slots__ = ("manifest", "branch")
    manifest: ManifestInfo
    """The depot's associated manifest."""
    branch: Branch
    """The branch the depot is for."""


class ProductInfo:
    __slots__ = ()
    _state: ConnectionState
    sha: str
    size: int
    change_number: int

    def __init__(
        self,
        state: ConnectionState,
        proto: (
            app_info.CMsgClientPicsProductInfoResponseAppInfo | app_info.CMsgClientPicsProductInfoResponsePackageInfo
        ),
        **kwargs: Any,
    ):
        super().__init__(state, **kwargs)  # type: ignore  # this is a mixin
        self.sha = proto.sha.hex()
        self.size = proto.size
        self.change_number = proto.change_number

    # async def changes(self) -> ...:
    #     """A method to fetch the changes to this game since this change number"""
    #     changes = await self._state.fetch_changes_since(self.change_number, True, True)
    #     return changes.app_changes[0].change_number


class GameInfo(ProductInfo, StatefulGame):
    """Represents a collection of information on a game.

    Attributes
    ----------
    type
        The game's type.
    has_adult_content
        Whether this game has adult content according to Steam.
    has_adult_content_violence
        Whether this game has adult violence according to Steam.
    market_presence
        Whether this game has a market presence.
    workshop_visible
        Whether this game has a market presence.
    community_hub_visible
        Whether this game has a content hub visible.
    controller_support
        This game's level of controller support.
    publishers
        This game's publishers.
    developers
        This game's developers.
    supported_languages
        This game's supported languages.
    created_at
        The time this game was created.
    review_score
        This game's review score.
    review_percentage
        This game's review percentage.
    partial_dlc
        This game's downloadable content.
    icon_url
        This game's icon URL.
    logo_url
        This game's logo URL.
    website_url
        This game's URL.
    headless_depots
        The depots for this game without a branch.
    sha
        The game's SHA for this product info.
    size
        The product info's size.
    change_number
        The product info's change number.
    """

    __slots__ = (
        "sha",
        "size",
        "change_number",
        "_branches",
        "headless_depots",
        "type",
        "has_adult_content",
        "has_adult_content_violence",
        "market_presence",
        "workshop_visible",
        "community_hub_visible",
        "controller_support",
        "publishers",
        "developers",
        "supported_languages",
        "created_at",
        "review_score",
        "review_percentage",
        "partial_dlc",
        "icon_url",
        "logo_url",
        "website_url",
        "parent",
        "_stats_visible",
        "_free",
        "_on_windows",
        "_on_mac_os",
        "_on_linux",
    )
    name: str

    def __init__(
        self,
        state: ConnectionState,
        data: manifest.GameInfo,
        proto: app_info.CMsgClientPicsProductInfoResponseAppInfo,
    ):
        common = data["common"]
        extended = data.get("extended", {})
        super().__init__(state, proto, id=proto.appid, name=common["name"])
        self.type = AppFlag.from_str(common["type"])
        self.has_adult_content = common.get("has_adult_content", "0") == "1"
        self.has_adult_content_violence = common.get("has_adult_content_violence", "0") == "1"
        self.market_presence = common.get("market_presence", "0") == "1"
        self.workshop_visible = common.get("workshop_visible", "0") == "1"
        self.community_hub_visible = common.get("community_hub_visible", "0") == "1"
        self._stats_visible = common.get("community_visible_stats", "0") == "1"
        self._free = extended.get("isfreeapp", "0") == "1"

        self.controller_support = common.get("controller_support", "none")

        self.publishers: list[str] = [
            publisher["name"]
            for publisher in common.get("associations", {}).values()
            if publisher["type"] == "publisher"
        ]
        self.developers: list[str] = [
            developer["name"]
            for developer in common.get("associations", {}).values()
            if developer["type"] == "developer"
        ]
        self.supported_languages: list[Language] = [
            Language.from_str(language) for language, value in common.get("languages", {}).items() if value == "1"
        ]

        # TODO categories/genres
        self.created_at = (
            DateTime.from_timestamp(int(common["steam_release_date"])) if "steam_release_date" in common else None
        )
        self.review_score = ReviewType.try_value(int(common.get("review_score", 0)))
        self.review_percentage = int(common.get("review_percentage", 0))
        dlc = extended.get("listofdlc", "")
        self.partial_dlc = [StatefulGame(state, id=int(id)) for id in dlc.split(",")] if dlc else []

        os_list = common.get("oslist", "")
        self._on_windows = "windows" in os_list
        self._on_mac_os = "macos" in os_list
        self._on_linux = "linux" in os_list

        self.icon_url = (
            f"https://media.steampowered.com/steamcommunity/public/images/apps/{self.id}/{common['icon']}.jpg"
            if "icon" in common
            else None
        )
        self.logo_url = (
            f"https://media.steampowered.com/steamcommunity/public/images/apps/{self.id}/{common['logo']}.jpg"
            if "logo" in common
            else None
        )
        self.website_url = extended.get("homepage")
        self.parent = StatefulGame(state, id=int(common["parent"])) if "parent" in common else None

        depots: manifest.Depot = data.get("depots", {})  # type: ignore
        self._branches: dict[str, Branch] = {}

        for name, value in depots.get("branches", {}).items():
            try:
                build_id = int(value["buildid"])
            except KeyError:
                log.debug("Got a branch %s with no build id, discarding", name)
            else:
                self._branches[name] = Branch(
                    name=name,
                    build_id=build_id,
                    updated_at=DateTime.from_timestamp(int(value["timeupdated"])) if "timeupdated" in value else None,
                    password_required=bool(int(value.get("pwdrequired", False))),
                    description=value.get("description") or None,
                )
        self.headless_depots: Sequence[HeadlessDepot] = []

        for key, depot in depots.items():  # type: ignore
            try:
                id = int(key)
            except ValueError:
                continue
            else:  # only the int keys have VDFDicts
                depot: manifest.Depot
                kwargs = {
                    "id": id,
                    "name": depot.get("name"),
                    "config": depot.get("config", MultiDict()),
                    "max_size": int(depot["maxsize"]) if "maxsize" in depot else None,
                    "game": self,
                    "shared_install": bool(int(depot.get("sharedinstall", False))),
                    "system_defined": bool(int(depot.get("system_defined", False))),
                }
                try:
                    manifests = depot["manifests"]
                except KeyError:
                    self.headless_depots.append(HeadlessDepot(**kwargs))  # type: ignore
                else:
                    for branch_name, manifest_id in manifests.items():
                        branch = self._branches[branch_name]
                        if not branch.password_required:
                            manifest = ManifestInfo(state, int(manifest_id), branch=branch)
                        else:
                            encrypted_id = PrivateManifestInfo._get_id(depot, branch)
                            if encrypted_id is not None:
                                manifest = PrivateManifestInfo(state, encrypted_id, branch)
                            else:  # fall back to the public version
                                manifest = ManifestInfo(
                                    state,
                                    int(manifests["public"]),
                                    branch=self.public_branch,
                                )
                        depot_ = Depot(**kwargs, branch=branch, manifest=manifest)  # type: ignore
                        manifest.depot = depot_
                        branch.depots.append(depot_)

    def get_branch(self, name: str) -> Branch | None:
        """Get a branch by its name."""
        return self._branches.get(name)

    @property
    def branches(self) -> Sequence[Branch]:
        """The branches for this game."""
        return list(self._branches.values())

    @property
    def public_branch(self) -> Branch:
        """The public branch. Shorthand for:

        .. code-block:: python3

            game.get_branch("public")
        """
        return self._branches["public"]

    async def depots(self) -> Sequence[Depot | HeadlessDepot]:
        return [depot for branch in self._branches.values() for depot in branch.depots] + self.headless_depots  # type: ignore

    def is_on_windows(self) -> bool:
        """Whether the game is playable on Windows."""
        return self._on_windows

    def is_on_mac_os(self) -> bool:
        """Whether the game is playable on macOS."""
        return self._on_mac_os

    def is_on_linux(self) -> bool:
        """Whether the game is playable on Linux."""
        return self._on_linux

    def has_visible_stats(self) -> bool:
        """Whether the game has publicly visible stats."""
        return self._stats_visible

    def is_free(self) -> bool:
        """Whether the game is free to download."""
        return self._free

    def __repr__(self) -> str:
        attrs = ("name", "id", "type", "sha", "change_number")
        resolved = [f"{name}={getattr(self, name)!r}" for name in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"


class PackageInfo(ProductInfo, StatefulPackage):
    """Represents a collection of information on a package.

    Attributes
    ----------
    games
        The games included in the package.
    billing_type
        The billing type for the package.
    license_type
        The license type for the package.
    status
        The status for the package.
    depot_ids
        The depot IDs in of the depots in the package.
    app_items
        The app items in the package.
    """

    __slots__ = (
        "sha",
        "size",
        "change_number",
        "_games",
        "billing_type",
        "license_type",
        "status",
        "depot_ids",
        "app_items",
    )

    def __init__(
        self,
        state: ConnectionState,
        data: manifest.PackageInfo,
        proto: app_info.CMsgClientPicsProductInfoResponsePackageInfo,
    ):
        super().__init__(state, proto, id=proto.packageid)
        self._games = [StatefulGame(state, id=id) for id in data["appids"].values()]
        self.billing_type = BillingType.try_value(data["billingtype"])
        self.license_type = LicenseType.try_value(data["licensetype"])
        self.status = PackageStatus.try_value(data["status"])
        self.depot_ids = list(data["depotids"].values())
        self.app_items = list(data["appitems"].values())

    def __repr__(self) -> str:
        attrs = ("id", "sha", "change_number")
        resolved = [f"{name}={getattr(self, name)!r}" for name in attrs]
        return f"<{self.__class__.__name__} {' '.join(resolved)}>"

    async def games(self) -> list[StatefulGame]:
        return self._games
