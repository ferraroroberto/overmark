"""Start, pause and stop from hotkeys and the tray; ffmpeg work runs off the UI thread."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal

from overmark import win32
from overmark.config import Settings
from overmark.recording.command import capture_plans
from overmark.recording.devices import (
    FFMPEG_DOWNLOAD_URL,
    EncoderPicker,
    encoder_test_command,
    find_ffmpeg,
    list_devices_command,
    parse_audio_devices,
)
from overmark.recording.indicator import RecordingIndicator
from overmark.recording.monitors import Monitor, numbered, select
from overmark.recording.naming import render_name, unique_path
from overmark.recording.options import SCREEN_ALL
from overmark.recording.segments import State
from overmark.recording.session import NO_WINDOW, Outcome, Recorder

log = logging.getLogger(__name__)

TICK_MS = 500
PROBE_TIMEOUT_S = 15.0  # one ffmpeg encode or device listing; a hung driver must not hang us
SHUTDOWN_WAIT_S = 60.0


def default_folder() -> Path:
    movies = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
    return Path(movies or Path.home() / "Videos") / "Overmark"


def _run_quiet(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, timeout=PROBE_TIMEOUT_S, creationflags=NO_WINDOW, check=False
    )


def list_microphones(ffmpeg_path: str) -> list[str]:
    """DirectShow audio devices, or an empty list when ffmpeg is missing or fails."""
    ffmpeg = find_ffmpeg(ffmpeg_path)
    if ffmpeg is None:
        return []
    try:
        done = _run_quiet(list_devices_command(ffmpeg))
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("⚠️ listing audio devices failed: %s", exc)
        return []
    return parse_audio_devices(done.stderr.decode("utf-8", errors="replace"))


class RecordingControls(QObject):
    """Owns at most one recording. ``hide_ink(True)`` takes the ink out of the capture."""

    state_changed = Signal()
    notify = Signal(str)
    _finished = Signal(str, object)  # (operation, result or exception), worker to UI thread

    def __init__(self, settings: Callable[[], Settings], hide_ink: Callable[[bool], None]) -> None:
        super().__init__()
        self._settings = settings
        self._hide_ink = hide_ink
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="overmark-rec")
        self._pickers: dict[str, EncoderPicker] = {}
        self._recorder: Recorder | None = None  # UI thread's view, set when "start" reports
        self._live: Recorder | None = None  # worker thread's view: an ffmpeg may be running
        self._busy = False
        self._ink_hidden = False
        self._screen_label = SCREEN_ALL
        self._indicator_monitor: Monitor | None = None
        self.indicator = RecordingIndicator()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._finished.connect(self._on_finished)

    @property
    def state(self) -> State:
        return self._recorder.state if self._recorder is not None else State.IDLE

    @property
    def busy(self) -> bool:
        return self._busy

    # ----- commands -------------------------------------------------------------------

    def toggle(self) -> None:
        if self._busy:
            return
        if self._recorder is None:
            self.start()
        else:
            self.stop()

    def toggle_pause(self) -> None:
        if self._busy or self._recorder is None:
            return
        if self.state is State.RECORDING:
            self._submit("pause", self._recorder.pause)
        elif self.state is State.PAUSED:
            self._submit("resume", self._recorder.resume)

    def start(self) -> None:
        opts = self._settings().recording
        ffmpeg = find_ffmpeg(opts.ffmpeg_path)
        if ffmpeg is None:
            self._tell(
                f"Recording needs ffmpeg. Install it from {FFMPEG_DOWNLOAD_URL} "
                "or set its path in Settings."
            )
            return
        microphone = opts.microphone.device if opts.microphone.enabled else None
        if opts.microphone.enabled and not microphone:
            self._tell("Microphone is on but no device is picked; choose one in Settings.")
            return
        monitors = win32.display_outputs()
        pointer = win32.cursor_position()
        try:
            chosen = select(monitors, opts.screen, pointer)
        except ValueError as exc:
            self._tell(f"Recording did not start: {exc}.")
            return
        if opts.screen == SCREEN_ALL:
            self._screen_label = SCREEN_ALL
            under = [m for m in chosen if pointer and m.contains(*pointer)]
            self._indicator_monitor = under[0] if under else chosen[0]
        else:
            self._screen_label = str(numbered(monitors).index(chosen[0]) + 1)
            self._indicator_monitor = chosen[0]
        folder = Path(opts.folder) if opts.folder else default_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            token: str | int = (
                SCREEN_ALL if self._screen_label == SCREEN_ALL else int(self._screen_label)
            )
            final = unique_path(
                folder, render_name(opts.name_pattern, datetime.now(), token), opts.container
            )
        except OSError as exc:
            self._tell(f"Recording did not start: the folder is not usable ({exc}).")
            return
        picker = self._pickers.setdefault(
            ffmpeg,
            EncoderPicker(
                lambda enc: _run_quiet(encoder_test_command(ffmpeg, enc)).returncode == 0
            ),
        )
        self._set_ink_hidden(not opts.include_ink)

        def begin() -> Recorder:
            plans = capture_plans(
                chosen,
                opts.backend,
                frame_rate=opts.frame_rate,
                cursor=opts.cursor,
                encoder=picker.pick(opts.container),
                quality=opts.quality,
                bitrate_kbps=opts.bitrate_kbps,
                microphone=microphone,
                container=opts.container,
            )
            recorder = Recorder(ffmpeg, plans, final)
            recorder.start()
            self._live = recorder
            return recorder

        self._submit("start", begin)

    def stop(self) -> None:
        if self._busy or self._recorder is None:
            return
        self._timer.stop()
        self.indicator.hide()
        self._submit("stop", self._stop_live)

    def _stop_live(self) -> Outcome | None:
        """Worker thread: stop whichever recording is running, if any."""
        recorder, self._live = self._live, None
        return recorder.stop() if recorder is not None else None

    def shutdown(self) -> None:
        """On quit: save a running recording, also one whose start is still in flight.

        The worker runs jobs in order, so this final stop runs after any pending start.
        """
        self._timer.stop()
        try:
            outcome = self._worker.submit(self._stop_live).result(timeout=SHUTDOWN_WAIT_S)
            if outcome is not None:
                self._report(outcome)
        except Exception as exc:  # noqa: BLE001 (quitting: report, never block the exit)
            log.error("❌ recording not saved at quit: %s", exc)
        self._set_ink_hidden(False)
        self._worker.shutdown(wait=False, cancel_futures=True)

    # ----- worker plumbing ------------------------------------------------------------

    def _submit(self, operation: str, work: Callable[[], object]) -> None:
        self._busy = True
        self.state_changed.emit()

        def run() -> None:
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 (reported to the user via notify)
                result = exc
            self._finished.emit(operation, result)

        self._worker.submit(run)

    def _on_finished(self, operation: str, result: object) -> None:
        self._busy = False
        failed = isinstance(result, Exception)
        if operation == "start":
            if failed:
                self._set_ink_hidden(False)
                self._tell(f"Recording did not start: {result}")
            else:
                self._recorder = result  # type: ignore[assignment]
                self.indicator.show_on(self._indicator_monitor)
                self._timer.start()
                log.info("✅ recording started (screen %s)", self._screen_label)
        elif operation in ("pause", "resume"):
            if failed:
                self._tell(f"Recording could not {operation}: {result}")
            self._tick()
        elif operation == "stop":
            self._recorder = None
            self._set_ink_hidden(False)
            if failed:
                self._tell(f"Recording not saved: {result}")
            elif isinstance(result, Outcome):
                self._report(result)
        self.state_changed.emit()

    def _report(self, outcome: Outcome) -> None:
        log.info(
            "🎬 recording saved: screen=%s duration=%.1fs size=%.2fMB encoder=%s backend=%s",
            self._screen_label,
            outcome.seconds,
            outcome.size_bytes / 1_000_000,
            outcome.encoder,
            outcome.backend,
        )
        self.notify.emit(f"Recording saved as {outcome.path.name}")

    def _tell(self, message: str) -> None:
        """Show a problem in the tray and keep it in the log, so it is diagnosable later."""
        log.warning("⚠️ %s", message)
        self.notify.emit(message)

    def _tick(self) -> None:
        recorder = self._recorder
        if recorder is None or self._busy:
            return
        if recorder.state is State.RECORDING and not recorder.alive():
            self._tell("Recording stopped unexpectedly; saving what was recorded.")
            self.stop()
            return
        self.indicator.update_time(recorder.elapsed(), paused=recorder.state is State.PAUSED)

    def _set_ink_hidden(self, hidden: bool) -> None:
        if hidden != self._ink_hidden:
            self._ink_hidden = hidden
            self._hide_ink(hidden)

    @property
    def ink_hidden(self) -> bool:
        return self._ink_hidden
