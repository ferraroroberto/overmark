"""Where the toolbar sits: the screen-layout key, the default spot, keeping it on screen.

The point that is saved is the pill's top centre (the anchor), so the collapsed handle
and the expanded pill share one spot. Pure Python, no Qt.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

Point = tuple[int, int]


class Area(NamedTuple):
    """A screen rectangle in logical desktop coordinates."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, point: Point) -> bool:
        px, py = point
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def distance(self, point: Point) -> int:
        """Zero inside; otherwise how far outside, summed over both axes."""
        px, py = point
        dx = max(self.x - px, 0, px - (self.x + self.width - 1))
        dy = max(self.y - py, 0, py - (self.y + self.height - 1))
        return dx + dy


def _within(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))  # ``low`` wins when the window is wider than the area


def layout_key(screens: Sequence[Area]) -> str:
    """Name a monitor arrangement by its geometry only, in an order-independent way."""
    return ";".join(f"{a.x},{a.y},{a.width}x{a.height}" for a in sorted(screens))


def nearest(areas: Sequence[Area], point: Point) -> Area:
    return min(areas, key=lambda area: area.distance(point))


def resolve_anchor(
    saved: Point | None, areas: Sequence[Area], primary: Area, top_margin: int
) -> tuple[Point, Area]:
    """The saved anchor and its screen, or top centre of the primary if it is off screen."""
    if saved is not None:
        for area in areas:
            if area.contains(saved):
                return saved, area
    return (primary.x + (primary.width - 1) // 2, primary.y + top_margin), primary


def clamp_anchor(anchor: Point, area: Area, height: int) -> Point:
    """Pull a dropped anchor back so the pill's row stays on the screen."""
    return (
        _within(anchor[0], area.x, area.x + area.width - 1),
        _within(anchor[1], area.y, area.y + area.height - height),
    )


def top_left(anchor: Point, width: int, height: int, area: Area) -> Point:
    """The window position for a pill of this size: centred on the anchor, kept on screen."""
    return (
        _within(anchor[0] - width // 2, area.x, area.x + area.width - width),
        _within(anchor[1], area.y, area.y + area.height - height),
    )
