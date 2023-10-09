"""Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE"""

from __future__ import annotations

import hashlib
import os
import struct
from time import time
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from .utils import cached_slot_property

__all__ = ("Media",)

if TYPE_CHECKING:
    from collections.abc import Callable

    from _typeshed import StrOrBytesPath
    from typing_extensions import Self


@runtime_checkable
class MediaIO(Protocol):
    def seekable(self) -> bool:
        ...

    def seek(self, offset: int, whence: int = ..., /) -> Any:
        ...

    def tell(self) -> int:
        ...

    def readable(self) -> bool:
        ...

    def read(self, size: int = ..., /) -> bytes:
        ...

    def close(self) -> Any:
        ...

    def fileno(self) -> int:
        ...


class Media:
    """A wrapper around common media files. Used for :meth:`steam.User.send`.

    Parameters
    ----------
    fp
        An media or path-like to pass to :func:`open`.
    spoiler
        Whether to mark the media as a spoiler.

    Note
    ----
    Currently supported media types include:
        - PNG
        - JPG/JPEG
        - GIF
        - WEBM
        - MPG/MPEG
        - MP4
        - OGV
    """

    __slots__ = ("fp", "spoiler", "name", "width", "height", "type", "_size_cs", "_tell")
    fp: MediaIO

    def __init__(self, fp: MediaIO | StrOrBytesPath | int, *, spoiler: bool = False):
        self.fp = fp if isinstance(fp, MediaIO) else open(fp, "rb")  # noqa
        if not (self.fp.seekable() and self.fp.readable()):
            raise ValueError(f"File buffer {fp!r} must be seekable and readable")

        self._tell = self.fp.tell()

        # from https://stackoverflow.com/questions/8032642
        headers = self.fp.read(36)
        match type := next(filter(None, (test(headers) for test in tests)), None):
            case "png":
                check = struct.unpack(">i", headers[4:8])[0]
                if check != 0x0D0A1A0A:
                    raise ValueError("Opened file's headers do not match a standard PNGs headers")
                width, height = struct.unpack(">ii", headers[16:24])
            case "gif":
                width, height = struct.unpack("<HH", headers[6:10])
            case "jpeg":
                try:
                    self.fp.seek(self._tell)  # read 0xff next
                    size = self._tell + 2
                    ftype = 0
                    while not 0xC0 <= ftype <= 0xCF or ftype in {0xC4, 0xC8, 0xCC}:
                        self.fp.seek(size, 1)
                        byte = self.fp.read(1)
                        while ord(byte) == 0xFF:
                            byte = self.fp.read(1)
                        ftype = ord(byte)
                        size = struct.unpack(">H", self.fp.read(2))[0] - 2
                    # we are at a SOFn block
                    self.fp.seek(1, 1)  # skip 'precision' byte.
                    height, width = struct.unpack(">HH", self.fp.read(4))
                except Exception as exc:
                    raise ValueError from exc
            case "webm" | "mp4" | "mpeg" | "ogv":
                width, height = 0, 0
            case _:
                raise TypeError("Unsupported file format passed")
        self.type = type
        self.spoiler = spoiler
        self.width = width
        self.height = height
        self.name = f'{int(time())}_{getattr(self.fp, "name", f"media.{self.type}")}'

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.fp.close()

    def read(self) -> bytes:
        self.fp.seek(self._tell)
        read = self.fp.read()
        self.fp.seek(self._tell)
        return read

    @cached_slot_property
    def size(self) -> int:
        try:
            size = os.stat(self.fp.fileno()).st_size - self._tell  # noqa: PTH116
        except OSError:  # slow fallback
            size = len(self.fp.read())
            self.fp.seek(self._tell)
        if size > 1024 * 1024 * 10:  # 10MiB
            raise ValueError("File is too large to upload")
        return size

    @staticmethod
    def hash(contents: bytes) -> str:
        return hashlib.sha1(contents).hexdigest()


tests: list[Callable[[bytes], str | None]] = []


@tests.append
def test_jpeg(h: bytes) -> Literal["jpeg"] | None:
    if h[6:10] in {b"JFIF", b"Exif"} or h[:3] == b"\xff\xd8\xff":
        return "jpeg"


@tests.append
def test_png(h: bytes) -> Literal["png"] | None:
    if h.startswith(b"\211PNG\r\n\032\n"):
        return "png"


@tests.append
def test_gif(h: bytes) -> Literal["gif"] | None:
    if h[:6] in {b"GIF87a", b"GIF89a"}:
        return "gif"


@tests.append
def test_webm(h: bytes) -> Literal["webm"] | None:
    if h[29:36] == b"\x82\x84webmB":
        return "webm"


@tests.append
def test_mp4(h: bytes) -> Literal["mp4"] | None:
    if h[4:8] == b"ftyp":
        return "mp4"


@tests.append
def test_mpeg(h: bytes) -> Literal["mpeg"] | None:
    if h[:3] == b"\x00\x00\x01":
        return "mpeg"


@tests.append
def test_ogv(h: bytes) -> Literal["ogv"] | None:
    if h[28:34] == b"video":
        return "ogv"
