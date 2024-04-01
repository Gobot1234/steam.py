import pytest

from steam import AppType, Enum, Instance, Intents, Language, Result, TypeChar


def is_unknown(enum: Enum) -> bool:
    return "Unknown" in enum.name


def test_enum_behaviour() -> None:
    assert isinstance(Result.OK, Result)
    assert isinstance(Result.OK, int)
    assert Result.OK.name == "OK"
    assert Result.OK.value == 1
    assert Result["OK"] is Result.OK
    assert Result(1) is Result.OK

    assert isinstance(Language.English, Language)
    assert isinstance(Language.English, int)
    assert Language.English.name == "English"
    assert Language.English.value == 0
    assert Language["English"] is Language.English
    assert Language(0) is Language.English

    with pytest.raises(AttributeError):
        Language.English.Arabic  # diverge from enum behaviour

    assert Language.English.api_name


def test_enum_try_value() -> None:
    assert Result.try_value(1) == Result.OK
    assert is_unknown(Result.try_value(10_000))


def test_flag_behaviour() -> None:
    assert isinstance(Instance.Desktop, Instance)
    assert isinstance(Instance.Desktop, int)
    assert Instance.Desktop.name == "Desktop"
    assert Instance.Desktop.value == 1
    assert Instance["Desktop"] is Instance.Desktop
    assert Instance(1) is Instance.Desktop

    value = Instance.Desktop | Instance.Web
    assert isinstance(value, Instance)
    assert isinstance(value, int)
    assert value.name == "Desktop | Web"
    assert value.value == 1 | 4

    assert isinstance(value & Instance.Desktop, Instance)
    assert isinstance(value & Instance.Desktop, int)

    assert (value & Instance.Desktop).name == "Desktop"
    assert (value & Instance.Desktop).value == 1
    assert value & Instance.Desktop is Instance.Desktop

    assert isinstance(AppType.Game, AppType)
    assert isinstance(AppType.Game, int)
    assert AppType.Game.name == "Game"
    assert AppType.Game.value == 1
    assert AppType["Game"] is AppType.Game
    assert AppType(1) is AppType.Game


def test_flag_try_value() -> None:
    assert Instance.try_value(1) == Instance.Desktop
    assert Instance.try_value(1 << 17 | 1 << 18) == Instance.ChatMMSLobby | Instance.ChatLobby
    assert Instance.try_value(100).value == 100

    assert Instance.try_value(0) == Instance.All

    instance_flag_20 = Instance.try_value(1 << 20)
    assert is_unknown(instance_flag_20)
    assert instance_flag_20.value == 1 << 20


def test_intents():
    assert Intents.Market & Intents.Safe == 0
    assert Intents.Market | Intents.Safe == Intents.All


def test_language_from_str() -> None:
    assert Language.from_str("english") == Language.English
    not_a_lang = Language.from_str("not a lang")
    assert not_a_lang.name == "Not A Lang"


def test_app_flag_from_str() -> None:
    assert AppType.from_str("game,dlc") == AppType.Game | AppType.DLC
    assert AppType.from_str("SERIES ") == AppType.Series


def test_aliasing() -> None:
    assert TypeChar.T == TypeChar.L == TypeChar.c
    assert TypeChar.T is not TypeChar.L
    assert TypeChar.T is not TypeChar.c
    assert TypeChar.L is not TypeChar.c
