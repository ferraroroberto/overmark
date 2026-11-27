"""A save from the settings page: the checks the settings window used to run, kept."""

import pytest

from overmark.config import Settings, settings_to_dict
from overmark.web.settings_api import SettingsError, checked_update


def saved(**changes) -> dict:
    """The page's save: the full settings shape with ``changes`` applied by dotted path."""
    raw = settings_to_dict(Settings())
    for path, value in changes.items():
        node = raw
        *parents, last = path.split("__")
        for key in parents:
            node = node[key]
        node[last] = value
    return raw


def test_a_valid_save_round_trips() -> None:
    raw = saved(fade__delay_seconds=3.5, screens__cover_all=False, hotkey__toggle_draw="ctrl+alt+q")
    updated = checked_update(Settings(), raw)
    assert updated.fade.delay_seconds == 3.5
    assert updated.cover_all_screens is False
    assert updated.toggle_hotkey == "ctrl+alt+q"


def test_keys_sizes_and_toolbar_positions_come_from_the_running_app() -> None:
    current = Settings()
    current.keys["pen"] = "j"
    current.toolbar_positions = {"layout-a": (10, 20)}
    raw = saved(keys={"pen": "p"}, toolbar={"positions": {}})
    updated = checked_update(current, raw)
    assert updated.keys["pen"] == "j"
    assert updated.toolbar_positions == {"layout-a": (10, 20)}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"hotkey__toggle_draw": "d"}, "Draw hotkey: a global hotkey needs ctrl, alt or win"),
        ({"hotkey__record_pause": ""}, "Pause recording hotkey: press a key combination"),
        ({"hotkey__record_toggle": "ctrl+alt+d"}, "Hotkeys clash: Draw and Start/stop recording"),
        ({"keep_awake__interval_seconds": 2}, "Keep-awake: Interval must be between 5"),
        ({"keep_awake__mode": "shake"}, "Keep-awake: Mode must be one of"),
        ({"recording__name_pattern": "{nope}"}, "Recording: Name pattern has unknown token"),
        ({"recording__bitrate_kbps": -1}, "Recording: Bitrate must be from 0"),
        ({"recording__screen": 99}, "Recording: Screen number must be from 1"),
    ],
)
def test_an_invalid_save_is_refused_with_its_reason(changes: dict, message: str) -> None:
    with pytest.raises(SettingsError, match="^" + message.replace("(", r"\(")):
        checked_update(Settings(), saved(**changes))


def test_a_hotkey_on_an_in_draw_key_is_refused() -> None:
    current = Settings()
    current.keys["pen"] = "ctrl+alt+p"
    with pytest.raises(SettingsError, match="the in-draw key for Pen"):
        checked_update(current, saved(hotkey__toggle_draw="ctrl+alt+p"))


def test_the_microphone_needs_a_device_when_it_is_on() -> None:
    raw = saved(recording__microphone={"enabled": True, "device": " "})
    with pytest.raises(SettingsError, match="pick a microphone"):
        checked_update(Settings(), raw)


def test_a_save_missing_a_block_is_refused() -> None:
    raw = saved()
    del raw["keep_awake"]
    with pytest.raises(SettingsError, match="no keep_awake block"):
        checked_update(Settings(), raw)
    with pytest.raises(SettingsError, match="not a settings object"):
        checked_update(Settings(), [])
