"""Fade timing: how opaque a finished stroke is at a given moment."""

from __future__ import annotations

FADE_OUT_SECONDS = 0.6


def opacity(
    now: float,
    finished_at: float | None,
    *,
    enabled: bool,
    delay: float,
    pinned: bool = False,
    duration: float = FADE_OUT_SECONDS,
) -> float:
    """Return 1.0 until ``delay`` seconds after the stroke ends, then ease out to 0.0.

    A stroke still being drawn (``finished_at`` is None), a pinned stroke, or any
    stroke while fading is off stays fully opaque.
    """
    if not enabled or pinned or finished_at is None:
        return 1.0
    elapsed = now - finished_at - delay
    if elapsed <= 0:
        return 1.0
    if elapsed >= duration:
        return 0.0
    progress = elapsed / duration
    eased = 1.0 - (1.0 - progress) ** 3  # ease-out: most of the drop happens early
    return 1.0 - eased


def is_expired(
    now: float,
    finished_at: float | None,
    *,
    enabled: bool,
    delay: float,
    pinned: bool = False,
) -> bool:
    return opacity(now, finished_at, enabled=enabled, delay=delay, pinned=pinned) <= 0.0


def is_fading_or_waiting(finished_at: float | None, *, enabled: bool, pinned: bool = False) -> bool:
    """True while a stroke will still change opacity, so the fade timer must run."""
    return enabled and not pinned and finished_at is not None
