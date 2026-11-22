"""Key combos, the in-draw key map and global hotkey parsing."""

import pytest

from overmark.keymap import (
    DEFAULT_KEYS,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    KeyMap,
    hotkey_clashes,
    normalize_combo,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ctrl+Alt+D", "ctrl+alt+d"),
        ("alt + control + d", "ctrl+alt+d"),
        ("Escape", "esc"),
        ("Meta+F2", "win+f2"),
        ("shift+ctrl+z", "ctrl+shift+z"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize_combo(raw) == expected


@pytest.mark.parametrize("raw", ["", "ctrl+alt", "a+b"])
def test_normalize_rejects_not_exactly_one_key(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_combo(raw)


def test_default_map_covers_every_action() -> None:
    keys = KeyMap(DEFAULT_KEYS)
    assert keys.action_for("e") == "clear"
    assert keys.action_for("Ctrl+Z") == "undo"
    assert keys.action_for("esc") == "exit"
    assert [keys.action_for(str(n)) for n in range(1, 8)] == [f"preset_{n}" for n in range(1, 8)]
    assert keys.action_for("x") is None


def test_rebinding_and_duplicates() -> None:
    keys = KeyMap({**DEFAULT_KEYS, "clear": "c", "pin": "c"})
    assert keys.action_for("c") == "clear"
    assert keys.action_for("e") is None


def test_parse_hotkey() -> None:
    assert parse_hotkey("ctrl+alt+d") == (MOD_CONTROL | MOD_ALT, ord("D"))
    assert parse_hotkey("ctrl+shift+f9") == (MOD_CONTROL | MOD_SHIFT, 0x78)
    assert parse_hotkey("alt+7") == (MOD_ALT, ord("7"))


@pytest.mark.parametrize("raw", ["d", "shift+d", "ctrl+alt+?"])
def test_parse_hotkey_rejects_unsafe_or_unknown(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_hotkey(raw)


DEFAULT_HOTKEYS = {
    "Draw": "ctrl+alt+d",
    "Start/stop recording": "ctrl+alt+f9",
    "Pause recording": "ctrl+alt+f10",
}


def test_default_hotkeys_do_not_clash() -> None:
    assert hotkey_clashes(DEFAULT_HOTKEYS, DEFAULT_KEYS) == []


def test_two_hotkeys_on_one_combo_clash() -> None:
    problems = hotkey_clashes({**DEFAULT_HOTKEYS, "Pause recording": "Alt+Ctrl+D"}, DEFAULT_KEYS)
    assert problems == ["Draw and Pause recording both use CTRL+ALT+D"]


def test_a_hotkey_on_an_in_draw_key_clashes() -> None:
    problems = hotkey_clashes({**DEFAULT_HOTKEYS, "Start/stop recording": "ctrl+z"}, DEFAULT_KEYS)
    assert problems == ["Start/stop recording uses CTRL+Z, the in-draw key for Undo"]


def test_rebound_in_draw_keys_are_what_counts() -> None:
    keys = {**DEFAULT_KEYS, "clear": "ctrl+alt+f9"}
    assert hotkey_clashes(DEFAULT_HOTKEYS, keys) == [
        "Start/stop recording uses CTRL+ALT+F9, the in-draw key for Clear all ink"
    ]
