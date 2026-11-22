"""The chrome takes every colour from the token module and every icon from Lucide."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from overmark import glyphs, theme  # noqa: E402

SRC = Path(__file__).resolve().parents[1] / "src" / "overmark"
CHROME = [
    SRC / "app.py",
    SRC / "toolbar.py",
    SRC / "settings_dialog.py",
    SRC / "icons.py",
    SRC / "glyphs.py",
    SRC / "recording" / "indicator.py",
]
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
# Every glyph the toolbar, tray menu, settings window and recording chip draw.
USED = [
    theme.BRAND_GLYPH,
    "highlighter",
    "arrow-up-right",
    "type",
    "rotate-ccw",
    "trash-2",
    "pin",
    "sun",
    "keyboard",
    "settings",
    "power",
    "circle",
    "square",
    "pause",
    "play",
    "video",
    "folder",
]


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_light_and_dark_define_the_same_tokens() -> None:
    assert theme.LIGHT.keys() == theme.DARK.keys()


@pytest.mark.parametrize("path", CHROME, ids=lambda p: p.name)
def test_chrome_holds_no_colour_literal(path: Path) -> None:
    assert HEX.findall(path.read_text("utf-8")) == []


@pytest.mark.parametrize("name", USED)
def test_every_used_glyph_renders(name: str) -> None:
    renderer = QSvgRenderer(QByteArray(glyphs.svg(name, "#000000").encode()))
    assert renderer.isValid()


def test_unknown_glyph_names_the_glyph() -> None:
    with pytest.raises(KeyError, match="no-such-glyph"):
        glyphs.svg("no-such-glyph", "#000000")


def test_tray_icon_is_the_brand_tile_with_a_keep_awake_badge(qapp: QApplication) -> None:
    from overmark.app import tray_icon

    size = 64
    plain = tray_icon(armed=False).pixmap(size, size).toImage()
    armed = tray_icon(armed=True).pixmap(size, size).toImage()
    assert plain.pixelColor(1, 1) == QColor(theme.BRAND_TILE)
    badge = round(size * 0.77)  # inside the bottom-right badge
    assert plain.pixelColor(badge, badge) == QColor(theme.BRAND_TILE)
    assert armed.pixelColor(badge, badge) == QColor(theme.BRAND_BADGE_ON)
