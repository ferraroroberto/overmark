"""Key combos: normalising, the in-draw key map, and parsing the global hotkey.

Combos are lowercase strings such as ``"ctrl+z"`` or ``"e"``, modifiers in a fixed
order, so a binding written by hand in ``config.json`` compares equal to one built
from a key event.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")
_ALIASES = {
    "control": "ctrl",
    "escape": "esc",
    "meta": "win",
    "super": "win",
    "cmd": "win",
    "return": "enter",
}

# Keys used only while drawing, when the overlay has keyboard focus. Letters avoid
# the slideshow keys (arrows, space, page up/down, b/w) so muscle memory is safe.
DEFAULT_KEYS: dict[str, str] = {
    "pen": "p",
    "highlighter": "h",
    "arrow": "a",
    "text": "t",
    "laser": "l",
    "undo": "ctrl+z",
    "clear": "e",
    "pin": "f",
    "cheat_sheet": "?",
    "exit": "esc",
    **{f"preset_{n}": str(n) for n in range(1, 8)},
}

ACTION_LABELS: dict[str, str] = {
    "pen": "Pen",
    "highlighter": "Highlighter",
    "arrow": "Arrow",
    "text": "Text label (click, type, Enter)",
    "laser": "Laser (hold)",
    "undo": "Undo",
    "clear": "Clear all ink",
    "pin": "Pin ink (stop fading)",
    "cheat_sheet": "This cheat-sheet",
    "exit": "Stop drawing (again: clear)",
    **{f"preset_{n}": f"Preset {n}" for n in range(1, 8)},
}

# RegisterHotKey modifier flags.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
_MOD_FLAGS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}


def normalize_combo(text: str) -> str:
    """Return ``text`` as a canonical combo; raise ``ValueError`` if it is not one key."""
    parts = [p.strip().lower() for p in text.replace(" ", "").split("+")]
    # "ctrl++" means ctrl and the plus key: an empty part after a separator is "+".
    if text.endswith("++"):
        parts = parts[:-2] + ["+"]
    parts = [_ALIASES.get(p, p) for p in parts if p]
    mods = sorted({p for p in parts if p in MODIFIER_ORDER}, key=MODIFIER_ORDER.index)
    keys = [p for p in parts if p not in MODIFIER_ORDER]
    if len(keys) != 1:
        raise ValueError(f"expected exactly one non-modifier key in {text!r}")
    return "+".join([*mods, keys[0]])


class KeyMap:
    """Reverse lookup from a combo to the action bound to it."""

    def __init__(self, bindings: dict[str, str]) -> None:
        self.bindings = dict(bindings)
        self._by_combo: dict[str, str] = {}
        for action, combo in bindings.items():
            key = normalize_combo(combo)
            if key in self._by_combo:
                log.warning(
                    "⚠️ key %r bound to both %s and %s; keeping %s",
                    key,
                    self._by_combo[key],
                    action,
                    self._by_combo[key],
                )
                continue
            self._by_combo[key] = action

    def action_for(self, combo: str) -> str | None:
        try:
            return self._by_combo.get(normalize_combo(combo))
        except ValueError:
            return None


def hotkey_clashes(hotkeys: dict[str, str], draw_keys: dict[str, str]) -> list[str]:
    """Messages for global hotkeys that share a combo, or that take a key used while drawing.

    ``hotkeys`` maps a label (``"Draw"``) to its combo; ``draw_keys`` is the in-draw key
    map. A global hotkey wins over the overlay, so a shared combo silently disables one.
    """
    problems = []
    seen: dict[str, str] = {}
    in_draw = {}
    for action, combo in draw_keys.items():
        try:
            in_draw[normalize_combo(combo)] = action
        except ValueError:
            continue
    for label, combo in hotkeys.items():
        try:
            key = normalize_combo(combo)
        except ValueError:
            continue  # validity is reported by parse_hotkey, not here
        if key in seen:
            problems.append(f"{seen[key]} and {label} both use {key.upper()}")
        else:
            seen[key] = label
        if key in in_draw:
            action = ACTION_LABELS.get(in_draw[key], in_draw[key])
            problems.append(f"{label} uses {key.upper()}, the in-draw key for {action}")
    return problems


def _virtual_key(key: str) -> int | None:
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1  # VK_F1 .. VK_F24 are contiguous
    named = {"space": 0x20, "pause": 0x13, "insert": 0x2D, "home": 0x24, "end": 0x23}
    return named.get(key)


def parse_hotkey(text: str) -> tuple[int, int]:
    """Parse a global hotkey into ``(modifier_flags, virtual_key)`` for RegisterHotKey.

    A global hotkey needs ctrl, alt or win: a bare letter would swallow typing in
    every other application.
    """
    combo = normalize_combo(text)
    *mods, key = combo.split("+")
    if not {"ctrl", "alt", "win"} & set(mods):
        raise ValueError("a global hotkey needs ctrl, alt or win")
    vk = _virtual_key(key)
    if vk is None:
        raise ValueError(f"unsupported key {key!r} for a global hotkey")
    flags = 0
    for mod in mods:
        flags |= _MOD_FLAGS[mod]
    return flags, vk
