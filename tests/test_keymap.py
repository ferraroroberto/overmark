"""Key combos, the in-draw key map and global hotkey parsing."""

import pytest

from overmark.keymap import (
    DEFAULT_KEYS,
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    KeyMap,
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
