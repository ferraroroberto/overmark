"""The floating toolbar pill and the cheat-sheet, both hidden from screen capture."""

from __future__ import annotations

import logging

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from overmark import theme, win32
from overmark.controller import Controller
from overmark.keymap import ACTION_LABELS
from overmark.strokes import Tool

log = logging.getLogger(__name__)

COLLAPSE_DELAY_MS = 700  # long enough to cross a gap between pill and pointer
TOP_MARGIN = 12
_FLAGS = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool
    | Qt.WindowType.WindowDoesNotAcceptFocus
    | Qt.WindowType.NoDropShadowWindowHint
)


class CaptureHidden(QWidget):
    """A top-most window that never takes focus and never appears in a capture."""

    def __init__(self) -> None:
        super().__init__(None, _FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        hwnd = int(self.winId())
        win32.set_no_activate(hwnd)
        if not win32.exclude_from_capture(hwnd):
            log.warning("⚠️ %s could not be excluded from capture", type(self).__name__)
        win32.bring_to_top(hwnd)

    def raise_above_overlays(self) -> None:
        if self.isVisible():
            win32.bring_to_top(int(self.winId()))


class _Swatch(QToolButton):
    def __init__(self, index: int) -> None:
        super().__init__()
        self.index = index
        self.color = QColor("#ffffff")
        self.selected = False
        self.setFixedSize(QSize(30, 36))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = theme.tokens()
        r = 9 if self.selected else 7
        centre = QRectF(self.rect()).center()
        if self.selected:
            painter.setPen(QPen(QColor(t["accent"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, r + 4, r + 4)
        painter.setPen(QPen(QColor(t["control_border"]), 1))
        painter.setBrush(self.color)
        painter.drawEllipse(centre, r, r)


class Toolbar(CaptureHidden):
    settings_requested = Signal()

    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self.controller = controller
        self.expanded = False
        self.setWindowTitle("Overmark toolbar")

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(COLLAPSE_DELAY_MS)
        self._collapse_timer.timeout.connect(self.collapse)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(2)

        self.handle = self._button("✎", "Overmark: hover or click to expand", self.expand)
        row.addWidget(self.handle)

        self.panel = QWidget()
        panel_row = QHBoxLayout(self.panel)
        panel_row.setContentsMargins(0, 0, 0, 0)
        panel_row.setSpacing(2)
        self.draw_button = self._button("Draw", "Toggle drawing", controller.toggle_draw)
        self.draw_button.setObjectName("drawToggle")
        self.draw_button.setCheckable(True)
        self.draw_button.setMinimumWidth(56)
        panel_row.addWidget(self.draw_button)

        self.tool_buttons: dict[Tool, QToolButton] = {}
        for tool, glyph, tip in (
            (Tool.PEN, "✏", "Pen (P)"),
            (Tool.HIGHLIGHTER, "▮", "Highlighter (H)"),
            (Tool.ARROW, "➚", "Arrow (A)"),
            (Tool.TEXT, "T", "Text label (T)"),
        ):
            button = self._button(glyph, tip, lambda _=False, t=tool: controller.set_tool(t))
            button.setCheckable(True)
            self.tool_buttons[tool] = button
            panel_row.addWidget(button)

        self.swatches: list[_Swatch] = []
        for i in range(len(controller.settings.presets)):
            swatch = _Swatch(i)
            swatch.clicked.connect(lambda _=False, n=i: controller.select_preset(n))
            self.swatches.append(swatch)
            panel_row.addWidget(swatch)

        for glyph, tip, slot in (
            ("↶", "Undo (Ctrl+Z)", controller.undo),
            ("⌫", "Clear (E)", controller.clear),
            ("📌", "Pin ink so it stops fading (F)", controller.pin),
        ):
            panel_row.addWidget(self._button(glyph, tip, slot))
        self.awake_button = self._button("☀", "", controller.toggle_keep_awake)
        self.awake_button.setCheckable(True)
        panel_row.addWidget(self.awake_button)
        for glyph, tip, slot in (
            ("?", "Cheat-sheet (?)", controller.cheat_sheet_requested.emit),
            ("⚙", "Settings", self.settings_requested.emit),
        ):
            panel_row.addWidget(self._button(glyph, tip, slot))
        row.addWidget(self.panel)
        self.panel.hide()

        controller.mode_changed.connect(lambda _on: self.refresh())
        controller.tool_changed.connect(self.refresh)
        controller.settings_changed.connect(self.refresh)
        self.apply_theme()
        self.refresh()

    def _button(self, glyph: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(glyph)
        button.setToolTip(tip)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def apply_theme(self) -> None:
        self.setStyleSheet(theme.stylesheet(theme.tokens()))
        self.update()

    def refresh(self) -> None:
        c = self.controller
        self.draw_button.setChecked(c.drawing)
        for tool, button in self.tool_buttons.items():
            button.setChecked(tool is c.tool)
        for swatch in self.swatches:
            preset = c.settings.presets[swatch.index]
            swatch.color = QColor(preset.color)
            swatch.selected = swatch.index == c.cycler.index
            swatch.setToolTip(f"{swatch.index + 1}: {preset.name}")
            swatch.update()
        armed = c.settings.keep_awake.enabled
        self.awake_button.setChecked(armed)
        self.awake_button.setToolTip(f"Keep display awake: {'on' if armed else 'off'}")
        self.handle.setToolTip(
            f"Overmark: {c.settings.toggle_hotkey.upper()} toggles drawing; hover to expand"
            + ("; keep-awake on" if armed else "")
        )
        self._place()

    def _place(self) -> None:
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(QPoint(screen.center().x() - self.width() // 2, screen.top() + TOP_MARGIN))

    # ----- collapse / expand -----------------------------------------------------

    def expand(self) -> None:
        self._collapse_timer.stop()
        if not self.expanded:
            self.expanded = True
            self.handle.hide()
            self.panel.show()
            self._place()

    def collapse(self) -> None:
        if self.expanded:
            self.expanded = False
            self.panel.hide()
            self.handle.show()
            self._place()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._collapse_timer.start()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt override)
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta:
            self.controller.step_preset(-1 if delta > 0 else 1)
        event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.setBrush(QColor(t["card"]))
        radius = rect.height() / 2  # pill
        painter.drawRoundedRect(rect, radius, radius)


class CheatSheet(CaptureHidden):
    """The key list, opened from the toolbar or with ``?``; any click closes it."""

    def __init__(self, controller: Controller) -> None:
        super().__init__()
        self.controller = controller
        self.setObjectName("cheatSheet")
        self.setWindowTitle("Overmark keys")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 20, 24, 20)
        self._grid_host = QWidget()
        self._layout.addWidget(self._grid_host)
        controller.settings_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        self.setStyleSheet(theme.stylesheet(theme.tokens()))
        old = self._grid_host
        self._grid_host = QWidget()
        grid = QGridLayout(self._grid_host)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        heading = QLabel("Overmark keys")
        heading.setObjectName("heading")
        grid.addWidget(heading, 0, 0, 1, 2)
        settings = self.controller.settings
        rows = [
            (settings.toggle_hotkey.upper(), "Toggle drawing (anywhere)"),
            (settings.record_hotkey.upper(), "Start / stop recording (anywhere)"),
            (settings.pause_hotkey.upper(), "Pause / resume recording (anywhere)"),
        ]
        rows += [
            (combo.upper(), ACTION_LABELS[a])
            for a, combo in self.controller.keymap.bindings.items()
        ]
        rows += [
            ("Wheel on toolbar", "Next / previous preset"),
            ("Pen eraser end", "Erase strokes"),
        ]
        for i, (key, label) in enumerate(rows, start=1):
            key_label = QLabel(key)
            key_label.setStyleSheet("font-weight: 600;")
            text = QLabel(label)
            text.setObjectName("muted")
            grid.addWidget(key_label, i, 0)
            grid.addWidget(text, i, 1)
        note = QLabel("Keys work while drawing. Click to close.")
        note.setObjectName("note")
        grid.addWidget(note, len(rows) + 1, 0, 1, 2)
        self._layout.replaceWidget(old, self._grid_host)
        old.deleteLater()
        self.adjustSize()

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.rebuild()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())
        self.show()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        t = theme.tokens()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(t["border"]), 1))
        painter.setBrush(QColor(t["card"]))
        painter.drawRoundedRect(rect, 16, 16)
