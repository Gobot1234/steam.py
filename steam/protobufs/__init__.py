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

This is an updated version of https://github.com/ValvePython/steam/tree/master/steam/core/msg
"""

from __future__ import annotations

import dataclasses
from typing import Any, Generic, Optional, Type, TypeVar, Union

import betterproto

from ..enums import Enum
from .emsg import *
from .headers import *
from .protobufs import *
from .unified import *

T = TypeVar("T", bound=betterproto.Message)
AllowedHeaders = (ExtendedMsgHdr, MsgHdrProtoBuf)
GetProtoType = Optional[Type[betterproto.Message]]


def _Message__bool__(self: betterproto.Message) -> bool:
    return any(getattr(self, field.name) for field in dataclasses.fields(self))


betterproto.Message.__bool__ = _Message__bool__


def get_cmsg(emsg: Union[EMsg, int]) -> GetProtoType:
    """Get a protobuf from its EMsg.

    Parameters
    ----------
    emsg: Union[:class:`EMsg`, :class:`int`]
        The EMsg of the protobuf.

    Returns
    -------
    Optional[type[:class:`betterproto.Message`]]
        The uninitialized protobuf.
    """
    return PROTOBUFS.get(EMsg.try_value(emsg))


def get_um(name: str) -> GetProtoType:
    """Get the protobuf for a certain Unified Message.

    Parameters
    ----------
    name: :class:`str`
        The name of the UM.

    Returns
    -------
    Optional[type[:class:`betterproto.Message`]]
        The uninitialized protobuf.
    """
    return UMS.get(name)


class MsgBase(Generic[T]):
    __slots__ = ("header", "body", "payload", "skip")

    def __init__(self, msg: EMsg, data: Optional[bytes], **kwargs: Any):
        self.msg = msg
        self.body: Optional[T] = None
        self.payload: Optional[bytes] = data[self.skip :] if data else None

        self.parse()
        if kwargs:
            for key, value in kwargs.items():
                if isinstance(value, Enum):
                    kwargs[key] = value.value
            if self.body is not None:
                self.body.from_dict(kwargs)

    def __repr__(self) -> str:
        attrs = (
            "msg",
            "header",
        )
        resolved = [f"{attr}={getattr(self, attr)!r}" for attr in attrs]
        if isinstance(self.body, betterproto.Message):
            resolved.extend(f"{k}={v!r}" for k, v in self.body.to_dict(betterproto.Casing.SNAKE).items())
        else:
            resolved.append("body='!!! Failed To Parse !!!'")
        return " ".join(resolved)

    def __bytes__(self) -> bytes:
        return bytes(self.header) + bytes(self.body)

    def _parse(self, proto: Optional[type[T]]) -> None:
        if proto:
            self.body: T = proto()
            if self.payload:
                self.body.parse(self.payload)

    @property
    def msg(self) -> EMsg:
        """Union[:class:`.EMsg`, :class:`int`]: The :attr:`header.msg`."""
        return self.header.msg

    @msg.setter
    def msg(self, value: int) -> None:
        self.header.msg = EMsg.try_value(value)

    @property
    def steam_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The :attr:`header`'s 64 bit Steam ID."""
        return self.header.steam_id if isinstance(self.header, AllowedHeaders) else None

    @steam_id.setter
    def steam_id(self, value: int) -> None:
        if isinstance(self.header, AllowedHeaders):
            self.header.steam_id = value

    @property
    def session_id(self) -> Optional[int]:
        """Optional[:class:`int`]: The :attr:`header`'s session ID."""
        return self.header.session_id if isinstance(self.header, AllowedHeaders) else None

    @session_id.setter
    def session_id(self, value: int) -> None:
        if isinstance(self.header, AllowedHeaders):
            self.header.session_id = value

    def parse(self) -> None:
        raise NotImplementedError


class Msg(MsgBase[T]):
    """A wrapper around received protobuf messages.

    .. container:: operations

        .. describe:: bytes(x)

            Returns the sterilised message.

        .. describe:: x[y]

            Allows for type hinting of the messages body.
            e.g.::

                async def handle_multi(self, msg: MsgProto['CMsgMulti']) -> None:
                    if msg.body.size_unzipped:  # this is now properly typed
                        ...

    Parameters
    ----------
    msg: :class:`EMsg`
        The emsg for the message.
    data: Optional[:class:`bytes`]
        The raw data for the message.
    extended: :class:`bool`
        Which header type to use, ``True`` uses :class:`.ExtendedMsgHdr` else it's :class:`.MsgHdr`.
    **kwargs
        Any keyword-arguments to construct the :attr:`body` with.

    Attributes
    ----------
    header: Union[:class:`.ExtendedMsgHdr`, :class:`.MsgHdr`]
        The message's header.
    msg: :class:`.EMsg`
        The emsg for the message.
    body: :class:`betterproto.Message`
        The instance of the protobuf.
    payload: :class:`bytes`
        The raw data for the message.
    """

    def __init__(
        self,
        msg: EMsg,
        data: Optional[bytes] = None,
        extended: bool = False,
        **kwargs: Any,
    ):
        self.header = ExtendedMsgHdr(data) if extended else MsgHdr(data)
        self.skip = self.header.SIZE
        super().__init__(msg, data, **kwargs)

    def __repr__(self) -> str:
        return f"<Msg {super().__repr__()}>"

    def parse(self) -> None:
        """Parse the payload/data into a protobuf."""
        if self.body is None:
            proto = get_cmsg(self.msg)
            self._parse(proto)


class MsgProto(MsgBase[T]):
    """A wrapper around received protobuf messages.

    .. container:: operations

        .. describe:: bytes(x)

            Returns the sterilised message.

        .. describe:: x[y]

            Allows for type hinting of the messages body.
            e.g.::

                async def handle_multi(self, msg: MsgProto['CMsgMulti']) -> None:
                    log.debug('Received a multi, unpacking')
                    if msg.body.size_unzipped:  # this is now properly typed
                        ...

    Parameters
    ----------
    msg: :class:`.EMsg`
        The emsg for the message.
    data: Optional[:class:`bytes`]
        The raw data for the message.
    **kwargs
        Any keyword-arguments to construct the :attr:`body` with.

    Attributes
    ----------
    header: Union[:class:`.ExtendedMsgHdr`, :class:`.MsgHdr`]
        The message's header.
    msg: :class:`.EMsg`
        The emsg for the message.
    body: :class:`betterproto.Message`
        The instance of the protobuf.
    payload: :class:`bytes`
        The raw data for the message.
    """

    __slots__ = ("um_name",)

    def __init__(
        self,
        msg: EMsg,
        data: Optional[bytes] = None,
        _um_name: Optional[str] = None,
        **kwargs: Any,
    ):
        self.header = MsgHdrProtoBuf(data)
        self.skip = self.header._full_size
        self.um_name = _um_name
        super().__init__(msg, data, **kwargs)

    def __repr__(self) -> str:
        return f"<MsgProto {super().__repr__()}>"

    def parse(self) -> None:
        """Parse the payload/data into a protobuf."""
        if self.body is None:
            if self.msg in (
                EMsg.ServiceMethod,
                EMsg.ServiceMethodResponse,
                EMsg.ServiceMethodSendToClient,
                EMsg.ServiceMethodCallFromClient,
            ):
                name = self.header.job_name_target or self.um_name
                proto = get_um(f"{name}_Response" if self.msg == EMsg.ServiceMethodResponse else name)
                if name:
                    self.header.job_name_target = name.replace("_Request", "").replace("_Response", "")

            else:
                proto = get_cmsg(self.msg)

            self._parse(proto)
