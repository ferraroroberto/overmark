"""The renderer boundary: stroke model in, pixels out.

Everything that turns ``strokes.Stroke`` into pixels lives here, so a different
renderer (for example a native one) replaces this module and nothing else.
Coordinates in the model are global desktop logical pixels; widths are capture
pixels, divided by the screen's device pixel ratio so they look the same in a
recording on every monitor.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

from overmark import fade
from overmark.config import Fade, Sizes
from overmark.strokes import LaserTrail, Point, Rect, Stroke, Tool, arrow_head_length

PRESSURE_FLOOR = 0.35  # the lightest pen touch still draws a readable line
ARROW_HEAD_DEGREES = 28
TEXT_FONT_FAMILY = "Segoe UI"
LASER_COLOR = "#FF2BD6"


def to_qrect(rect: Rect) -> QRectF:
    return QRectF(QPointF(rect[0], rect[1]), QPointF(rect[2], rect[3]))


def text_font(size_px: float, dpr: float) -> QFont:
    font = QFont(TEXT_FONT_FAMILY)
    font.setPixelSize(max(1, round(size_px / dpr)))
    font.setWeight(QFont.Weight.Bold)
    return font


def measure_text(text: str, size_px: float) -> tuple[float, float]:
    """Width and height of a label at device pixel ratio 1, for bounds and hit tests."""
    metrics = QFontMetricsF(text_font(size_px, 1.0))
    lines = (text or " ").split("\n")
    return max(metrics.horizontalAdvance(line) for line in lines), metrics.height() * len(lines)


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, max(width, 0.5))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _polyline(points: list[Point], origin: QPointF) -> QPainterPath:
    path = QPainterPath(QPointF(points[0].x, points[0].y) - origin)
    if len(points) == 1:
        path.lineTo(path.currentPosition() + QPointF(0.01, 0))  # a dot still paints
    for p in points[1:]:
        path.lineTo(QPointF(p.x, p.y) - origin)
    return path


def _arrow_path(stroke: Stroke, origin: QPointF, dpr: float) -> QPainterPath:
    tail, tip = stroke.points[0], stroke.points[-1]
    a = QPointF(tail.x, tail.y) - origin
    b = QPointF(tip.x, tip.y) - origin
    path = QPainterPath(a)
    path.lineTo(b)
    length = arrow_head_length(stroke.style.width_px) / dpr
    angle = math.atan2(b.y() - a.y(), b.x() - a.x())
    if math.hypot(b.x() - a.x(), b.y() - a.y()) > 1:
        for side in (-1, 1):
            theta = angle + math.pi - side * math.radians(ARROW_HEAD_DEGREES)
            path.moveTo(b)
            path.lineTo(b + QPointF(math.cos(theta) * length, math.sin(theta) * length))
    return path


def _draw_body(painter: QPainter, stroke: Stroke, origin: QPointF, dpr: float) -> None:
    """Draw one stroke fully opaque; the caller applies transparency and fading."""
    style = stroke.style
    color = QColor(style.color)
    outline = QColor(style.outline_color)
    width = style.width_px / dpr
    ring = style.outline_px / dpr

    if stroke.tool is Tool.TEXT:
        if not stroke.text:
            return
        font = text_font(style.width_px, dpr)
        metrics = QFontMetricsF(font)
        path = QPainterPath()
        top = QPointF(stroke.points[0].x, stroke.points[0].y) - origin
        for i, line in enumerate(stroke.text.split("\n")):
            path.addText(top + QPointF(0, metrics.ascent() + i * metrics.height()), font, line)
        if ring > 0:
            painter.strokePath(path, _pen(outline, ring * 2))
        painter.fillPath(path, color)
        return

    if stroke.tool is Tool.ARROW:
        path = _arrow_path(stroke, origin, dpr)
        if ring > 0:
            painter.strokePath(path, _pen(outline, width + ring * 2))
        painter.strokePath(path, _pen(color, width))
        return

    points = stroke.points
    varies = stroke.tool is Tool.PEN and any(p.pressure != points[0].pressure for p in points)
    if not varies:
        path = _polyline(points, origin)
        cap_width = (
            width * _pressure_scale(points[0].pressure) if stroke.tool is Tool.PEN else width
        )
        if stroke.tool is Tool.HIGHLIGHTER:
            pen = _pen(color, cap_width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.strokePath(path, pen)
            return
        if ring > 0:
            painter.strokePath(path, _pen(outline, cap_width + ring * 2))
        painter.strokePath(path, _pen(color, cap_width))
        return

    # Pressure varies: draw segment by segment, all outline first so it never covers ink.
    segments = list(zip(points, points[1:], strict=False))
    for layer_color, extra in ((outline, ring * 2), (color, 0.0)):
        if layer_color is outline and ring <= 0:
            continue
        for a, b in segments:
            seg_width = width * _pressure_scale((a.pressure + b.pressure) / 2) + extra
            painter.setPen(_pen(layer_color, seg_width))
            painter.drawLine(QPointF(a.x, a.y) - origin, QPointF(b.x, b.y) - origin)


def _pressure_scale(pressure: float) -> float:
    return PRESSURE_FLOOR + (1 - PRESSURE_FLOOR) * min(max(pressure, 0.0), 1.0)


class Renderer:
    """Paints the board onto one overlay window."""

    def __init__(self) -> None:
        self._scratch: QImage | None = None

    def paint(
        self,
        painter: QPainter,
        strokes: list[Stroke],
        *,
        origin: QPointF,
        dpr: float,
        clip: QRect,
        now: float,
        fade_cfg: Fade,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        global_clip = QRectF(clip).translated(origin)
        for stroke in strokes:
            box = stroke.bounds()
            if box is None or not to_qrect(box).intersects(global_clip):
                continue
            opacity = stroke.style.alpha * fade.opacity(
                now,
                stroke.finished_at,
                enabled=fade_cfg.enabled,
                delay=fade_cfg.delay_seconds,
                pinned=stroke.pinned,
            )
            if opacity <= 0:
                continue
            if opacity >= 1:
                _draw_body(painter, stroke, origin, dpr)
            else:
                self._draw_translucent(painter, stroke, origin, dpr, clip, opacity)

    def _draw_translucent(
        self,
        painter: QPainter,
        stroke: Stroke,
        origin: QPointF,
        dpr: float,
        clip: QRect,
        opacity: float,
    ) -> None:
        """Draw opaque into a scratch layer, then blend it once.

        Blending each part separately would let the outline and self-overlaps show
        through translucent ink as darker patches.
        """
        area = to_qrect(stroke.bounds()).translated(-origin).toAlignedRect().intersected(clip)
        if area.isEmpty():
            return
        scale = painter.device().devicePixelRatioF() if painter.device() else 1.0
        w, h = math.ceil(area.width() * scale), math.ceil(area.height() * scale)
        scratch = self._scratch
        if scratch is None or scratch.width() < w or scratch.height() < h:
            scratch = QImage(max(w, 256), max(h, 256), QImage.Format.Format_ARGB32_Premultiplied)
            self._scratch = scratch
        scratch.setDevicePixelRatio(scale)
        scratch.fill(Qt.GlobalColor.transparent)
        layer = QPainter(scratch)
        layer.setRenderHint(QPainter.RenderHint.Antialiasing)
        _draw_body(layer, stroke, origin + QPointF(area.topLeft()), dpr)
        layer.end()
        painter.save()
        painter.setOpacity(opacity)
        painter.drawImage(
            QRectF(area), scratch, QRectF(0, 0, area.width() * scale, area.height() * scale)
        )
        painter.restore()


def laser_rect(trail: LaserTrail, sizes: Sizes, now: float) -> Rect | None:
    pts = trail.visible(now)
    if not pts:
        return None
    reach = sizes.laser_dot_px / 2 + sizes.laser_halo_px + 2
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)


def paint_laser(
    painter: QPainter, trail: LaserTrail, *, origin: QPointF, dpr: float, sizes: Sizes, now: float
) -> None:
    pts = trail.visible(now)
    if not pts:
        return
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    dot = sizes.laser_dot_px / dpr
    halo = sizes.laser_halo_px / dpr
    core = QColor(LASER_COLOR)
    for (x0, y0, _), (x1, y1, age) in zip(pts, pts[1:], strict=False):
        trail_color = QColor(core)
        trail_color.setAlphaF(max(0.0, 0.7 * (1 - age)))
        painter.setPen(_pen(trail_color, dot * 0.6 * (1 - age) + 1))
        painter.drawLine(QPointF(x0, y0) - origin, QPointF(x1, y1) - origin)
    hx, hy, _ = pts[-1]
    centre = QPointF(hx, hy) - origin
    glow = QColor(core)
    glow.setAlphaF(0.35)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(centre, dot / 2 + halo, dot / 2 + halo)
    painter.setBrush(core)
    painter.drawEllipse(centre, dot / 2, dot / 2)
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawEllipse(centre, dot / 6, dot / 6)
