"""
A small script that imitates the behaviour of the WS parser and allows you to debug messages from the steam chat

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

import asyncio
import logging
from base64 import b64decode, b64encode
from collections import defaultdict
from pathlib import Path
from typing import Any

import black

import steam
from steam.gateway import SteamWebSocket
from steam.protobufs import EMsg, ProtobufMessage, UnifiedMessage
from steam.protobufs.base import CMsgMulti
from steam.protobufs.msg import REQUEST_EMSGS, RESPONSE_EMSGS
from steam.state import ConnectionState

logging.getLogger("steam").setLevel(logging.DEBUG)
logging.basicConfig()


async def main(input_message: str) -> None:
    try:
        if (path := Path(input_message)).is_file():
            input_message = b64encode(path.read_bytes()).decode()
    except OSError:
        pass

    client = steam.Client()
    client.http.user = steam.ID(0)  # type: ignore
    state = client._state
    fake_ws = SteamWebSocket(state, None, None, None)  # type: ignore
    client.ws = fake_ws

    def parser(msg: ProtobufMessage) -> None:
        print(f"{msg.MSG=}")
        print(black.format_str(str(msg), mode=black.Mode()))
        print(black.format_str(str(msg.header), mode=black.Mode()))
        if msg._unknown_fields:
            print(f"Unknown fields: {msg._unknown_fields}")

    def handle_multi(self: ConnectionState, msg: CMsgMulti) -> None:
        print("This is a multi message, unpacking...")
        state.handle_multi(msg)

    def handle_um_request(self: ConnectionState, msg: UnifiedMessage) -> None:
        print("This is a UM request", msg.UM_NAME)
        print(black.format_str(str(msg), mode=black.Mode()))
        print(black.format_str(str(msg.header), mode=black.Mode()))
        if msg._unknown_fields:
            print(f"Unknown fields: {msg._unknown_fields}")

    def handle_um_response(self: ConnectionState, msg: UnifiedMessage) -> None:
        print("This is a UM response", msg.UM_NAME)
        print(black.format_str(str(msg), mode=black.Mode()))
        print(black.format_str(str(msg.header), mode=black.Mode()))
        if msg._unknown_fields:
            print(f"Unknown fields: {msg._unknown_fields}")

    state.parsers = defaultdict[EMsg, Any](lambda: parser)
    state.parsers[EMsg.Multi] = handle_multi
    for msg in REQUEST_EMSGS:
        state.parsers[msg] = handle_um_request
    for msg in RESPONSE_EMSGS:
        state.parsers[msg] = handle_um_response
    fake_ws.receive(bytearray(b64decode(input_message)))
    await asyncio.sleep(2)
