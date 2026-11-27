"""The running tray as the settings server's ``Backend``: every Qt call goes through the bridge."""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable

from PySide6.QtCore import QDir
from PySide6.QtWidgets import QFileDialog

from overmark import win32
from overmark.config import Settings
from overmark.recording.controls import list_microphones
from overmark.recording.loopback import list_loopback_devices
from overmark.recording.monitors import describe
from overmark.web.bridge import QtBridge

log = logging.getLogger(__name__)

PICK_TIMEOUT_S = 600.0  # the folder dialog waits on a person, not on the app


class QtBackend:
    """``read`` returns the live settings; ``apply`` is the tray's own ``apply_settings``."""

    def __init__(
        self,
        bridge: QtBridge,
        read: Callable[[], Settings],
        apply: Callable[[Settings], str | None],
    ) -> None:
        self._bridge = bridge
        self._read = read
        self._apply = apply

    def settings(self) -> Settings:
        return self._bridge.call(lambda: copy.deepcopy(self._read()))

    def apply(self, settings: Settings) -> str | None:
        return self._bridge.call(lambda: self._apply(settings))

    def microphones(self, ffmpeg_path: str) -> list[str]:
        # ffmpeg runs as a subprocess: no Qt, so the request thread waits on it, not the UI.
        return list_microphones(ffmpeg_path)

    def system_audio(self) -> list[str]:
        return self._bridge.call(list_loopback_devices)

    def screens(self) -> list[str]:
        return self._bridge.call(lambda: describe(win32.display_outputs()))

    def pick_folder(self, start: str) -> str | None:
        def choose() -> str | None:
            chosen = QFileDialog.getExistingDirectory(None, "Recording folder", start)
            return QDir.toNativeSeparators(chosen) if chosen else None

        folder = self._bridge.call(choose, timeout=PICK_TIMEOUT_S)
        log.info("ℹ️ recording folder dialog %s", "chose a folder" if folder else "cancelled")
        return folder
