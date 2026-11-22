"""One transparent, top-most overlay window per monitor.

All windows paint the same board in global coordinates, so a stroke started on one
monitor continues onto the next: Qt keeps delivering moves to the window that saw
the press, and positions are taken in global coordinates.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QScreen,
    QTabletEvent,
)
from PySide6.QtWidgets import QWidget

from overmark import render, win32
from overmark.controller import Controller

log = logging.getLogger(__name__)

# Alpha 1 of 255 is invisible but keeps the window hit-testable in draw mode;
# fully transparent pixels of a layered window let clicks fall through.
HIT_TEST_FILL = QColor(0, 0, 0, 1)

_NAMED_KEYS = {
    Qt.Key.Key_Escape: "esc",
    Qt.Key.Key_Return: "enter",
    Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Backspace: "backspace",
    Qt.Key.Key_Question: "?",
    Qt.Key.Key_Space: "space",
}


def key_combo(event: QKeyEvent) -> str:
    """Build a keymap combo string (``"ctrl+z"``) from a Qt key event."""
    key = Qt.Key(event.key())
    if key in _NAMED_KEYS:
        name = _NAMED_KEYS[key]
    elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        name = chr(key.value).lower()
    elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        name = f"f{key.value - Qt.Key.Key_F1.value + 1}"
    else:
        name = event.text().lower() or f"key{key.value}"
    mods = event.modifiers()
    parts = []
    if mods & Qt.KeyboardModifier.ControlModifier:
        parts.append("ctrl")
    if mods & Qt.KeyboardModifier.AltModifier:
        parts.append("alt")
    # Shift is part of punctuation like "?" itself; only letters and named keys keep it.
    if mods & Qt.KeyboardModifier.ShiftModifier and (name.isalpha() or name == "enter"):
        parts.append("shift")
    return "+".join([*parts, name])


class OverlayWindow(QWidget):
    def __init__(self, controller: Controller, screen: QScreen) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.controller = controller
        self.renderer = render.Renderer()
        self._screen = screen
        self._pen_down = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle("Overmark ink")
        self.fit_screen()
        screen.geometryChanged.connect(self.fit_screen)

        controller.changed.connect(self.on_changed)
        controller.mode_changed.connect(self.on_mode_changed)
        controller.laser_changed.connect(lambda _on: self._update_cursor())

    @property
    def target_screen(self) -> QScreen:
        return self._screen

    def fit_screen(self) -> None:
        self.setScreen(self._screen)
        self.setGeometry(self._screen.geometry())

    def hwnd(self) -> int:
        return int(self.winId())

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        self.apply_mode()

    def apply_mode(self) -> None:
        ok = win32.set_click_through(self.hwnd(), not self.controller.drawing)
        if not ok:
            log.warning("⚠️ click-through toggle not confirmed on %s", self._screen.name())
        self._update_cursor()

    def on_mode_changed(self, drawing: bool) -> None:
        self.apply_mode()
        self.update()

    def on_changed(self, area: QRectF) -> None:
        if area.isNull():
            self.update()
            return
        local = area.translated(-QPointF(self.geometry().topLeft())).toAlignedRect()
        local = local.intersected(self.rect())
        if not local.isEmpty():
            self.update(local)

    def _update_cursor(self) -> None:
        if self.controller.laser_active:
            self.setCursor(Qt.CursorShape.BlankCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    # ----- painting -----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        clip = event.rect()
        if self.controller.drawing:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(clip, HIT_TEST_FILL)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        origin = QPointF(self.geometry().topLeft())
        dpr = self.devicePixelRatioF()
        now = time.monotonic()
        settings = self.controller.settings
        self.renderer.paint(
            painter,
            self.controller.board.paint_order(),
            origin=origin,
            dpr=dpr,
            clip=clip,
            now=now,
            fade_cfg=settings.fade,
        )
        if self.controller.laser_active:
            render.paint_laser(
                painter,
                self.controller.laser,
                origin=origin,
                dpr=dpr,
                sizes=settings.sizes,
                now=now,
            )
        painter.end()

    # ----- pointer input ----------------------------------------------------------

    def tabletEvent(self, event: QTabletEvent) -> None:  # noqa: N802 (Qt override)
        pos = event.globalPosition()
        erase = event.pointerType() == event.pointerType().Eraser or bool(
            event.buttons() & (Qt.MouseButton.RightButton | Qt.MouseButton.MiddleButton)
        )
        pressure = event.pressure() if event.pressure() > 0 else 1.0
        kind = event.type()
        if kind == QEvent.Type.TabletPress:
            self._pen_down = True
            self.controller.pointer_down(pos.x(), pos.y(), pressure, erase)
        elif kind == QEvent.Type.TabletMove:
            if self._pen_down or self.controller.laser_active:
                self.controller.pointer_move(pos.x(), pos.y(), pressure, erase)
        elif kind == QEvent.Type.TabletRelease:
            self._pen_down = False
            self.controller.pointer_up()
        event.accept()  # no synthesised mouse event: the pen path is complete on its own

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.globalPosition()
            self.controller.pointer_down(pos.x(), pos.y())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        pos = event.globalPosition()
        if event.buttons() & Qt.MouseButton.LeftButton or self.controller.laser_active:
            self.controller.pointer_move(pos.x(), pos.y())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.pointer_up()

    # ----- keyboard (only reaches us while we hold focus) ----------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        combo = key_combo(event)
        if not self.controller.handle_key(combo, event.text(), True, event.isAutoRepeat()):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        combo = key_combo(event)
        if not self.controller.handle_key(combo, event.text(), False, event.isAutoRepeat()):
            super().keyReleaseEvent(event)


def screen_under_cursor() -> QScreen:
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
