"""Monitors in physical desktop pixels, the screen choice, and the composed canvas."""

from __future__ import annotations

from dataclasses import dataclass

from overmark.recording.options import SCREEN_ACTIVE, SCREEN_ALL


@dataclass(frozen=True)
class Monitor:
    """One display output. ``dda_index`` is ffmpeg's ``ddagrab`` ``output_idx``.

    ``ddagrab`` only reaches the outputs of the default graphics adapter; a monitor
    on another adapter has ``dda_index=None`` and is captured with ``gdigrab``.
    """

    name: str
    x: int
    y: int
    width: int
    height: int
    dda_index: int | None = None

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


def numbered(monitors: list[Monitor]) -> list[Monitor]:
    """Screens in the order the user numbers them: left to right, then top to bottom."""
    return sorted(monitors, key=lambda m: (m.x, m.y))


def describe(monitors: list[Monitor]) -> list[str]:
    """One label per numbered screen, for the settings screen picker."""
    return [
        f"Screen {n}: {m.width}×{m.height} at {m.x}, {m.y}"
        for n, m in enumerate(numbered(monitors), start=1)
    ]


def select(
    monitors: list[Monitor], screen: str | int, pointer: tuple[int, int] | None
) -> list[Monitor]:
    """The monitors a recording covers; raise ``ValueError`` if the choice cannot be met."""
    if not monitors:
        raise ValueError("Windows reports no monitors")
    ordered = numbered(monitors)
    if screen == SCREEN_ALL:
        return ordered
    if screen == SCREEN_ACTIVE:
        if pointer is not None:
            for monitor in ordered:
                if monitor.contains(*pointer):
                    return [monitor]
        return [ordered[0]]
    if isinstance(screen, int) and 1 <= screen <= len(ordered):
        return [ordered[screen - 1]]
    raise ValueError(f"screen {screen} is not connected; Windows reports {len(ordered)}")


def bounding_box(monitors: list[Monitor]) -> tuple[int, int, int, int]:
    """``(x, y, width, height)`` of the smallest rectangle holding every monitor."""
    left = min(m.x for m in monitors)
    top = min(m.y for m in monitors)
    right = max(m.x + m.width for m in monitors)
    bottom = max(m.y + m.height for m in monitors)
    return left, top, right - left, bottom - top
