# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015 Rossen Georgiev <rossen@rgp.io>
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

This is an updated copy of
https://github.com/ValvePython/steam/blob/master/steam/core/msg/headers.py
"""

import struct
from typing import Optional, Union

from stringcase import snakecase

from ..enums import EResult
from ..utils import clear_proto_bit, set_proto_bit
from . import foobar, steammessages_base
from .emsg import EMsg

__all__ = (
    "MsgHdr",
    "GCMsgHdr",
    "GCMsgHdrProto",
    "ExtendedMsgHdr",
    "MsgHdrProtoBuf",
)


class MsgHdr:
    """The standard message header.

    .. container:: operations

        .. describe:: bytes(x)

            Returns the sterilised header.

    Attributes
    ----------
    msg: :class:`EMsg`
    job_id_target: :class:`int`
    job_id_source: :class:`int`
    """

    __slots__ = ("msg", "eresult", "job_name_target", "job_id_target", "job_id_source")
    SIZE = 20

    def __init__(self, data: bytes = None):
        self.msg = EMsg.Invalid
        self.eresult = EResult.Invalid
        self.job_name_target = None
        self.job_id_target = -1
        self.job_id_source = -1
        if data:
            self.parse(data)

    def __repr__(self):
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in ("msg", "job_id_target", "job_id_source")]
        return f'<MsgHdr {" ".join(resolved)}>'

    def __bytes__(self):
        return struct.pack("<Iqq", self.msg, self.job_id_target, self.job_id_source)

    def parse(self, data: bytes) -> None:
        """Parse the header.

        Parameters
        ----------
        data: :class:`bytes`
        """
        msg, self.job_id_target, self.job_id_source = struct.unpack_from("<Iqq", data)
        self.msg = EMsg(msg)


class ExtendedMsgHdr:
    """The extended standard message header.

    .. container:: operations

        .. describe:: bytes(x)

            Returns the sterilised header.

    Attributes
    ----------
    msg: :class:`EMsg`
    job_id_target: :class:`int`
    job_id_source: :class:`int`
    steam_id: :class:`str`
    session_id: :class:`int`
    header_size: :class:`int`
    header_version: :class:`int`
    header_canary: :class:`int`
    """

    __slots__ = (
        "msg",
        "steam_id",
        "session_id",
        "header_size",
        "header_version",
        "header_canary",
        "job_name_target",
        "job_id_target",
        "job_id_source",
    )
    SIZE = 36

    def __init__(self, data: bytes = None):
        self.msg = EMsg.Invalid
        self.header_size = 36
        self.header_version = 2
        self.job_name_target = None
        self.job_id_target = -1
        self.job_id_source = -1
        self.header_canary = 239
        self.steam_id = -1
        self.session_id = -1
        if data:
            self.parse(data)

    def __repr__(self):
        attrs = ("msg", "steam_id", "session_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        return f'<ExtendedMsgHdr {" ".join(resolved)}>'

    def __bytes__(self):
        return struct.pack(
            "<IBHqqBqi",
            self.msg,
            self.header_size,
            self.header_version,
            self.job_id_target,
            self.job_id_source,
            self.header_canary,
            self.steam_id,
            self.session_id,
        )

    def parse(self, data: bytes) -> None:
        """Parse the header.

        Parameters
        ----------
        data: :class:`bytes`
        """
        (
            msg,
            self.header_size,
            self.header_version,
            self.job_id_target,
            self.job_id_source,
            self.header_canary,
            self.steam_id,
            self.session_id,
        ) = struct.unpack_from("<IBHqqBqi", data)

        self.msg = EMsg(msg)

        if self.header_size != 36 or self.header_version != 2:
            raise RuntimeError("Failed to parse header")


class MsgHdrProtoBuf:
    """The message header for :class:`steam.protobufs.MsgProto` objects.

    .. container:: operations

        .. describe:: bytes(x)

            Returns the sterilised header.

    Attributes
    ----------
    msg: :class:`EMsg`
    body: :class:`protobufs.steammessages_base.CMsgProtoBufHeader`
    """

    SIZE = 8
    __slots__ = ("body", "msg", "_full_size")

    def __init__(self, data: bytes = None):
        self.msg = EMsg.Invalid
        self.body = steammessages_base.CMsgProtoBufHeader()
        self._full_size = 0

        if data:
            self.parse(data)

    def __repr__(self):
        attrs = ("msg",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(snakecase).items())
        return f'<MsgHdrProtoBuf {" ".join(resolved)}>'

    def __bytes__(self):
        proto_data = bytes(self.body)
        return struct.pack("<II", set_proto_bit(self.msg.value), len(proto_data)) + proto_data

    def parse(self, data: bytes) -> None:
        """Parse the header.

        Parameters
        ----------
        data: :class:`bytes`
        """
        msg, proto_length = struct.unpack_from("<II", data)

        self.msg = EMsg(clear_proto_bit(msg))
        self._full_size = self.SIZE + proto_length
        self.body.parse(data[self.SIZE : self._full_size])

    # allow for consistency between headers

    @property
    def session_id(self) -> int:
        return self.body.client_sessionid

    @session_id.setter
    def session_id(self, value: int):
        self.body.client_sessionid = int(value)

    @property
    def steam_id(self) -> int:
        return self.body.steamid

    @steam_id.setter
    def steam_id(self, value: int):
        self.body.steamid = int(value)

    @property
    def job_name_target(self) -> str:
        return self.body.target_job_name

    @job_name_target.setter
    def job_name_target(self, value: str) -> None:
        self.body.target_job_name = value

    @property
    def job_id_source(self) -> int:
        return int(self.body.jobid_source)

    @job_id_source.setter
    def job_id_source(self, value: int) -> None:
        self.body.jobid_source = int(value)

    @property
    def job_id_target(self) -> int:
        return int(self.body.jobid_target)

    @job_id_target.setter
    def job_id_target(self, value: int) -> None:
        self.body.jobid_target = int(value)

    @property
    def eresult(self) -> Union[EResult, int]:
        return EResult.try_value(self.body.eresult)

    @property
    def message(self) -> str:
        return self.body.error_message


class GCMsgHdr:
    __slots__ = ("msg", "body", "header_version", "target_job_id", "source_job_id")
    SIZE = 18

    def __init__(self, msg: int, data: Optional[bytes] = None):
        self.msg = clear_proto_bit(msg)
        self.body = None
        self.header_version = 1
        self.target_job_id = -1
        self.source_job_id = -1

        if data:
            self.parse(data)

    def __repr__(self):
        attrs = ("msg", "target_job_id", "source_job_id")
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(snakecase).items())
        return f'<GCMsgHdr {" ".join(resolved)}>'

    def __bytes__(self):
        return struct.pack("<Hqq", self.header_version, self.target_job_id, self.source_job_id)

    def parse(self, data):
        (
            self.header_version,
            self.target_job_id,
            self.source_job_id,
        ) = struct.unpack_from("<Hqq", data)


class GCMsgHdrProto:
    __slots__ = ("msg", "body", "header_length")
    SIZE = 8

    def __init__(self, msg: int, data: Optional[bytes] = None):
        self.msg = EMsg.try_value(clear_proto_bit(msg))
        self.body = foobar.CMsgProtoBufHeader()
        self.header_length = 0

        if data:
            self.parse(data)

    def __repr__(self):
        attrs = ("msg",)
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(snakecase).items())
        return f'<GCMsgHdrProto {" ".join(resolved)}>'

    def __bytes__(self):
        proto_data = bytes(self.body)
        self.header_length = len(proto_data)
        return struct.pack("<Ii", set_proto_bit(self.msg), self.header_length) + proto_data

    def parse(self, data: bytes) -> None:
        msg, self.header_length = struct.unpack_from("<Ii", data)

        self.msg = EMsg(clear_proto_bit(msg))

        if self.header_length:
            x = GCMsgHdrProto.SIZE
            self.body = self.body.parse(data[x : x + self.header_length])
