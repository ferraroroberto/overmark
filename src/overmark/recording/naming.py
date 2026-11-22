"""File names: the name template, a never-overwrite rule, and the in-progress names."""

from __future__ import annotations

import re
import string
from datetime import datetime
from pathlib import Path

DEFAULT_PATTERN = "overmark-{date}-{time}-{screen}"
TOKENS = ("date", "time", "screen")
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_SUFFIX = 9999  # a folder holding 10,000 same-second files is a bug, not a use


def validate_pattern(pattern: object) -> str:
    """Return the pattern stripped; raise ``ValueError`` if it is not a usable template."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("Name pattern must not be empty")
    try:
        fields = [name for _, name, _, _ in string.Formatter().parse(pattern) if name is not None]
    except ValueError as exc:
        raise ValueError(f"Name pattern is not a valid template ({exc})") from None
    unknown = [name for name in fields if name not in TOKENS]
    if unknown:
        allowed = ", ".join("{" + t + "}" for t in TOKENS)
        raise ValueError(f"Name pattern has unknown token {{{unknown[0]}}}; use {allowed}")
    return pattern.strip()


def screen_token(screen: str | int) -> str:
    return f"screen{screen}" if isinstance(screen, int) else str(screen)


def render_name(pattern: str, when: datetime, screen: str | int) -> str:
    """Fill the template and make the result safe as a Windows file name (no extension)."""
    name = validate_pattern(pattern).format(
        date=when.strftime("%Y-%m-%d"),
        time=when.strftime("%H-%M-%S"),
        screen=screen_token(screen),
    )
    name = _ILLEGAL.sub("-", name).strip(" .")
    return name or "overmark"


def unique_path(folder: Path, stem: str, ext: str) -> Path:
    """``folder/stem.ext``, or ``stem-2.ext``, ``stem-3.ext`` ... if taken. Never overwrites.

    A name is also taken while its in-progress files exist, so two recordings started
    in the same second never share segments.
    """
    for n in range(1, MAX_SUFFIX + 1):
        candidate = stem if n == 1 else f"{stem}-{n}"
        final = folder / f"{candidate}.{ext}"
        if not final.exists() and not any(folder.glob(f".{glob_escape(candidate)}.part*")):
            return final
    raise FileExistsError(f"no free name for {stem!r} in the destination folder")


def glob_escape(text: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", text)


def segment_path(final: Path, index: int) -> Path:
    """The n-th in-progress segment: hidden-looking and plainly unfinished, always MKV.

    MKV survives a killed encoder (an MP4 without its index is unplayable), and the
    segments are joined into the chosen container only when recording stops cleanly.
    """
    return final.with_name(f".{final.stem}.part{index}.mkv")


def system_audio_path(segment: Path) -> Path:
    """The system-audio WAV captured beside a segment, as plainly unfinished as it."""
    return segment.with_suffix(".wav")


def joining_path(final: Path) -> Path:
    """Where the joined file is written before its rename to ``final``."""
    return final.with_name(f".{final.stem}.part.{final.suffix.lstrip('.')}")
