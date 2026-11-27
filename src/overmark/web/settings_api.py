"""What the settings page reads and how a save from it is checked. Pure Python, no Qt.

A save carries the whole ``config.json`` shape. It gets the same checks the settings
window ran before the page replaced it: every hotkey must parse (a preset's may be empty),
no two hotkeys may share a combo or take an in-draw key, and the keep-awake and recording
values must be valid.
A failed check names the problem and changes nothing.
"""

from __future__ import annotations

from typing import Any

from overmark.config import (
    MAX_TRANSPARENCY_PERCENT,
    PRESET_HOTKEY_KEYS,
    Settings,
    settings_from_dict,
)
from overmark.keepawake import (
    MAX_DISTANCE_PX,
    MAX_INTERVAL_S,
    MIN_INTERVAL_S,
    MODE_EXECUTION_STATE,
    MODE_NUDGE,
    parse_distance,
    parse_interval,
    parse_mode,
)
from overmark.keymap import ACTION_LABELS, hotkey_clashes, parse_hotkey
from overmark.recording.naming import TOKENS, validate_pattern
from overmark.recording.options import (
    FRAME_RATES,
    MAX_BITRATE_KBPS,
    parse_bitrate,
    parse_screen,
)

# Label shown in errors, then the key under ``hotkey`` in config.json.
HOTKEYS = (
    ("Draw", "toggle_draw"),
    ("Start/stop recording", "record_toggle"),
    ("Pause recording", "record_pause"),
)
# The same, for the hotkeys that may be left empty.
PRESET_HOTKEYS = tuple((f"Preset {n}", key) for n, key in enumerate(PRESET_HOTKEY_KEYS, 1))

# The page's pickers: value and label pairs, so the page holds no list of its own.
CHOICES: dict[str, Any] = {
    "awake_modes": [
        [MODE_EXECUTION_STATE, "Ask Windows"],
        [MODE_NUDGE, "Nudge the pointer"],
    ],
    "containers": [["mp4", "MP4 (H.264)"], ["mkv", "MKV (H.264)"], ["webm", "WebM (VP9)"]],
    "qualities": [["low", "Low (small files)"], ["medium", "Medium"], ["high", "High"]],
    "backends": [
        ["auto", "Automatic"],
        ["ddagrab", "GPU duplication"],
        ["gdigrab", "GDI (slower)"],
    ],
    "frame_rates": list(FRAME_RATES),
    "name_tokens": list(TOKENS),
    "min_interval_s": MIN_INTERVAL_S,
    "max_interval_s": MAX_INTERVAL_S,
    "max_distance_px": MAX_DISTANCE_PX,
    "max_bitrate_kbps": MAX_BITRATE_KBPS,
    "max_transparency": MAX_TRANSPARENCY_PERCENT,
    "key_labels": dict(ACTION_LABELS),
}


class SettingsError(ValueError):
    """A save the page must refuse; the message is shown to the user as it is."""


def _block(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise SettingsError(f"The save has no {key} block")
    return value


def _check(what: str, check, value: Any) -> None:
    try:
        check(value)
    except ValueError as exc:
        raise SettingsError(f"{what}: {exc}") from None


def checked_update(current: Settings, raw: Any) -> Settings:
    """The settings a save asks for, or ``SettingsError`` saying why it is refused.

    The in-draw keys, tool sizes and toolbar positions are not edited on the page, so
    they come from ``current``: a toolbar drag made while the page was open survives.
    """
    if not isinstance(raw, dict):
        raise SettingsError("The save is not a settings object")
    hotkeys = _block(raw, "hotkey")
    combos = {}
    for label, key in (*HOTKEYS, *PRESET_HOTKEYS):
        optional = key in PRESET_HOTKEY_KEYS
        combo = hotkeys.get(key, "" if optional else None)
        if optional and combo == "":
            continue
        if not isinstance(combo, str) or not combo.strip():
            raise SettingsError(f"{label} hotkey: press a key combination")
        _check(f"{label} hotkey", parse_hotkey, combo)
        combos[label] = combo
    clashes = hotkey_clashes(combos, current.keys)
    if clashes:
        raise SettingsError("Hotkeys clash: " + "; ".join(clashes))

    awake = _block(raw, "keep_awake")
    _check("Keep-awake", parse_mode, awake.get("mode"))
    _check("Keep-awake", parse_interval, awake.get("interval_seconds"))
    _check("Keep-awake", parse_distance, awake.get("distance_px"))

    recording = _block(raw, "recording")
    _check("Recording", validate_pattern, recording.get("name_pattern"))
    _check("Recording", parse_bitrate, recording.get("bitrate_kbps"))
    _check("Recording", parse_screen, recording.get("screen"))
    microphone = recording.get("microphone")
    if isinstance(microphone, dict) and microphone.get("enabled") is True:
        device = microphone.get("device")
        if not isinstance(device, str) or not device.strip():
            raise SettingsError("Recording: pick a microphone, or switch the microphone off")

    updated = settings_from_dict(raw)
    updated.keys = dict(current.keys)
    updated.sizes = current.sizes
    updated.toolbar_positions = dict(current.toolbar_positions)
    return updated
