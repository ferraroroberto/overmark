"""The recording block of config.json: defaults, validation, round trip, screen choice."""

import pytest

from overmark.config import Settings, settings_from_dict, settings_to_dict
from overmark.recording.monitors import Monitor, bounding_box, describe, numbered, select
from overmark.recording.options import (
    RecordingOptions,
    SystemAudio,
    options_from_dict,
    options_to_dict,
    parse_bitrate,
    parse_screen,
)

A = Monitor("a", 0, 0, 1920, 1080, 0)
B = Monitor("b", 1920, 0, 1920, 1080, 1)
C = Monitor("c", 0, -1080, 1920, 1080, 2)


def test_missing_block_gives_defaults() -> None:
    assert options_from_dict(None) == RecordingOptions()
    assert settings_from_dict({}).recording == RecordingOptions()


def test_every_setting_round_trips_through_config() -> None:
    raw = {
        "folder": "D:/talks",
        "name_pattern": "{date}-session",
        "container": "webm",
        "quality": "high",
        "bitrate_kbps": 8000,
        "frame_rate": 60,
        "screen": 2,
        "cursor": False,
        "include_ink": False,
        "microphone": {"enabled": True, "device": "Desk Mic"},
        "system_audio": {"enabled": True, "device": "Desk Speakers"},
        "backend": "gdigrab",
        "ffmpeg_path": "C:/tools/ffmpeg.exe",
    }
    options = options_from_dict(raw)
    assert options_to_dict(options) == raw
    settings = Settings(recording=options, record_hotkey="ctrl+alt+f7", pause_hotkey="ctrl+alt+f8")
    again = settings_from_dict(settings_to_dict(settings))
    assert again.recording == options
    assert (again.record_hotkey, again.pause_hotkey) == ("ctrl+alt+f7", "ctrl+alt+f8")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("container", "avi"),
        ("quality", "ultra"),
        ("frame_rate", 25),
        ("bitrate_kbps", -1),
        ("bitrate_kbps", "fast"),
        ("screen", 0),
        ("screen", "left"),
        ("backend", "wgc"),
        ("name_pattern", "{user}"),
        ("folder", 3),
    ],
)
def test_bad_values_fall_back_to_the_default(key: str, value) -> None:
    assert getattr(options_from_dict({key: value}), key) == getattr(RecordingOptions(), key)


def test_bad_recording_hotkeys_fall_back() -> None:
    settings = settings_from_dict({"hotkey": {"record_toggle": "r", "record_pause": "ctrl+alt+?"}})
    assert settings.record_hotkey == "ctrl+alt+f9"
    assert settings.pause_hotkey == "ctrl+alt+f10"


@pytest.mark.parametrize(("value", "expected"), [("all", "all"), (" Active ", "active"), (3, 3)])
def test_screen_values(value, expected) -> None:
    assert parse_screen(value) == expected


@pytest.mark.parametrize("value", [True, 0, 17, "x", 1.5])
def test_screen_rejects(value) -> None:
    with pytest.raises(ValueError, match="Screen"):
        parse_screen(value)


@pytest.mark.parametrize("value", [True, 1.5, None, "-3", 200_001])
def test_bitrate_rejects(value) -> None:
    with pytest.raises(ValueError, match="Bitrate"):
        parse_bitrate(value)


def test_screens_are_numbered_left_to_right_then_top_to_bottom() -> None:
    assert numbered([A, B, C]) == [C, A, B]
    assert describe([A, B])[1] == "Screen 2: 1920×1080 at 1920, 0"


def test_all_screens_selects_every_monitor() -> None:
    assert select([A, B, C], "all", None) == [C, A, B]


def test_active_screen_is_the_one_under_the_pointer() -> None:
    assert select([A, B, C], "active", (2500, 500)) == [B]
    assert select([A, B, C], "active", (10, -10)) == [C]


def test_active_screen_without_a_pointer_takes_the_first() -> None:
    assert select([A, B], "active", None) == [A]
    assert select([A, B], "active", (99_999, 0)) == [A]


def test_a_numbered_screen_is_picked_by_its_number() -> None:
    assert select([A, B, C], 3, None) == [B]


def test_a_screen_number_beyond_the_monitors_is_an_error() -> None:
    with pytest.raises(ValueError, match="not connected"):
        select([A, B], 3, None)
    with pytest.raises(ValueError, match="no monitors"):
        select([], "all", None)


def test_bounding_box_covers_every_monitor() -> None:
    assert bounding_box([A, B, C]) == (0, -1080, 3840, 2160)


def test_system_audio_defaults_off_with_the_default_output() -> None:
    options = options_from_dict({})
    assert options.system_audio == SystemAudio(enabled=False, device="")


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ("on", SystemAudio()),
        ({"enabled": "yes", "device": "Desk Speakers"}, SystemAudio(False, "Desk Speakers")),
        ({"enabled": True, "device": 7}, SystemAudio(True, "")),
    ],
)
def test_invalid_system_audio_falls_back_with_a_warning(block, expected, caplog) -> None:
    assert options_from_dict({"system_audio": block}).system_audio == expected
    assert "recording.system_audio" in caplog.text
