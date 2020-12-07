# -*- coding: utf-8 -*-

import platform

import pkg_resources


def get_version_info(package: str) -> str:
    return pkg_resources.get_distribution(package).version


def main() -> None:
    print("python version:", platform.python_version())
    print("steam.py version:", get_version_info("steam"))
    print("aiohttp version:", get_version_info("aiohttp"))
    print("betterproto version:", get_version_info("betterproto"))
    print("operating system info:", platform.platform())


if __name__ == "__main__":
    main()
