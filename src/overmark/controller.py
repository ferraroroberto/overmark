"""Drawing state shared by every overlay window: mode, tool, preset, board, laser."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QTimer, Signal

from overmark import config as config_mod
from overmark.config import Preset, Settings
from overmark.keymap import KeyMap
from overmark.presets import PresetCycler, style_for
from overmark.render import laser_rect, measure_text, to_qrect
from overmark.strokes import Board, LaserTrail, Point, Rect, Stroke, Style, Tool, union

log = logging.getLogger(__name__)

FRAME_MS = 16  # about 60 Hz while something animates (fade, laser trail)
ESC_GRACE_MS = 1000  # after Esc, a second Esc within this window clears the ink
ERASER_RADIUS_PX = 12.0
TOOL_ACTIONS = {
    "pen": Tool.PEN,
    "highlighter": Tool.HIGHLIGHTER,
    "arrow": Tool.ARROW,
    "text": Tool.TEXT,
}


class Controller(QObject):
    # A changed area in global coordinates; an invalid (null) rect means "everything".
    changed = Signal(QRectF)
    mode_changed = Signal(bool)
    tool_changed = Signal()
    laser_changed = Signal(bool)
    cheat_sheet_requested = Signal()
    settings_changed = Signal()
    restore_focus_requested = Signal()

    def __init__(self, settings: Settings, config_path: Path = config_mod.CONFIG_PATH) -> None:
        super().__init__()
        self.settings = settings
        self.config_path = config_path
        self.board = Board()
        self.laser = LaserTrail()
        self.cycler = PresetCycler(len(settings.presets))
        self.keymap = KeyMap(settings.keys)
        self.tool = Tool.PEN
        self.drawing = False
        self.laser_active = False
        self.editing: Stroke | None = None
        self._active: Stroke | None = None
        self._session_started = 0.0
        self._session_strokes = 0
        self._esc_armed = False
        self._laser_area: Rect | None = None

        self._ticker = QTimer(self)
        self._ticker.setInterval(FRAME_MS)
        self._ticker.timeout.connect(self._tick)
        self._esc_timer = QTimer(self)
        self._esc_timer.setSingleShot(True)
        self._esc_timer.setInterval(ESC_GRACE_MS)
        self._esc_timer.timeout.connect(self._end_esc_grace)

    # ----- mode -----------------------------------------------------------------

    def toggle_draw(self) -> None:
        self.set_drawing(not self.drawing)

    def set_drawing(self, on: bool, *, hold_focus: bool = False) -> None:
        """Switch mode. Leaving draw mode hands focus back unless ``hold_focus``."""
        if on == self.drawing:
            return
        self._esc_timer.stop()
        self._esc_armed = False
        if not on:
            self._commit_text()
            self._finish_active()
            self.set_laser(False)
            log.info(
                "ℹ️ draw session: overlay shown %.1f s, %d strokes",
                time.monotonic() - self._session_started,
                self._session_strokes,
            )
        else:
            self._session_started = time.monotonic()
            self._session_strokes = 0
        self.drawing = on
        self.mode_changed.emit(on)
        self.changed.emit(QRectF())
        if not on and not hold_focus:
            self.restore_focus_requested.emit()

    @property
    def input_in_progress(self) -> bool:
        """A stroke is being drawn, a label typed or the laser held: the pointer must stay put."""
        return self._active is not None or self.editing is not None or self.laser_active

    def toggle_keep_awake(self) -> None:
        """Flip keep-awake on or off from the tray or toolbar and persist it."""
        self.settings.keep_awake.enabled = not self.settings.keep_awake.enabled
        config_mod.save(self.settings, self.config_path)
        self.settings_changed.emit()

    def set_toolbar_position(self, layout: str, anchor: tuple[int, int]) -> None:
        """Remember where the toolbar was dragged to under this screen layout."""
        self.settings.toolbar_positions[layout] = anchor
        try:
            config_mod.save(self.settings, self.config_path)
        except OSError as exc:
            log.warning("⚠️ toolbar position not saved (%s); it lasts until the app closes", exc)
            return
        log.info("ℹ️ toolbar moved to %d,%d", *anchor)

    # ----- tools and presets ------------------------------------------------------

    def set_tool(self, tool: Tool) -> None:
        if tool is not Tool.TEXT:
            self._commit_text()
        self.tool = tool
        self.tool_changed.emit()

    def select_preset(self, index: int) -> None:
        if self.cycler.select(index):
            self._restyle_editing()
            self.tool_changed.emit()

    def step_preset(self, delta: int) -> None:
        self.cycler.step(delta)
        self._restyle_editing()
        self.tool_changed.emit()

    @property
    def preset(self) -> Preset:
        return self.settings.presets[self.cycler.index]

    def style(self, tool: Tool) -> Style:
        return style_for(tool, self.preset, self.settings.sizes)

    def set_laser(self, on: bool) -> None:
        if on == self.laser_active:
            return
        self.laser_active = on
        if not on:
            self.laser.clear()
            self._refresh_laser()
        self.laser_changed.emit(on)
        self._update_ticker()

    # ----- pointer input (global logical coordinates) ------------------------------

    def pointer_down(self, x: float, y: float, pressure: float = 1.0, erase: bool = False) -> None:
        if not self.drawing:
            return
        if erase:
            self.erase(x, y)
            return
        if self.laser_active:
            return
        if self.tool is Tool.TEXT:
            self._commit_text()
            stroke = Stroke(Tool.TEXT, self.style(Tool.TEXT), [Point(x, y)])
            stroke.text_extent = measure_text("", stroke.style.width_px)
            self.editing = self.board.begin(stroke)
            self._emit_area(stroke.bounds())
            return
        self._commit_text()
        point = Point(x, y, pressure)
        points = [point, point] if self.tool is Tool.ARROW else [point]
        self._active = self.board.begin(Stroke(self.tool, self.style(self.tool), points))
        self._emit_area(self._active.bounds())

    def pointer_move(self, x: float, y: float, pressure: float = 1.0, erase: bool = False) -> None:
        if not self.drawing:
            return
        if self.laser_active:
            self.laser.add(x, y, time.monotonic())
            self._refresh_laser()
            return
        if erase:
            self.erase(x, y)
            return
        stroke = self._active
        if stroke is None:
            return
        before = stroke.bounds()
        last = stroke.points[-1]
        stroke.add_point(Point(x, y, pressure))
        if stroke.tool is Tool.ARROW:
            self._emit_area(union(before, stroke.bounds()))
        else:
            pad = stroke.pad
            x0, x1 = min(last.x, x), max(last.x, x)
            y0, y1 = min(last.y, y), max(last.y, y)
            self._emit_area((x0 - pad, y0 - pad, x1 + pad, y1 + pad))

    def pointer_up(self) -> None:
        self._finish_active()

    def erase(self, x: float, y: float) -> None:
        area: Rect | None = None
        for stroke in self.board.erase_at(x, y, ERASER_RADIUS_PX):
            area = union(area, stroke.bounds())
        self._emit_area(area)

    # ----- commands -----------------------------------------------------------------

    def undo(self) -> None:
        if self.editing is not None:
            self._cancel_text()
            return
        self._emit_area(self.board.undo(time.monotonic()))
        self._update_ticker()

    def clear(self) -> None:
        self._cancel_text()
        if self.board.clear():
            self.changed.emit(QRectF())

    def pin(self) -> None:
        pinned = self.board.pin_all()
        log.info("ℹ️ pinned %d strokes", pinned)
        self._update_ticker()

    # ----- keyboard (only while the overlay has focus) --------------------------------

    def handle_key(self, combo: str, text: str, pressed: bool, repeat: bool) -> bool:
        """Handle one key event; return True if it was used."""
        action = self.keymap.action_for(combo)
        if not pressed:
            if action == "laser" and not repeat:
                self.set_laser(False)
                return True
            return False

        if self.editing is not None:
            return self._edit_text_key(combo, text)

        if action == "exit":
            if self._esc_armed:
                self._esc_timer.stop()
                self._esc_armed = False
                self.clear()
                self.restore_focus_requested.emit()
            elif self.drawing:
                self.set_drawing(False, hold_focus=True)
                self._esc_armed = True
                self._esc_timer.start()
            return True
        if self._esc_armed:
            # Any other key after Esc belongs to the application underneath.
            self._end_esc_grace()
            return False
        if not self.drawing or repeat:
            return action is not None
        if action in TOOL_ACTIONS:
            self.set_tool(TOOL_ACTIONS[action])
        elif action == "laser":
            self.set_laser(True)
        elif action == "undo":
            self.undo()
        elif action == "clear":
            self.clear()
        elif action == "pin":
            self.pin()
        elif action == "cheat_sheet":
            self.cheat_sheet_requested.emit()
        elif action and action.startswith("preset_"):
            self.select_preset(int(action.removeprefix("preset_")) - 1)
        else:
            return False
        return True

    def _edit_text_key(self, combo: str, text: str) -> bool:
        stroke = self.editing
        assert stroke is not None
        before = stroke.bounds()
        if combo == "esc":
            self._cancel_text()
            return True
        if combo == "enter":
            self._commit_text()
            return True
        if combo == "shift+enter":
            stroke.text += "\n"
        elif combo == "backspace":
            stroke.text = stroke.text[:-1]
        elif combo == "ctrl+z":
            self._cancel_text()
            return True
        elif text and text.isprintable() and not combo.startswith(("ctrl+", "alt+")):
            stroke.text += text
        else:
            return False
        stroke.text_extent = measure_text(stroke.text, stroke.style.width_px)
        self._emit_area(union(before, stroke.bounds()))
        return True

    # ----- settings ---------------------------------------------------------------------

    def apply_settings(self, settings: Settings) -> None:
        # Settings edits an earlier copy; a drag made since then must survive its save.
        settings.toolbar_positions = self.settings.toolbar_positions
        self.settings = settings
        self.keymap = KeyMap(settings.keys)
        self.cycler = PresetCycler(len(settings.presets), self.cycler.index)
        config_mod.save(settings, self.config_path)
        self.settings_changed.emit()
        self.tool_changed.emit()
        self._update_ticker()
        self.changed.emit(QRectF())

    # ----- internals ----------------------------------------------------------------------

    def _finish_active(self) -> None:
        stroke = self._active
        if stroke is None:
            return
        self._active = None
        self.board.finish(stroke, time.monotonic())
        self._session_strokes += 1
        self._update_ticker()

    def _commit_text(self) -> None:
        stroke = self.editing
        if stroke is None:
            return
        self.editing = None
        if stroke.text.strip():
            self.board.finish(stroke, time.monotonic())
            self._session_strokes += 1
            self._update_ticker()
        else:
            self.board.cancel(stroke)
        self._emit_area(stroke.bounds())

    def _cancel_text(self) -> None:
        stroke = self.editing
        if stroke is None:
            return
        self.editing = None
        self.board.cancel(stroke)
        self._emit_area(stroke.bounds())

    def _restyle_editing(self) -> None:
        if self.editing is not None:
            self.editing.style = self.style(Tool.TEXT)
            self._emit_area(self.editing.bounds())

    def _end_esc_grace(self) -> None:
        if self._esc_armed:
            self._esc_armed = False
            self.restore_focus_requested.emit()

    def _refresh_laser(self) -> None:
        """Repaint where the laser is now and where it was, so no trail is left behind."""
        now_area = laser_rect(self.laser, self.settings.sizes, time.monotonic())
        self._emit_area(union(self._laser_area, now_area))
        self._laser_area = now_area

    def _emit_area(self, area: Rect | None) -> None:
        if area is not None:
            self.changed.emit(to_qrect(area))

    def _update_ticker(self) -> None:
        fade_on = self.settings.fade.enabled
        needed = self.laser_active or self.board.needs_fade_ticks(enabled=fade_on)
        if needed and not self._ticker.isActive():
            self._ticker.start()
        elif not needed and self._ticker.isActive():
            self._ticker.stop()

    def _tick(self) -> None:
        now = time.monotonic()
        fade_cfg = self.settings.fade
        area: Rect | None = None
        for stroke in self.board.strokes:
            if stroke.finished_at is None or stroke.pinned or not fade_cfg.enabled:
                continue
            if now - stroke.finished_at >= fade_cfg.delay_seconds:
                area = union(area, stroke.bounds())
        for stroke in self.board.prune(now, enabled=fade_cfg.enabled, delay=fade_cfg.delay_seconds):
            area = union(area, stroke.bounds())
        self._emit_area(area)
        if self.laser_active:
            self._refresh_laser()
        self._update_ticker()
