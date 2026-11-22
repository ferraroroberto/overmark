"""Lucide glyphs rendered to Qt icons, tinted from the design tokens."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from overmark import glyphs, theme


def paint(
    painter: QPainter,
    name: str,
    color: str,
    rect: QRectF,
    stroke_width: float = glyphs.STROKE_WIDTH,
) -> None:
    """Draw glyph ``name`` into ``rect`` (the glyph's 24x24 box scales to fit)."""
    renderer = QSvgRenderer(QByteArray(glyphs.svg(name, color, stroke_width).encode()))
    renderer.render(painter, rect)


def pixmap(name: str, color: str, size: int) -> QPixmap:
    """A transparent ``size`` px square pixmap of the glyph, sharp at the screen's scale."""
    ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.instance() else 1
    image = QPixmap(round(size * ratio), round(size * ratio))
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint(painter, name, color, QRectF(0, 0, size, size))
    painter.end()
    return image


def icon(
    name: str,
    t: dict[str, str],
    size: int = theme.ICON_TOOLBAR,
    *,
    rest: str = "fg_muted",
    on: str = "accent_text",
) -> QIcon:
    """The icon-button glyph: muted at rest, ``fg`` on hover, ``on`` while checked.

    The tint carries every state; the button itself stays unpainted.
    """
    result = QIcon()
    off, hover, checked = (pixmap(name, t[key], size) for key in (rest, "fg", on))
    result.addPixmap(off, QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(hover, QIcon.Mode.Active, QIcon.State.Off)
    result.addPixmap(checked, QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(checked, QIcon.Mode.Active, QIcon.State.On)
    result.addPixmap(off, QIcon.Mode.Disabled, QIcon.State.Off)
    return result
