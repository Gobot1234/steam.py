"""
A small script that imitates the behaviour of the WS parser and allows you to debug messages from the steam chat

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

import asyncio
import sys
from base64 import b64decode
from collections import defaultdict

import betterproto
import black

import steam
from steam.gateway import SteamWebSocket
from steam.protobufs import EMsg, MsgBase, MsgProto
from steam.protobufs.base import CMsgMulti


async def amain(input_message: str) -> None:
    client = steam.Client()
    client.http.user = steam.ID(0)  # type: ignore
    fake_ws = SteamWebSocket(client._connection, None, None, None)  # type: ignore

    def parser(msg: MsgBase[betterproto.Message]) -> None:
        print(f"{msg.msg=}")
        print(black.format_str(str(msg.body), mode=black.Mode()))
        if msg.body._unknown_fields:
            print(f"Unknown fields: {msg.body._unknown_fields}")

    def handle_multi(msg: MsgProto[CMsgMulti]) -> None:
        print("This is a multi message, unpacking...")
        fake_ws.handle_multi(msg)

    def handle_um_request(msg: MsgProto[betterproto.Message]) -> None:
        print("This is a UM request", msg.header.body.job_name_target)
        print(black.format_str(str(msg.body), mode=black.Mode()))
        if msg.body._unknown_fields:
            print(f"Unknown fields: {msg.body._unknown_fields}")

    def handle_um_response(msg: MsgProto[betterproto.Message]) -> None:
        print("This is a UM response", msg.header.body.job_name_target)
        print(black.format_str(str(msg.body), mode=black.Mode()))
        if msg.body._unknown_fields:
            print(f"Unknown fields: {msg.body._unknown_fields}")

    fake_ws.parsers = defaultdict(lambda: parser)
    fake_ws.parsers[EMsg.Multi] = handle_multi
    fake_ws.parsers[EMsg.ServiceMethod] = handle_um_request
    fake_ws.parsers[EMsg.ServiceMethodResponse] = handle_um_response

    fake_ws.receive(b64decode(input_message))
    await asyncio.sleep(2)


def main(input: str) -> None:
    return asyncio.run(amain(input))


if __name__ == "__main__":
    main(sys.argv[1])
