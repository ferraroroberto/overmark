"""Stroke model: what has been drawn, in global desktop coordinates, with undo.

No Qt here. The renderer reads this model and turns it into pixels, so a different
renderer can replace it without touching the model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from overmark import fade


class Tool(StrEnum):
    PEN = "pen"
    HIGHLIGHTER = "highlighter"
    ARROW = "arrow"
    TEXT = "text"


@dataclass(frozen=True)
class Style:
    color: str
    width_px: float  # capture pixels; for text, the font size
    alpha: float = 1.0
    outline_px: float = 0.0  # 0 means no outline
    outline_color: str = "#0B0B0B"


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    pressure: float = 1.0


Rect = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass(eq=False)
class Stroke:
    tool: Tool
    style: Style
    points: list[Point] = field(default_factory=list)
    text: str = ""
    finished_at: float | None = None
    pinned: bool = False
    # Text extent (width, height) measured by the renderer; strokes compute their own.
    text_extent: tuple[float, float] = (0.0, 0.0)

    def add_point(self, point: Point) -> None:
        if self.tool is Tool.ARROW and len(self.points) >= 2:
            self.points[-1] = point  # an arrow is only its tail and its tip
        else:
            self.points.append(point)

    @property
    def pad(self) -> float:
        """Half the drawn width including outline, plus the arrowhead reach."""
        reach = self.style.width_px / 2 + self.style.outline_px + 1
        if self.tool is Tool.ARROW:
            reach += arrow_head_length(self.style.width_px)
        return reach

    def bounds(self) -> Rect | None:
        if not self.points:
            return None
        if self.tool is Tool.TEXT:
            x, y = self.points[0].x, self.points[0].y
            w, h = self.text_extent
            o = self.style.outline_px + 2
            return (x - o, y - o, x + w + o, y + h + o)
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        pad = self.pad
        return (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    def hit(self, x: float, y: float, radius: float) -> bool:
        """True if a circle of ``radius`` at (x, y) touches the drawn stroke."""
        box = self.bounds()
        if box is None:
            return False
        if self.tool is Tool.TEXT:
            x0, y0, x1, y1 = box
            return x0 - radius <= x <= x1 + radius and y0 - radius <= y <= y1 + radius
        reach = radius + self.style.width_px / 2 + self.style.outline_px
        pts = self.points if self.tool is not Tool.ARROW else [self.points[0], self.points[-1]]
        if len(pts) == 1:
            return math.hypot(x - pts[0].x, y - pts[0].y) <= reach
        return any(
            _segment_distance(x, y, a, b) <= reach for a, b in zip(pts, pts[1:], strict=False)
        )


def arrow_head_length(width_px: float) -> float:
    return max(18.0, width_px * 4)


def _segment_distance(px: float, py: float, a: Point, b: Point) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - a.x, py - a.y)
    t = max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / length_sq))
    return math.hypot(px - (a.x + t * dx), py - (a.y + t * dy))


def union(a: Rect | None, b: Rect | None) -> Rect | None:
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


class Board:
    """All committed ink plus the stroke in progress, with an undo stack.

    Undo records operations, not snapshots: ``add`` (a stroke), ``erase`` (strokes
    removed by the eraser, with their positions) and ``clear`` (everything).
    """

    def __init__(self) -> None:
        self.strokes: list[Stroke] = []
        self._undo: list[tuple[str, list[tuple[int, Stroke]]]] = []

    def begin(self, stroke: Stroke) -> Stroke:
        self.strokes.append(stroke)
        return stroke

    def finish(self, stroke: Stroke, now: float) -> None:
        stroke.finished_at = now
        self._undo.append(("add", [(len(self.strokes) - 1, stroke)]))

    def cancel(self, stroke: Stroke) -> None:
        if stroke in self.strokes:
            self.strokes.remove(stroke)

    def undo(self, now: float) -> Rect | None:
        """Undo the last operation; return the area that changed, or None."""
        if not self._undo:
            return None
        kind, items = self._undo.pop()
        area: Rect | None = None
        if kind == "add":
            for _, stroke in items:
                if stroke in self.strokes:
                    self.strokes.remove(stroke)
                area = union(area, stroke.bounds())
        else:
            for index, stroke in sorted(items, key=lambda item: item[0]):
                stroke.finished_at = now  # restored ink gets a fresh fade delay
                self.strokes.insert(min(index, len(self.strokes)), stroke)
                area = union(area, stroke.bounds())
        return area

    def clear(self) -> bool:
        if not self.strokes:
            return False
        self._undo.append(("clear", list(enumerate(self.strokes))))
        self.strokes = []
        return True

    def erase_at(self, x: float, y: float, radius: float) -> list[Stroke]:
        hits = [
            (i, s)
            for i, s in enumerate(self.strokes)
            if s.finished_at is not None and s.hit(x, y, radius)
        ]
        if not hits:
            return []
        self._undo.append(("erase", hits))
        removed = {id(s) for _, s in hits}
        self.strokes = [s for s in self.strokes if id(s) not in removed]
        return [s for _, s in hits]

    def pin_all(self) -> int:
        count = 0
        for stroke in self.strokes:
            if not stroke.pinned:
                stroke.pinned = True
                count += 1
        return count

    def prune(self, now: float, *, enabled: bool, delay: float) -> list[Stroke]:
        """Drop fully faded strokes, and the undo entries that would only re-add them."""
        expired = [
            s
            for s in self.strokes
            if fade.is_expired(now, s.finished_at, enabled=enabled, delay=delay, pinned=s.pinned)
        ]
        if not expired:
            return []
        gone = {id(s) for s in expired}
        self.strokes = [s for s in self.strokes if id(s) not in gone]
        self._undo = [op for op in self._undo if not (op[0] == "add" and id(op[1][0][1]) in gone)]
        return expired

    def needs_fade_ticks(self, *, enabled: bool) -> bool:
        return any(
            fade.is_fading_or_waiting(s.finished_at, enabled=enabled, pinned=s.pinned)
            for s in self.strokes
        )

    def paint_order(self) -> list[Stroke]:
        """Highlighter strokes first, so pen ink and text stay on top of them."""
        low = [s for s in self.strokes if s.tool is Tool.HIGHLIGHTER]
        high = [s for s in self.strokes if s.tool is not Tool.HIGHLIGHTER]
        return low + high


class LaserTrail:
    """The laser dot and its short fading trail. Never stored on the board, never undone."""

    def __init__(self, trail_seconds: float = 0.25) -> None:
        self.trail_seconds = trail_seconds
        self._points: list[tuple[float, float, float]] = []

    def add(self, x: float, y: float, now: float) -> None:
        self._points.append((x, y, now))
        self._drop_old(now)

    def visible(self, now: float) -> list[tuple[float, float, float]]:
        """Return ``(x, y, age_fraction)`` from oldest to newest; 0 is the newest."""
        self._drop_old(now)
        return [(x, y, (now - t) / self.trail_seconds) for x, y, t in self._points]

    def head(self) -> tuple[float, float] | None:
        return (self._points[-1][0], self._points[-1][1]) if self._points else None

    def clear(self) -> None:
        self._points.clear()

    def _drop_old(self, now: float) -> None:
        cutoff = now - self.trail_seconds
        # Keep the newest point even when still: the dot stays while the trail fades.
        while len(self._points) > 1 and self._points[0][2] < cutoff:
            self._points.pop(0)
