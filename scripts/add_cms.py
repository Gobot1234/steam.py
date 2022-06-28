"""
A script to add the default list of CMs to the constants file if Steam is down.

Licensed under The MIT License (MIT) - Copyright (c) 2020-present James H-B. See LICENSE
"""

import asyncio
from pathlib import Path

import aiohttp
import black
from typing_extensions import Final

from steam import NoCMsFound
from steam.models import api_route

ROOT: Final = Path(__file__).parent
DEFAULT_CMS_URL: Final = api_route("ISteamDirectory/GetCMListForConnect") % {
    "cmtype": "websockets",
    "realm": "steamglobal",
}
CONST_FILE: Final = ROOT.parent / "steam" / "_const.py"


async def amain() -> None:
    async with aiohttp.ClientSession() as client:
        async with client.get(DEFAULT_CMS_URL) as r:
            default_cms = await r.json(encoding="UTF-8")

    resp = default_cms["response"]
    if not resp["success"]:
        raise NoCMsFound(f"No Community Managers could be found to connect to:\n{resp['message']!r}")

    ws_list: list[str] = sorted(cm["endpoint"] for cm in default_cms["response"]["serverlist"])

    with CONST_FILE.open("r") as fp:
        new_lines = list[str]()
        for line in fp:
            new_lines.append(line)
            if line.strip() == "# default CMs if Steam API is down":
                break

        new_lines.append(f"DEFAULT_CMS: Final = {black.format_str(str(tuple(ws_list)), mode=black.Mode())}")

    with CONST_FILE.open("w") as fp:
        fp.write("".join(new_lines))


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
