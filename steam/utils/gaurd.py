from base64 import b64decode, b64encode
from hashlib import sha1
from hmac import new
from json import loads
from os.path import isfile
from struct import pack, unpack
from time import time

from steam.errors import SteamAuthenticatorError


def load_steam_guard(steam_guard: str):
    """
    Parameters
    -----------
    steam_guard: :class:`str`
        The location to the Steam Guard info

    Raises
    -------
    :exc:`SteamAuthenticatorError`
        The file wasn't loadable

    Returns
    -------
    :class:`dict`
        Dictionary of steam guard info
    """
    if isfile(steam_guard):
        with open(steam_guard, 'r') as f:
            return loads(f.read())
    else:
        try:
            return loads(steam_guard)
        except TypeError:
            raise SteamAuthenticatorError(f'{steam_guard} is not able to be loaded probably as it isn\'t a JSON file')


def generate_one_time_code(shared_secret: str, timestamp: int = int(time())):
    """
    Parameters
    -----------
    shared_secret: :class:`str`
        Identity secret from steam guard
    timestamp: Optional[:class:`int`]
        The time to generate the key for a specific time

    Returns
    -------
    :class:`str`
        2FA code
    """
    time_buffer = pack('>Q', timestamp // 30)  # pack as Big endian, uint64
    time_hmac = new(b64decode(shared_secret), time_buffer, digestmod=sha1).digest()
    begin = ord(time_hmac[19:20]) & 0xf
    full_code = unpack('>I', time_hmac[begin:begin + 4])[0] & 0x7fffffff  # unpack as Big endian uint32
    chars = '23456789BCDFGHJKMNPQRTVWXY'
    code = []

    for _ in range(5):
        full_code, i = divmod(full_code, len(chars))
        code.append(chars[i])

    return ''.join(code)


def generate_confirmation_key(identity_secret: str, tag: str, timestamp: int = int(time())):
    """
    Parameters
    -----------
    identity_secret: :class:`str`
        Identity secret from steam guard
    tag: :class:`str`
        Tag to encode to
    timestamp: Optional[:class:`int`]
        The time to generate the key for

    Returns
    -------
    :class:`bytes`
        Confirmation key for set timestamp
    """
    buffer = f'{pack(">Q", timestamp)}{tag.encode("ascii")}'
    return b64encode(new(b64decode(identity_secret), buffer, digestmod=sha1).digest())


# It works, however it's different that one generated from mobile app
def generate_device_id(steam_id: str):
    """
    Parameters
    -----------
    steam_id: :class:`str`
        The steam id to generate the id for

    Returns
    -------
    :class:`str`
        Device id
    """
    hexed_steam_id = sha1(steam_id.encode('ascii')).hexdigest()
    partial_id = [hexed_steam_id[:8],
                 hexed_steam_id[8:12],
                 hexed_steam_id[12:16],
                 hexed_steam_id[16:20],
                 hexed_steam_id[20:32]]
    return f'android:{"-".join(partial_id)}'
