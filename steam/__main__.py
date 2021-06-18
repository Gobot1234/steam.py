import platform

import aiohttp
import betterproto

import steam


def main() -> None:
    print("python version:", platform.python_version())
    print("steam.py version:", steam.__version__)
    print("aiohttp version:", aiohttp.__version__)
    print("betterproto version:", betterproto.__version__)
    print("operating system info:", platform.platform())


if __name__ == "__main__":
    main()
