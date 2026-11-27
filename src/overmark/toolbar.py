"""The floating toolbar pill and the cheat-sheet, both hidden from screen capture."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from overmark import icons, placement, theme, win32
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


def _area(rect: QRect) -> placement.Area:
    return placement.Area(rect.x(), rect.y(), rect.width(), rect.height())


def _available_areas() -> list[placement.Area]:
    return [_area(screen.availableGeometry()) for screen in QGuiApplication.screens()]


def _layout_key() -> str:
    # Full geometry, not the available part: moving the taskbar is not a new layout.
    return placement.layout_key([_area(s.geometry()) for s in QGuiApplication.screens()])


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
        self.color = QColor()  # the preset's ink colour, set by Toolbar.refresh
        self.selected = False
        self.setFixedSize(QSize(theme.HIT_TARGET, theme.HIT_TARGET))
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
        self.dragging = False
        self._press: QPoint | None = None  # pointer at a left press that may become a drag
        self._grab = QPoint()  # that pointer relative to the window

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(COLLAPSE_DELAY_MS)
        self._collapse_timer.timeout.connect(self.collapse)

        row = QHBoxLayout(self)
        row.setContentsMargins(theme.SPACE_SM, theme.SPACE_XS, theme.SPACE_SM, theme.SPACE_XS)
        row.setSpacing(0)

        self._glyphs: dict[QToolButton, str] = {}
        self.handle = self._button(
            theme.BRAND_GLYPH, "Overmark: hover or click to expand", self.expand
        )
        row.addWidget(self.handle)

        self.panel = QWidget()
        panel_row = QHBoxLayout(self.panel)
        panel_row.setContentsMargins(0, 0, 0, 0)
        panel_row.setSpacing(0)
        self.draw_button = QToolButton()
        self.draw_button.setText("Draw")
        self.draw_button.setToolTip("Toggle drawing")
        self.draw_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.draw_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.draw_button.clicked.connect(controller.toggle_draw)
        self.draw_button.setObjectName("drawToggle")
        self.draw_button.setCheckable(True)
        panel_row.addWidget(self.draw_button)

        self.tool_buttons: dict[Tool, QToolButton] = {}
        for tool, glyph, tip in (
            (Tool.PEN, "pencil", "Pen (P)"),
            (Tool.HIGHLIGHTER, "highlighter", "Highlighter (H)"),
            (Tool.ARROW, "arrow-up-right", "Arrow (A)"),
            (Tool.TEXT, "type", "Text label (T)"),
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
            ("rotate-ccw", "Undo (Ctrl+Z)", controller.undo),
            ("trash-2", "Clear (E)", controller.clear),
            ("pin", "Pin ink so it stops fading (F)", controller.pin),
        ):
            panel_row.addWidget(self._button(glyph, tip, slot))
        self.awake_button = self._button("sun", "", controller.toggle_keep_awake)
        self.awake_button.setCheckable(True)
        panel_row.addWidget(self.awake_button)
        for glyph, tip, slot in (
            ("keyboard", "Cheat-sheet (?)", controller.cheat_sheet_requested.emit),
            ("settings", "Settings", self.settings_requested.emit),
        ):
            panel_row.addWidget(self._button(glyph, tip, slot))
        row.addWidget(self.panel)
        self.panel.hide()
        # The buttons cover nearly all of the pill, so a drag may start on any of them.
        for button in self.findChildren(QAbstractButton):
            button.installEventFilter(self)

        controller.mode_changed.connect(lambda _on: self.refresh())
        controller.tool_changed.connect(self.refresh)
        controller.settings_changed.connect(self.refresh)
        self.apply_theme()
        self.refresh()

    def _button(self, glyph: str, tip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setAutoRaise(True)  # hover tints the glyph through the icon's Active mode
        button.setIconSize(QSize(theme.ICON_TOOLBAR, theme.ICON_TOOLBAR))
        button.setToolTip(tip)
        self._glyphs[button] = glyph
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def apply_theme(self) -> None:
        t = theme.tokens()
        self.setStyleSheet(theme.stylesheet(t))
        for button, glyph in self._glyphs.items():
            button.setIcon(icons.icon(glyph, t))
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
        self.place()

    # ----- position and drag -----------------------------------------------------

    def place(self) -> None:
        """Size to the content, then sit at this screen layout's saved spot or the default."""
        self.adjustSize()
        if self.dragging:
            return  # the pointer owns the position until the drop
        saved = self.controller.settings.toolbar_positions.get(_layout_key())
        primary = _area(QGuiApplication.primaryScreen().availableGeometry())
        anchor, area = placement.resolve_anchor(saved, _available_areas(), primary, TOP_MARGIN)
        self.move(QPoint(*placement.top_left(anchor, self.width(), self.height(), area)))

    def _drag(self, event: QMouseEvent) -> bool:
        """Feed one mouse event to the drag; True once the event belongs to a drag.

        A press that stays within the system drag distance is left alone, so it still clicks.
        """
        kind = event.type()
        left = Qt.MouseButton.LeftButton
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == left:
                self._press = event.globalPosition().toPoint()
                self._grab = self._press - self.pos()
                self.dragging = False
            return False
        if self._press is None:
            return False
        pointer = event.globalPosition().toPoint()
        if kind == QEvent.Type.MouseMove and event.buttons() & left:
            if not self.dragging:
                if (pointer - self._press).manhattanLength() < QApplication.startDragDistance():
                    return False
                self.dragging = True
                self._collapse_timer.stop()
            self.move(pointer - self._grab)
            return True
        if kind == QEvent.Type.MouseButtonRelease and event.button() == left:
            self._press = None
            if self.dragging:
                self.dragging = False
                self._drop(pointer)
                return True
        return False

    def _drop(self, pointer: QPoint) -> None:
        """Keep the spot where the pill was let go, on the screen under the pointer."""
        area = placement.nearest(_available_areas(), (pointer.x(), pointer.y()))
        dropped = (self.x() + self.width() // 2, self.y())
        anchor = placement.clamp_anchor(dropped, area, self.height())
        self.controller.set_toolbar_position(_layout_key(), anchor)
        self.place()
        self.raise_above_overlays()
        if not self.geometry().contains(QCursor.pos()):
            self._collapse_timer.start()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt override)
        if isinstance(event, QMouseEvent) and self._drag(event):
            watched.setDown(False)  # a drag is not a click
            return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        self._drag(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        self._drag(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt override)
        self._drag(event)

    # ----- collapse / expand -----------------------------------------------------

    def expand(self) -> None:
        self._collapse_timer.stop()
        if not self.expanded:
            self.expanded = True
            self.handle.hide()
            self.panel.show()
            self.place()

    def collapse(self) -> None:
        if self.expanded and not self.dragging:
            self.expanded = False
            self.panel.hide()
            self.handle.show()
            self.place()

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
        self._layout.setContentsMargins(
            theme.SPACE_LG, theme.SPACE_MD, theme.SPACE_LG, theme.SPACE_MD
        )
        self._grid_host = QWidget()
        self._layout.addWidget(self._grid_host)
        controller.settings_changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self) -> None:
        self.setStyleSheet(theme.stylesheet(theme.tokens()))
        old = self._grid_host
        self._grid_host = QWidget()
        grid = QGridLayout(self._grid_host)
        grid.setHorizontalSpacing(theme.SPACE_LG)
        grid.setVerticalSpacing(theme.SPACE_SM)
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
            key_label.setObjectName("key")
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
        painter.drawRoundedRect(rect, theme.RADIUS_LG, theme.RADIUS_LG)
