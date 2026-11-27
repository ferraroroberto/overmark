"""Entry point: tray icon, global hotkey, one overlay per monitor, toolbar."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import webbrowser
from collections.abc import Callable
from functools import partial
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QPointF, QRectF, QStandardPaths, QTimer
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from overmark import config as config_mod
from overmark import icons, theme, win32
from overmark._vendored.single_instance import SingleInstance
from overmark.buildprobe import read_git_sha, started_at
from overmark.config import PRESET_COUNT, Settings
from overmark.controller import Controller
from overmark.keepawake import POLL_MS, KeepAwakeEngine
from overmark.keymap import parse_hotkey
from overmark.overlay import OverlayWindow, screen_under_cursor
from overmark.recording.controls import RecordingControls
from overmark.recording.segments import State
from overmark.toolbar import CheatSheet, Toolbar
from overmark.web.bridge import QtBridge
from overmark.web.qt_backend import QtBackend
from overmark.web.server import WebServer, create_app

log = logging.getLogger(__name__)

# The checkout root (src/overmark/app.py is two levels below it); the build probe reads its HEAD.
REPO_ROOT = Path(__file__).resolve().parents[2]
# Session-wide named mutex behind the single-instance guard.
INSTANCE_MUTEX = "Global\\overmark-tray"

# Any ids unique within this process.
DRAW_HOTKEY_ID = 0x4F4D
RECORD_HOTKEY_ID = 0x4F4E
PAUSE_HOTKEY_ID = 0x4F4F
PRESET_HOTKEY_IDS = tuple(range(0x4F50, 0x4F50 + PRESET_COUNT))
HOTKEY_LABELS = {
    DRAW_HOTKEY_ID: "Draw",
    RECORD_HOTKEY_ID: "Start/stop recording",
    PAUSE_HOTKEY_ID: "Pause recording",
    **{hotkey_id: f"Preset {n}" for n, hotkey_id in enumerate(PRESET_HOTKEY_IDS, 1)},
}
TRAY_SIZES = (16, 20, 24, 32, 40, 48, 64)  # Windows picks per DPI; small sizes stay crisp


class HotkeyFilter(QAbstractNativeEventFilter):
    """Delivers WM_HOTKEY for each of our ids to its callback."""

    def __init__(self, callbacks: dict[int, Callable[[], None]]) -> None:
        super().__init__()
        self._callbacks = callbacks

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt override)
        if event_type == b"windows_generic_MSG":
            callback = self._callbacks.get(win32.hotkey_id_from_msg(int(message)))
            if callback is not None:
                callback()
                return True, 0
        return False, 0


def tray_icon(armed: bool = False) -> QIcon:
    """The fleet brand tile (Lucide master, light on dark); a badge shows keep-awake is armed."""
    result = QIcon()
    for size in TRAY_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(theme.BRAND_TILE))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = size * theme.BRAND_PAD
        box = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
        icons.paint(painter, theme.BRAND_GLYPH, theme.BRAND_STROKE, box, theme.BRAND_STROKE_WIDTH)
        if armed:
            # Bottom-right, a corner the diagonal pencil leaves empty, ringed in the tile colour.
            radius = size * 0.2
            centre = size - radius - size * 0.03
            painter.setPen(QPen(QColor(theme.BRAND_TILE), size * 0.06))
            painter.setBrush(QColor(theme.BRAND_BADGE_ON))
            painter.drawEllipse(QPointF(centre, centre), radius, radius)
        painter.end()
        result.addPixmap(pixmap)
    return result


def menu_icon(name: str) -> QIcon:
    """A tray-menu glyph at the inline size, in the theme's text colour."""
    return QIcon(icons.pixmap(name, theme.tokens()["fg"], theme.ICON_INLINE))


class OvermarkApp:
    def __init__(self, qapp: QApplication, settings: Settings, config_path: Path) -> None:
        self.qapp = qapp
        self.controller = Controller(settings, config_path)
        self.overlays: list[OverlayWindow] = []
        self.toolbar = Toolbar(self.controller)
        self.cheat_sheet = CheatSheet(self.controller)
        self.settings_url: str | None = None  # set once the settings server is serving
        self._previous_foreground = 0
        self._hotkeys: dict[int, str] = {}  # id to the combo registered for it

        self.recording = RecordingControls(lambda: self.controller.settings, self.hide_ink)
        self.recording.notify.connect(lambda text: self.tray.showMessage("Overmark", text))
        self.recording.state_changed.connect(self._update_menu)

        self.hotkey_filter = HotkeyFilter(
            {
                DRAW_HOTKEY_ID: self.controller.toggle_draw,
                RECORD_HOTKEY_ID: self.recording.toggle,
                PAUSE_HOTKEY_ID: self.recording.toggle_pause,
                **{
                    hotkey_id: partial(self.controller.draw_with_preset, index)
                    for index, hotkey_id in enumerate(PRESET_HOTKEY_IDS)
                },
            }
        )
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
        qapp.screenAdded.connect(self._on_screen_added)
        qapp.screenRemoved.connect(lambda _s: self.rebuild_overlays())
        for screen in QGuiApplication.screens():
            self._follow_screen(screen)
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
        self.register_startup_hotkeys()
        log.info("✅ Overmark running on %d screen(s)", len(self.overlays))
        return True

    # ----- overlays ---------------------------------------------------------------

    def screens(self) -> list[QScreen]:
        if self.controller.settings.cover_all_screens:
            return list(QGuiApplication.screens())
        return [QGuiApplication.primaryScreen()]

    def _follow_screen(self, screen: QScreen) -> None:
        # A resolution or arrangement change can leave the toolbar's spot off screen.
        screen.geometryChanged.connect(lambda _g: self.toolbar.place())

    def _on_screen_added(self, screen: QScreen) -> None:
        self._follow_screen(screen)
        self.rebuild_overlays()

    def rebuild_overlays(self) -> None:
        for overlay in self.overlays:
            overlay.close()
            overlay.deleteLater()
        self.overlays = [OverlayWindow(self.controller, s) for s in self.screens()]
        for overlay in self.overlays:
            overlay.show()
            if self.recording.ink_hidden:
                win32.set_capture_excluded(overlay.hwnd(), True)
        self.toolbar.place()
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

    def hide_ink(self, hidden: bool) -> None:
        """Take the ink out of the capture (or back in) for the length of a recording."""
        for overlay in self.overlays:
            if not win32.set_capture_excluded(overlay.hwnd(), hidden):
                log.warning("⚠️ ink capture exclusion not confirmed on one screen")
        log.info("ℹ️ ink %s the recording", "hidden from" if hidden else "back in")

    def restore_focus(self) -> None:
        if self._previous_foreground:
            win32.set_foreground(self._previous_foreground)

    # ----- hotkey -------------------------------------------------------------------

    @staticmethod
    def wanted_hotkeys(settings: Settings) -> dict[int, str]:
        """Id to combo for every hotkey the settings define; an unset preset has none."""
        presets = zip(PRESET_HOTKEY_IDS, settings.preset_hotkeys, strict=True)
        return {
            DRAW_HOTKEY_ID: settings.toggle_hotkey,
            RECORD_HOTKEY_ID: settings.record_hotkey,
            PAUSE_HOTKEY_ID: settings.pause_hotkey,
            **{hotkey_id: combo for hotkey_id, combo in presets if combo},
        }

    def register_startup_hotkeys(self) -> None:
        """Register every hotkey; one notice names all the refused ones, so none hides another."""
        refused = [
            f"{HOTKEY_LABELS[hotkey_id]} ({combo.upper()})"
            for hotkey_id, combo in self.wanted_hotkeys(self.controller.settings).items()
            if not self.register_hotkey(hotkey_id, combo)
        ]
        if refused:
            self.tray.showMessage(
                "Overmark",
                f"Hotkey not registered: {', '.join(refused)}. Pick another in Settings.",
            )

    def register_hotkey(self, hotkey_id: int, combo: str) -> bool:
        label = HOTKEY_LABELS[hotkey_id]
        try:
            modifiers, vk = parse_hotkey(combo)
        except ValueError as exc:
            log.error("❌ %s hotkey %r invalid: %s", label, combo, exc)
            return False
        self.unregister_hotkey(hotkey_id)
        if not win32.register_hotkey(hotkey_id, modifiers, vk):
            log.warning("⚠️ %s hotkey %s not registered: Windows refused it", label, combo)
            return False
        self._hotkeys[hotkey_id] = combo
        log.info("✅ %s hotkey %s registered", label, combo)
        return True

    def unregister_hotkey(self, hotkey_id: int) -> None:
        if self._hotkeys.pop(hotkey_id, None) is not None:
            win32.unregister_hotkey(hotkey_id)

    # ----- settings -------------------------------------------------------------------

    def open_settings(self) -> None:
        """Open the settings page in the browser; drawing stops so the browser takes input."""
        self.controller.set_drawing(False)
        if self.settings_url is None:
            self.tray.showMessage(
                "Overmark", "Settings are unavailable: the settings server did not start."
            )
            return
        if not webbrowser.open(self.settings_url):
            log.warning("⚠️ no browser opened %s", self.settings_url)
            self.tray.showMessage("Overmark", f"Open {self.settings_url} in a browser.")

    def apply_settings(self, new: Settings) -> str | None:
        """Apply and persist; return an error message (and change nothing) on failure."""
        old = self.controller.settings
        before, after = self.wanted_hotkeys(old), self.wanted_hotkeys(new)
        # Not registered as the save wants it: edited, cleared, or refused earlier.
        changed = [i for i in HOTKEY_LABELS if self._hotkeys.get(i) != after.get(i)]
        # Release every changed combo first, so two of our hotkeys can swap keys.
        for hotkey_id in changed:
            self.unregister_hotkey(hotkey_id)
        for hotkey_id in changed:
            combo = after.get(hotkey_id)
            if combo is None or self.register_hotkey(hotkey_id, combo):
                continue
            if combo == before.get(hotkey_id):
                continue  # refused before this save too: it must not block an unrelated one
            for undo_id in changed:
                self.unregister_hotkey(undo_id)
            for undo_id in changed:
                if undo_id in before:
                    self.register_hotkey(undo_id, before[undo_id])
            return f"{combo.upper()} is already used by another application."
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
        self._theme_menu()

    # ----- tray ----------------------------------------------------------------------

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        self.draw_action = QAction("Draw", menu, checkable=True)
        self.draw_action.triggered.connect(lambda _c: self.controller.toggle_draw())
        menu.addAction(self.draw_action)
        clear_action = menu.addAction("Clear ink", self.controller.clear)
        self.awake_action = QAction("Keep display awake", menu, checkable=True)
        self.awake_action.triggered.connect(lambda _c: self.controller.toggle_keep_awake())
        menu.addAction(self.awake_action)
        self.record_action = QAction("Start recording", menu)
        self.record_action.triggered.connect(lambda _c: self.recording.toggle())
        menu.addAction(self.record_action)
        self.pause_action = QAction("Pause recording", menu)
        self.pause_action.triggered.connect(lambda _c: self.recording.toggle_pause())
        menu.addAction(self.pause_action)
        keys_action = menu.addAction("Cheat-sheet", self.cheat_sheet.toggle)
        settings_action = menu.addAction("Settings…", self.open_settings)
        menu.addSeparator()
        quit_action = menu.addAction("Quit", self.quit)
        # Fixed glyphs; the record and pause glyphs follow the recording state.
        self._menu_glyphs = {
            self.draw_action: theme.BRAND_GLYPH,
            clear_action: "trash-2",
            self.awake_action: "sun",
            keys_action: "keyboard",
            settings_action: "settings",
            quit_action: "power",
        }
        self._menu = menu
        self._theme_menu()
        return menu

    def _theme_menu(self) -> None:
        self._menu.setStyleSheet(theme.stylesheet(theme.tokens()))
        for action, glyph in self._menu_glyphs.items():
            action.setIcon(menu_icon(glyph))
        self._update_menu()

    def _update_menu(self) -> None:
        if hasattr(self, "draw_action"):
            self.draw_action.setChecked(self.controller.drawing)
            self.draw_action.setText(f"Draw ({self.controller.settings.toggle_hotkey.upper()})")
            self.awake_action.setChecked(self.controller.settings.keep_awake.enabled)
            settings = self.controller.settings
            state = self.recording.state
            idle = state is State.IDLE
            self.record_action.setText(
                f"{'Start' if idle else 'Stop'} recording ({settings.record_hotkey.upper()})"
            )
            self.record_action.setEnabled(not self.recording.busy)
            self.record_action.setIcon(menu_icon("circle" if idle else "square"))
            self.pause_action.setIcon(menu_icon("play" if state is State.PAUSED else "pause"))
            self.pause_action.setText(
                f"{'Resume' if state is State.PAUSED else 'Pause'} recording "
                f"({settings.pause_hotkey.upper()})"
            )
            self.pause_action.setEnabled(not idle and not self.recording.busy)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.controller.toggle_draw()

    def quit(self) -> None:
        self._awake_timer.stop()
        self.keep_awake.release()
        self.recording.shutdown()
        for hotkey_id in list(self._hotkeys):
            self.unregister_hotkey(hotkey_id)
        self.tray.hide()
        self.qapp.quit()


def data_dir() -> Path:
    """This user's app-data folder: the log and the restart record, never the checkout."""
    folder = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    )
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def setup_logging() -> Path:
    log_file = data_dir() / "overmark.log"
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

    # Held for the life of the process: the OS drops the name when the process ends.
    guard = SingleInstance(INSTANCE_MUTEX)
    if not guard.acquired:
        log.warning("⚠️ Overmark is already running; this second start stands down")
        return 0

    settings = config_mod.load(args.config)
    app = OvermarkApp(qapp, settings, args.config)
    app.start()
    server = start_settings_server(app)
    qapp.aboutToQuit.connect(server.stop)
    return qapp.exec()


def start_settings_server(app: OvermarkApp) -> WebServer:
    """Serve the settings page, ``/api/version`` and the restart on loopback port 8467."""
    bridge = QtBridge()  # created here, on the Qt thread, which runs its calls
    backend = QtBackend(bridge, lambda: app.controller.settings, app.apply_settings)
    web_app = create_app(
        backend,
        git_sha=read_git_sha(REPO_ROOT),
        built_at=started_at(),
        pid=os.getpid(),
        restart_dir=data_dir() / "restart",
    )
    server = WebServer(web_app)
    if server.start():
        app.settings_url = server.url
    return server
