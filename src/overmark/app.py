"""Entry point: tray icon, global hotkey, one overlay per monitor, toolbar."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QPointF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from overmark import config as config_mod
from overmark import theme, win32
from overmark.config import Settings
from overmark.controller import Controller
from overmark.keepawake import POLL_MS, KeepAwakeEngine
from overmark.keymap import parse_hotkey
from overmark.overlay import OverlayWindow, screen_under_cursor
from overmark.settings_dialog import SettingsDialog
from overmark.toolbar import CheatSheet, Toolbar

log = logging.getLogger(__name__)

HOTKEY_ID = 0x4F4D  # any id unique within this process
ARMED_BADGE = "#1a7f37"  # fleet success green, readable on the accent circle


class HotkeyFilter(QAbstractNativeEventFilter):
    """Delivers WM_HOTKEY for our id to a callback."""

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt override)
        if (
            event_type == b"windows_generic_MSG"
            and win32.hotkey_id_from_msg(int(message)) == HOTKEY_ID
        ):
            self._callback()
            return True, 0
        return False, 0


def tray_icon(armed: bool = False) -> QIcon:
    """The app icon; a green badge in the corner shows keep-awake is armed."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.tokens()["accent_fill"]))
    painter.drawEllipse(2, 2, 60, 60)
    pen = QPen(QColor("#ffffff"), 7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(QPointF(19, 44), QPointF(44, 19))
    painter.drawPoint(QPointF(46, 46))
    if armed:
        painter.setPen(QPen(QColor("#ffffff"), 4))
        painter.setBrush(QColor(ARMED_BADGE))
        painter.drawEllipse(QPointF(50, 14), 11, 11)
    painter.end()
    return QIcon(pixmap)


class OvermarkApp:
    def __init__(self, qapp: QApplication, settings: Settings, config_path: Path) -> None:
        self.qapp = qapp
        self.controller = Controller(settings, config_path)
        self.overlays: list[OverlayWindow] = []
        self.toolbar = Toolbar(self.controller)
        self.cheat_sheet = CheatSheet(self.controller)
        self.settings_dialog: SettingsDialog | None = None
        self._previous_foreground = 0
        self._hotkey_registered: str | None = None

        self.hotkey_filter = HotkeyFilter(self.controller.toggle_draw)
        qapp.installNativeEventFilter(self.hotkey_filter)

        self.keep_awake = KeepAwakeEngine(
            hold_display=win32.hold_display_on,
            nudge=win32.nudge_pointer,
            idle=win32.idle_milliseconds,
            busy=lambda: self.controller.input_in_progress,
        )
        self._awake_timer = QTimer()
        self._awake_timer.setInterval(POLL_MS)
        self._awake_timer.timeout.connect(self.keep_awake.poll)

        c = self.controller
        c.settings_changed.connect(self.apply_keep_awake)
        c.mode_changed.connect(self.on_mode_changed)
        c.restore_focus_requested.connect(self.restore_focus)
        c.cheat_sheet_requested.connect(self.cheat_sheet.toggle)
        self.toolbar.settings_requested.connect(self.open_settings)
        qapp.screenAdded.connect(lambda _s: self.rebuild_overlays())
        qapp.screenRemoved.connect(lambda _s: self.rebuild_overlays())
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _s: self.apply_theme())

        self.tray = QSystemTrayIcon(tray_icon())
        self.tray.setToolTip("Overmark")
        self.tray.setContextMenu(self._build_menu())
        self.tray.activated.connect(self._on_tray_activated)

    def start(self) -> bool:
        self.apply_keep_awake()
        self.rebuild_overlays()
        self.toolbar.show()
        self.tray.show()
        if not self.register_hotkey(self.controller.settings.toggle_hotkey):
            self.tray.showMessage(
                "Overmark",
                f"The draw hotkey {self.controller.settings.toggle_hotkey.upper()} is taken; "
                "pick another in Settings.",
            )
        log.info("✅ Overmark running on %d screen(s)", len(self.overlays))
        return True

    # ----- overlays ---------------------------------------------------------------

    def screens(self) -> list[QScreen]:
        if self.controller.settings.cover_all_screens:
            return list(QGuiApplication.screens())
        return [QGuiApplication.primaryScreen()]

    def rebuild_overlays(self) -> None:
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays = [OverlayWindow(self.controller, s) for s in self.screens()]
        for overlay in self.overlays:
            overlay.show()
        self.toolbar.raise_above_overlays()
        log.info(
            "ℹ️ overlays on %s",
            ", ".join(f"{s.geometry().width()}x{s.geometry().height()}" for s in self.screens()),
        )

    def on_mode_changed(self, drawing: bool) -> None:
        self._update_menu()
        if drawing:
            self._previous_foreground = win32.foreground_window()
            target = next(
                (o for o in self.overlays if o.target_screen is screen_under_cursor()),
                self.overlays[0] if self.overlays else None,
            )
            if target is not None:
                target.raise_()
                target.activateWindow()
                target.setFocus()
            self.toolbar.raise_above_overlays()
            self.cheat_sheet.raise_above_overlays()

    def restore_focus(self) -> None:
        if self._previous_foreground:
            win32.set_foreground(self._previous_foreground)

    # ----- hotkey -------------------------------------------------------------------

    def register_hotkey(self, combo: str) -> bool:
        try:
            modifiers, vk = parse_hotkey(combo)
        except ValueError as exc:
            log.error("❌ draw hotkey %r invalid: %s", combo, exc)
            return False
        if self._hotkey_registered:
            win32.unregister_hotkey(HOTKEY_ID)
            self._hotkey_registered = None
        if not win32.register_hotkey(HOTKEY_ID, modifiers, vk):
            return False
        self._hotkey_registered = combo
        log.info("✅ draw hotkey %s registered", combo)
        return True

    # ----- settings -------------------------------------------------------------------

    def open_settings(self) -> None:
        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            return
        self.controller.set_drawing(False)
        self.settings_dialog = SettingsDialog(self.controller.settings, self.apply_settings)
        self.settings_dialog.show()
        self.settings_dialog.activateWindow()

    def apply_settings(self, new: Settings) -> str | None:
        """Apply and persist; return an error message (and change nothing) on failure."""
        old = self.controller.settings
        if new.toggle_hotkey != self._hotkey_registered and not self.register_hotkey(
            new.toggle_hotkey
        ):
            if old.toggle_hotkey:
                self.register_hotkey(old.toggle_hotkey)
            return f"{new.toggle_hotkey.upper()} is already used by another application."
        screens_changed = new.cover_all_screens != old.cover_all_screens
        self.controller.apply_settings(new)
        if screens_changed:
            self.rebuild_overlays()
        self._update_menu()
        return None

    def apply_keep_awake(self) -> None:
        """Push the keep-awake setting to the engine, the poll timer, the tray and its menu."""
        self.keep_awake.configure(self.controller.settings.keep_awake)
        if self.keep_awake.needs_polling:
            self._awake_timer.start()
        else:
            self._awake_timer.stop()
        armed = self.keep_awake.armed
        self.tray.setIcon(tray_icon(armed))
        self.tray.setToolTip("Overmark (keep-awake on)" if armed else "Overmark")
        self._update_menu()

    def apply_theme(self) -> None:
        self.toolbar.apply_theme()
        self.cheat_sheet.rebuild()
        self.tray.setIcon(tray_icon(self.keep_awake.armed))

    # ----- tray ----------------------------------------------------------------------

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        self.draw_action = QAction("Draw", menu, checkable=True)
        self.draw_action.triggered.connect(lambda _c: self.controller.toggle_draw())
        menu.addAction(self.draw_action)
        menu.addAction("Clear ink", self.controller.clear)
        self.awake_action = QAction("Keep display awake", menu, checkable=True)
        self.awake_action.triggered.connect(lambda _c: self.controller.toggle_keep_awake())
        menu.addAction(self.awake_action)
        menu.addAction("Cheat-sheet", self.cheat_sheet.toggle)
        menu.addAction("Settings…", self.open_settings)
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self._menu = menu
        self._update_menu()
        return menu

    def _update_menu(self) -> None:
        if hasattr(self, "draw_action"):
            self.draw_action.setChecked(self.controller.drawing)
            self.draw_action.setText(f"Draw ({self.controller.settings.toggle_hotkey.upper()})")
            self.awake_action.setChecked(self.controller.settings.keep_awake.enabled)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.controller.toggle_draw()

    def quit(self) -> None:
        self._awake_timer.stop()
        self.keep_awake.release()
        win32.unregister_hotkey(HOTKEY_ID)
        self.tray.hide()
        self.qapp.quit()


def setup_logging() -> Path:
    log_dir = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "overmark.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None:  # pythonw has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    return log_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="overmark", description="Screen annotation overlay.")
    parser.add_argument("--config", type=Path, default=config_mod.CONFIG_PATH, help="settings file")
    args = parser.parse_args(argv)

    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName("Overmark")
    qapp.setOrganizationName("Overmark")
    qapp.setQuitOnLastWindowClosed(False)
    log_file = setup_logging()
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8")
    log.info("ℹ️ logging to %s", log_file.name)

    settings = config_mod.load(args.config)
    app = OvermarkApp(qapp, settings, args.config)
    app.start()
    return qapp.exec()
