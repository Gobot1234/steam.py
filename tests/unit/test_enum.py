import pytest

from steam import AppFlag, Enum, InstanceFlag, Language, Result


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
    assert isinstance(InstanceFlag.Desktop, InstanceFlag)
    assert isinstance(InstanceFlag.Desktop, int)
    assert InstanceFlag.Desktop.name == "Desktop"
    assert InstanceFlag.Desktop.value == 1
    assert InstanceFlag["Desktop"] is InstanceFlag.Desktop
    assert InstanceFlag(1) is InstanceFlag.Desktop

    value = InstanceFlag.Desktop | InstanceFlag.Web
    assert isinstance(value, InstanceFlag)
    assert isinstance(value, int)
    assert value.name == "Desktop | Web"
    assert value.value == 1 | 4

    assert isinstance(value & InstanceFlag.Desktop, InstanceFlag)
    assert isinstance(value & InstanceFlag.Desktop, int)

    assert (value & InstanceFlag.Desktop).name == "Desktop"
    assert (value & InstanceFlag.Desktop).value == 1
    assert value & InstanceFlag.Desktop is InstanceFlag.Desktop

    assert isinstance(AppFlag.Game, AppFlag)
    assert isinstance(AppFlag.Game, int)
    assert AppFlag.Game.name == "Game"
    assert AppFlag.Game.value == 1
    assert AppFlag["Game"] is AppFlag.Game
    assert AppFlag(1) is AppFlag.Game


def test_flag_try_value() -> None:
    assert InstanceFlag.try_value(1) == InstanceFlag.Desktop
    assert InstanceFlag.try_value(1 << 17 | 1 << 18) == InstanceFlag.ChatMMSLobby | InstanceFlag.ChatLobby
    assert InstanceFlag.try_value(100).value == 100

    assert InstanceFlag.try_value(0) == InstanceFlag.All

    instance_flag_20 = InstanceFlag.try_value(1 << 20)
    assert is_unknown(instance_flag_20)
    assert instance_flag_20.value == 1 << 20


def test_language_from_str() -> None:
    assert Language.from_str("english") == Language.English
    not_a_lang = Language.from_str("not a lang")
    assert not_a_lang.name == "Not A Lang"
    assert not_a_lang.value == -1


def test_app_flag_from_str() -> None:
    assert AppFlag.from_str("game,dlc") == AppFlag.Game | AppFlag.DLC
    assert AppFlag.from_str("SERIES ") == AppFlag.Series
