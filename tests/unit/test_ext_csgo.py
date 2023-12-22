from unittest.mock import MagicMock

from steam.ext import csgo
from steam.protobufs.econ import Asset, ItemDescription

client = csgo.Client()
bot = csgo.Bot(command_prefix="!")


def test_item_construction():
    item = csgo.BackpackItem(MagicMock(), Asset(), ItemDescription(), MagicMock())
    assert csgo.BackpackItem.__slots__
    for attr in csgo.BackpackItem.__slots__:
        setattr(item, attr, MagicMock())
    csgo.BaseInspectedItem(*(MagicMock(),) * len(csgo.BaseInspectedItem.__slots__))
    for attr in csgo.CasketItem.__slots__:
        setattr(csgo.CasketItem(), attr, MagicMock())
