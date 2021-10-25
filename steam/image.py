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

Based on https://github.com/Rapptz/discord.py/blob/master/discord/file.py
"""

from __future__ import annotations

import hashlib
import imghdr
import io
import struct
from time import time
from typing import TYPE_CHECKING, Any

from typing_extensions import Protocol

__all__ = ("Image",)

if TYPE_CHECKING:
    from _typeshed import StrOrBytesPath


class ImageIO(Protocol):
    def seekable(self) -> bool:
        ...

    def seek(self, offset: int, whence: int = ...) -> Any:
        ...

    def tell(self) -> int:
        ...

    def readable(self) -> bool:
        ...

    def read(self, size: int = ...) -> bytes:
        ...

    def close(self) -> Any:
        ...


class Image:
    """A wrapper around common image files. Used for :meth:`steam.User.send`.

    Parameters
    ----------
    fp
        An image or path-like to pass to :func:`open`.
    spoiler
        Whether or not to mark the image as a spoiler.

    Note
    ----
    Currently supported image types include:
        - PNG
        - JPG/JPEG
        - GIF
    """

    # TODO add support for "webm", "mpg", "mp4", "mpeg", "ogv"

    __slots__ = ("fp", "spoiler", "name", "width", "height", "type", "hash", "size", "_tell")
    fp: ImageIO

    def __init__(self, fp: ImageIO | StrOrBytesPath | int, *, spoiler: bool = False):
        self.fp = fp if isinstance(fp, io.BufferedIOBase) else open(fp, "rb")
        if not (self.fp.seekable() and self.fp.readable()):
            raise ValueError(f"File buffer {fp!r} must be seekable and readable")

        self._tell = self.fp.tell()
        contents = self.read()
        self.size = len(contents)
        if self.size > 1024 * 1024 * 10:  # 10MiB
            raise ValueError("File is too large to upload")

        # from https://stackoverflow.com/questions/8032642
        headers = self.fp.read(24)
        if len(headers) != 24:
            raise ValueError("Opened file has no headers")
        self.type = imghdr.what(None, headers)
        if self.type == "png":
            check = struct.unpack(">i", headers[4:8])[0]
            if check != 0x0D0A1A0A:
                raise ValueError("Opened file's headers do not match a standard PNGs headers")
            width, height = struct.unpack(">ii", headers[16:24])
        elif self.type == "gif":
            width, height = struct.unpack("<HH", headers[6:10])
        elif self.type == "jpeg":
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
        else:
            raise TypeError("Unsupported file format passed")
        self.spoiler = spoiler
        self.width = width
        self.height = height
        self.hash = hashlib.sha1(contents).hexdigest()
        self.name = f'{int(time())}_{getattr(self.fp, "name", f"image.{self.type}")}'

    def read(self) -> bytes:
        self.fp.seek(self._tell)
        read = self.fp.read()
        self.fp.seek(self._tell)
        return read

    def __enter__(self) -> Image:
        return self

    def __exit__(self, *args: Any) -> None:
        self.fp.close()


def test_jpeg(h: bytes, _) -> str | None:  # adds support for more header types
    # SOI APP2 + ICC_PROFILE
    if h[0:4] == "\xff\xd8\xff\xe2" and h[6:17] == b"ICC_PROFILE":
        return "jpeg"
    # SOI APP14 + Adobe
    if h[0:4] == "\xff\xd8\xff\xee" and h[6:11] == b"Adobe":
        return "jpeg"
    # SOI DQT
    if h[0:4] == "\xff\xd8\xff\xdb":
        return "jpeg"


imghdr.tests.append(test_jpeg)
