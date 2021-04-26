import platform
from importlib.metadata import distribution


def get_version_info(package: str) -> str:
    return distribution(package).version


def main() -> None:
    print("python version:", platform.python_version())
    print("steam.py version:", get_version_info("steamio"))
    print("aiohttp version:", get_version_info("aiohttp"))
    print("betterproto version:", get_version_info("betterproto"))
    print("operating system info:", platform.platform())


if __name__ == "__main__":
    main()
