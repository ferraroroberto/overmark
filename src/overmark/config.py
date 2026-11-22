"""Settings: load ``config.json`` (created from ``config.sample.json``), validate, save.

Pure Python, no Qt, so the defaults and validation are unit-testable.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from overmark.keepawake import (
    KeepAwake,
    parse_distance,
    parse_interval,
    parse_mode,
)
from overmark.keymap import DEFAULT_KEYS, normalize_combo, parse_hotkey

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.json"
SAMPLE_PATH = REPO_ROOT / "config.sample.json"

PRESET_COUNT = 7
DEFAULT_HOTKEY = "ctrl+alt+d"
MAX_TRANSPARENCY_PERCENT = 95  # fully transparent ink would be invisible, not a useful preset


@dataclass
class Transparency:
    enabled: bool = False
    percent: int = 0


@dataclass
class Outline:
    enabled: bool = True
    thickness_px: float = 2.0


@dataclass
class Preset:
    name: str
    color: str
    thickness_px: float = 6.0
    transparency: Transparency = field(default_factory=Transparency)
    outline: Outline = field(default_factory=Outline)


@dataclass
class Fade:
    enabled: bool = True
    delay_seconds: float = 8.0


@dataclass
class Sizes:
    """Tool sizes in capture pixels, chosen to survive video-call compression."""

    highlighter_px: float = 28.0
    text_px: float = 32.0
    laser_dot_px: float = 18.0
    laser_halo_px: float = 6.0


def default_presets() -> list[Preset]:
    def solid(name: str, color: str) -> Preset:
        return Preset(name, color, 6.0, Transparency(False, 0), Outline(True, 2.0))

    return [
        solid("yellow", "#FFE600"),
        solid("magenta", "#FF2BD6"),
        solid("cyan", "#19E3FF"),
        solid("mint", "#4DFFA6"),
        solid("white", "#FFFFFF"),
        solid("ink", "#111111"),
        Preset("marker", "#FFE600", 28.0, Transparency(True, 55), Outline(False, 0.0)),
    ]


@dataclass
class Settings:
    toggle_hotkey: str = DEFAULT_HOTKEY
    cover_all_screens: bool = True
    fade: Fade = field(default_factory=Fade)
    presets: list[Preset] = field(default_factory=default_presets)
    sizes: Sizes = field(default_factory=Sizes)
    keys: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYS))
    keep_awake: KeepAwake = field(default_factory=KeepAwake)


def _is_hex_color(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return True


def _number(value: Any, default: float, low: float, high: float, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        if value is not None:
            log.warning("⚠️ config: %s=%r is not a number; using %s", what, value, default)
        return default
    if not low <= value <= high:
        clamped = min(max(float(value), low), high)
        log.warning("⚠️ config: %s=%r out of range; using %s", what, value, clamped)
        return clamped
    return float(value)


def _flag(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _preset_from(raw: Any, fallback: Preset, index: int) -> Preset:
    if not isinstance(raw, dict):
        return fallback
    where = f"presets[{index}]"
    color = raw.get("color")
    if not _is_hex_color(color):
        log.warning("⚠️ config: %s.color=%r is not #RRGGBB; using default", where, color)
        color = fallback.color
    trans = raw.get("transparency") if isinstance(raw.get("transparency"), dict) else {}
    outline = raw.get("outline") if isinstance(raw.get("outline"), dict) else {}
    name = raw.get("name")
    return Preset(
        name=name if isinstance(name, str) and name.strip() else fallback.name,
        color=str(color).upper(),
        thickness_px=_number(
            raw.get("thickness_px"), fallback.thickness_px, 1, 120, f"{where}.thickness_px"
        ),
        transparency=Transparency(
            enabled=_flag(trans.get("enabled"), fallback.transparency.enabled),
            percent=int(
                _number(
                    trans.get("percent"),
                    fallback.transparency.percent,
                    0,
                    MAX_TRANSPARENCY_PERCENT,
                    f"{where}.transparency.percent",
                )
            ),
        ),
        outline=Outline(
            enabled=_flag(outline.get("enabled"), fallback.outline.enabled),
            thickness_px=_number(
                outline.get("thickness_px"),
                fallback.outline.thickness_px,
                0,
                12,
                f"{where}.outline.thickness_px",
            ),
        ),
    )


def _keys_from(raw: Any) -> dict[str, str]:
    keys = dict(DEFAULT_KEYS)
    if not isinstance(raw, dict):
        return keys
    for action, combo in raw.items():
        if action not in DEFAULT_KEYS:
            log.warning("⚠️ config: keys.%s is not a known action; ignored", action)
            continue
        try:
            keys[action] = normalize_combo(str(combo))
        except ValueError as exc:
            log.warning("⚠️ config: keys.%s=%r invalid (%s); using default", action, combo, exc)
    return keys


def _keep_awake_from(raw: Any) -> KeepAwake:
    base = KeepAwake()
    if not isinstance(raw, dict):
        return base

    def checked(parse, key: str, default):
        if key not in raw:
            return default
        try:
            return parse(raw[key])
        except ValueError as exc:
            log.warning(
                "⚠️ config: keep_awake.%s=%r invalid (%s); using %s", key, raw[key], exc, default
            )
            return default

    return KeepAwake(
        enabled=_flag(raw.get("enabled"), base.enabled),
        mode=checked(parse_mode, "mode", base.mode),
        interval_seconds=checked(parse_interval, "interval_seconds", base.interval_seconds),
        distance_px=checked(parse_distance, "distance_px", base.distance_px),
    )


def settings_from_dict(raw: dict[str, Any]) -> Settings:
    """Build settings from parsed JSON, falling back to defaults key by key."""
    base = Settings()
    hotkey = (raw.get("hotkey") or {}).get("toggle_draw", base.toggle_hotkey)
    try:
        parse_hotkey(str(hotkey))
        hotkey = normalize_combo(str(hotkey))
    except ValueError as exc:
        log.warning("⚠️ config: hotkey %r invalid (%s); using %s", hotkey, exc, DEFAULT_HOTKEY)
        hotkey = DEFAULT_HOTKEY

    fade_raw = raw.get("fade") if isinstance(raw.get("fade"), dict) else {}
    sizes_raw = raw.get("sizes") if isinstance(raw.get("sizes"), dict) else {}
    screens_raw = raw.get("screens") if isinstance(raw.get("screens"), dict) else {}

    presets_raw = raw.get("presets") if isinstance(raw.get("presets"), list) else []
    if presets_raw and len(presets_raw) != PRESET_COUNT:
        log.warning(
            "⚠️ config: %d presets found, %d expected; missing ones use defaults",
            len(presets_raw),
            PRESET_COUNT,
        )
    presets = [
        _preset_from(presets_raw[i] if i < len(presets_raw) else None, fallback, i)
        for i, fallback in enumerate(base.presets)
    ]

    return Settings(
        toggle_hotkey=hotkey,
        cover_all_screens=_flag(screens_raw.get("cover_all"), base.cover_all_screens),
        fade=Fade(
            enabled=_flag(fade_raw.get("enabled"), base.fade.enabled),
            delay_seconds=_number(
                fade_raw.get("delay_seconds"), base.fade.delay_seconds, 0.5, 3600, "fade.delay"
            ),
        ),
        presets=presets,
        sizes=Sizes(
            highlighter_px=_number(sizes_raw.get("highlighter_px"), 28.0, 4, 120, "highlighter"),
            text_px=_number(sizes_raw.get("text_px"), 32.0, 8, 200, "sizes.text_px"),
            laser_dot_px=_number(sizes_raw.get("laser_dot_px"), 18.0, 4, 80, "laser_dot_px"),
            laser_halo_px=_number(sizes_raw.get("laser_halo_px"), 6.0, 0, 40, "laser_halo_px"),
        ),
        keys=_keys_from(raw.get("keys")),
        keep_awake=_keep_awake_from(raw.get("keep_awake")),
    )


def settings_to_dict(settings: Settings) -> dict[str, Any]:
    """Serialise in the same shape as ``config.sample.json``."""
    return {
        "hotkey": {"toggle_draw": settings.toggle_hotkey},
        "screens": {"cover_all": settings.cover_all_screens},
        "fade": {
            "enabled": settings.fade.enabled,
            "delay_seconds": settings.fade.delay_seconds,
        },
        "presets": [
            {
                "name": p.name,
                "color": p.color,
                "thickness_px": p.thickness_px,
                "transparency": {
                    "enabled": p.transparency.enabled,
                    "percent": p.transparency.percent,
                },
                "outline": {"enabled": p.outline.enabled, "thickness_px": p.outline.thickness_px},
            }
            for p in settings.presets
        ],
        "sizes": {
            "highlighter_px": settings.sizes.highlighter_px,
            "text_px": settings.sizes.text_px,
            "laser_dot_px": settings.sizes.laser_dot_px,
            "laser_halo_px": settings.sizes.laser_halo_px,
        },
        "keys": dict(settings.keys),
        "keep_awake": {
            "enabled": settings.keep_awake.enabled,
            "mode": settings.keep_awake.mode,
            "interval_seconds": settings.keep_awake.interval_seconds,
            "distance_px": settings.keep_awake.distance_px,
        },
    }


def load(path: Path = CONFIG_PATH, sample: Path = SAMPLE_PATH) -> Settings:
    """Load settings, first creating ``path`` from ``sample`` when it is missing.

    A malformed file is left untouched (it is the user's) and defaults are used.
    """
    if not path.exists() and sample.exists():
        shutil.copyfile(sample, path)
        log.info("ℹ️ created %s from the sample", path.name)
    if not path.exists():
        log.warning("⚠️ no %s and no sample; using built-in defaults", path.name)
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.error("❌ could not read %s (%s); using built-in defaults", path.name, exc)
        return Settings()
    if not isinstance(raw, dict):
        log.error("❌ %s is not a JSON object; using built-in defaults", path.name)
        return Settings()
    return settings_from_dict(raw)


def save(settings: Settings, path: Path = CONFIG_PATH) -> None:
    """Write atomically through a temp file so a crash never leaves half a config."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(settings_to_dict(settings), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    log.info("✅ saved settings to %s", path.name)
