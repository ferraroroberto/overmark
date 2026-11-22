"""Recording settings: the ``recording`` block of ``config.json``, validated key by key."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from overmark.recording.naming import DEFAULT_PATTERN, validate_pattern

log = logging.getLogger(__name__)

CONTAINERS = ("mp4", "mkv", "webm")
QUALITIES = ("low", "medium", "high")
FRAME_RATES = (15, 24, 30, 60)
BACKENDS = ("auto", "ddagrab", "gdigrab")
SCREEN_ALL = "all"
SCREEN_ACTIVE = "active"
MAX_BITRATE_KBPS = 200_000  # far above any screen recording; guards against typos
MAX_SCREENS = 16


@dataclass
class Microphone:
    enabled: bool = False
    device: str = ""  # a DirectShow audio device name; empty means none picked yet


@dataclass
class SystemAudio:
    enabled: bool = False
    device: str = ""  # a loopback device name; empty means the default output's loopback


@dataclass
class RecordingOptions:
    folder: str = ""  # empty means the user's Videos folder plus "Overmark"
    name_pattern: str = DEFAULT_PATTERN
    container: str = "mp4"
    quality: str = "medium"
    bitrate_kbps: int = 0  # 0 means the quality preset decides
    frame_rate: int = 30
    screen: str | int = SCREEN_ALL  # "all", "active", or a screen number from 1
    cursor: bool = True
    include_ink: bool = True
    microphone: Microphone = field(default_factory=Microphone)
    system_audio: SystemAudio = field(default_factory=SystemAudio)
    backend: str = "auto"
    ffmpeg_path: str = ""  # empty means look ffmpeg up on PATH


def parse_screen(value: Any) -> str | int:
    if isinstance(value, str) and value.strip().lower() in (SCREEN_ALL, SCREEN_ACTIVE):
        return value.strip().lower()
    if isinstance(value, bool):
        raise ValueError("Screen must be 'all', 'active' or a number from 1")
    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError("Screen must be 'all', 'active' or a number from 1") from None
    if not 1 <= number <= MAX_SCREENS:
        raise ValueError(f"Screen number must be from 1 to {MAX_SCREENS}")
    return number


def parse_bitrate(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise ValueError("Bitrate must be a whole number of kbps (0 for automatic)")
    try:
        kbps = int(str(value).strip())
    except ValueError:
        raise ValueError("Bitrate must be a whole number of kbps (0 for automatic)") from None
    if not 0 <= kbps <= MAX_BITRATE_KBPS:
        raise ValueError(f"Bitrate must be from 0 to {MAX_BITRATE_KBPS} kbps")
    return kbps


def _choice(raw: dict, key: str, choices: tuple, default: Any) -> Any:
    value = raw.get(key, default)
    if value in choices:
        return value
    log.warning(
        "⚠️ config: recording.%s=%r is not one of %s; using %r", key, value, choices, default
    )
    return default


def _text(raw: dict, key: str, default: str, label: str | None = None) -> str:
    value = raw.get(key, default)
    if isinstance(value, str):
        return value.strip()
    log.warning("⚠️ config: recording.%s=%r is not text; using %r", label or key, value, default)
    return default


def _flag(raw: dict, key: str, default: bool, label: str | None = None) -> bool:
    value = raw.get(key, default)
    if isinstance(value, bool):
        return value
    log.warning(
        "⚠️ config: recording.%s=%r is not true or false; using %r", label or key, value, default
    )
    return default


def _block(raw: dict, key: str) -> dict:
    """A nested block such as ``microphone``; anything but an object falls back whole."""
    value = raw.get(key, {})
    if isinstance(value, dict):
        return value
    log.warning("⚠️ config: recording.%s=%r is not an object; using the defaults", key, value)
    return {}


def options_from_dict(raw: Any) -> RecordingOptions:
    """Build options from the parsed ``recording`` block, falling back key by key."""
    base = RecordingOptions()
    if not isinstance(raw, dict):
        return base

    def checked(parse, key: str, default):
        if key not in raw:
            return default
        try:
            return parse(raw[key])
        except ValueError as exc:
            log.warning(
                "⚠️ config: recording.%s=%r invalid (%s); using %r", key, raw[key], exc, default
            )
            return default

    mic_raw = _block(raw, "microphone")
    sys_raw = _block(raw, "system_audio")
    return RecordingOptions(
        folder=_text(raw, "folder", base.folder),
        name_pattern=checked(validate_pattern, "name_pattern", base.name_pattern),
        container=_choice(raw, "container", CONTAINERS, base.container),
        quality=_choice(raw, "quality", QUALITIES, base.quality),
        bitrate_kbps=checked(parse_bitrate, "bitrate_kbps", base.bitrate_kbps),
        frame_rate=_choice(raw, "frame_rate", FRAME_RATES, base.frame_rate),
        screen=checked(parse_screen, "screen", base.screen),
        cursor=_flag(raw, "cursor", base.cursor),
        include_ink=_flag(raw, "include_ink", base.include_ink),
        microphone=Microphone(
            enabled=_flag(mic_raw, "enabled", False, "microphone.enabled"),
            device=_text(mic_raw, "device", "", "microphone.device"),
        ),
        system_audio=SystemAudio(
            enabled=_flag(sys_raw, "enabled", False, "system_audio.enabled"),
            device=_text(sys_raw, "device", "", "system_audio.device"),
        ),
        backend=_choice(raw, "backend", BACKENDS, base.backend),
        ffmpeg_path=_text(raw, "ffmpeg_path", base.ffmpeg_path),
    )


def options_to_dict(options: RecordingOptions) -> dict[str, Any]:
    return {
        "folder": options.folder,
        "name_pattern": options.name_pattern,
        "container": options.container,
        "quality": options.quality,
        "bitrate_kbps": options.bitrate_kbps,
        "frame_rate": options.frame_rate,
        "screen": options.screen,
        "cursor": options.cursor,
        "include_ink": options.include_ink,
        "microphone": {
            "enabled": options.microphone.enabled,
            "device": options.microphone.device,
        },
        "system_audio": {
            "enabled": options.system_audio.enabled,
            "device": options.system_audio.device,
        },
        "backend": options.backend,
        "ffmpeg_path": options.ffmpeg_path,
    }
