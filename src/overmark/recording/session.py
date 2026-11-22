"""Runs ffmpeg for one recording: segments, a bounded clean stop, the join and rename.

No Qt. Calls block (a stop waits for ffmpeg to finish its file), so the app runs
them off the UI thread, one at a time.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from overmark.recording.command import CapturePlan, concat_list, join_command, segment_command
from overmark.recording.naming import joining_path
from overmark.recording.segments import Segments, State

log = logging.getLogger(__name__)

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
STARTUP_GRACE_S = 1.5  # a bad device or capture source makes ffmpeg exit well inside this
STOP_WAIT_S = 5.0  # time for ffmpeg to flush and close its file after "q"
KILL_WAIT_S = 2.0
JOIN_TIMEOUT_S = 600.0  # stream copy runs at disk speed; hours of video still fit
POLL_S = 0.1
LOG_TAIL_LINES = 6


class RecordingError(RuntimeError):
    """A failure the user should read: the message names what went wrong."""


@dataclass(frozen=True)
class Outcome:
    path: Path
    seconds: float
    size_bytes: int
    encoder: str
    backend: str


def _tail(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines[-LOG_TAIL_LINES:] if line.strip()]


# ffmpeg log fragments that have a cause the user can act on.
_KNOWN_FAILURES = (
    ("Could not find audio only device", "the microphone was not found; pick another in Settings"),
    ("Could not run graph", "the microphone is busy or unavailable"),
    ("Failed to enumerate DXGI output", "a screen cannot be captured with ddagrab"),
    ("No capable devices found", "the hardware encoder is not available"),
    ("No space left on device", "the destination disk is full"),
    ("Permission denied", "the destination folder is not writable"),
)
MAX_MESSAGE = 160


def explain_failure(lines: list[str]) -> str:
    """One readable sentence for a failed ffmpeg start, from the last lines of its log."""
    text = "\n".join(lines)
    for fragment, meaning in _KNOWN_FAILURES:
        if fragment in text:
            return meaning
    if not lines:
        return "ffmpeg exited at start"
    last = lines[-1].split("] ", 1)[-1]  # drop the "[component @ 0x...]" prefix
    return last[:MAX_MESSAGE]


class Recorder:
    """One recording. ``plans`` are tried in order at the first start (ddagrab, then the
    gdigrab fallback); the one that starts is used for every later segment.
    """

    def __init__(
        self,
        ffmpeg: str,
        plans: list[CapturePlan],
        final: Path,
        *,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        startup_grace_s: float = STARTUP_GRACE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not plans:
            raise ValueError("at least one capture plan is needed")
        self.ffmpeg = ffmpeg
        self._plans = list(plans)
        self.plan = plans[0]
        self.segments = Segments(final, clock)
        self._popen = popen
        self._run = run
        self._startup_grace_s = startup_grace_s
        self._proc: subprocess.Popen | None = None
        self._log_file = None
        self.work_dir = Path(tempfile.mkdtemp(prefix="overmark-rec-"))

    @property
    def state(self) -> State:
        return self.segments.state

    def elapsed(self) -> float:
        return self.segments.elapsed()

    def alive(self) -> bool:
        """False once a running segment's ffmpeg has exited on its own."""
        return self._proc is not None and self._proc.poll() is None

    # ----- lifecycle ------------------------------------------------------------------

    def start(self) -> None:
        errors: list[str] = []
        for plan in self._plans:
            self.plan = plan
            try:
                self._begin_segment()
            except RecordingError as exc:
                if str(exc) not in errors:
                    errors.append(str(exc))
                continue
            self._plans = [plan]
            return
        self._cleanup_work_dir()
        raise RecordingError("; ".join(errors))

    def pause(self) -> None:
        produced = self._end_segment()
        self.segments.pause(produced)

    def resume(self) -> None:
        self._begin_segment()

    def stop(self) -> Outcome:
        """End the recording and join it into the final file; never overwrites anything."""
        produced = self._end_segment() if self.state is State.RECORDING else False
        self.segments.stop(produced)
        kept = self.segments.kept
        if not kept:
            self._cleanup_work_dir()
            raise RecordingError("nothing was recorded")
        final = self.segments.final
        joined = joining_path(final)
        list_file = self.work_dir / "segments.txt"
        list_file.write_text(concat_list(kept), encoding="utf-8")
        cmd = join_command(self.ffmpeg, list_file, self.plan.container, joined)
        try:
            done = self._run(
                cmd,
                capture_output=True,
                timeout=JOIN_TIMEOUT_S,
                creationflags=NO_WINDOW,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RecordingError(
                f"joining the segments took over {JOIN_TIMEOUT_S:.0f} s; "
                f"they are kept as {final.stem} part files in {final.parent.name}"
            ) from None
        if done.returncode != 0 or not joined.exists():
            message = done.stderr.decode("utf-8", errors="replace").strip()[-300:]
            raise RecordingError(
                f"joining the segments failed ({message}); "
                f"they are kept as {final.stem} part files in {final.parent.name}"
            )
        os.rename(joined, final)  # fails rather than replaces if the name was taken meanwhile
        for path in self.segments.all_paths:
            path.unlink(missing_ok=True)
        self._cleanup_work_dir()
        return Outcome(
            path=final,
            seconds=self.segments.elapsed(),
            size_bytes=final.stat().st_size,
            encoder=self.plan.encoder,
            backend=self.plan.backend,
        )

    # ----- segments -------------------------------------------------------------------

    def _begin_segment(self) -> None:
        out = self.segments.begin()
        log_path = self.work_dir / f"{out.stem.lstrip('.')}.log"
        self._log_file = open(log_path, "wb")  # noqa: SIM115 (closed in _close_log)
        cmd = segment_command(self.ffmpeg, self.plan, out)
        log.info("ℹ️ recording segment %s with %s", out.name, self.plan.backend)
        try:
            self._proc = self._popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self._log_file,
                creationflags=NO_WINDOW,
            )
        except OSError as exc:
            self._close_log()
            self.segments.abandon_current()
            raise RecordingError(f"ffmpeg could not be started ({exc})") from None
        deadline = time.monotonic() + self._startup_grace_s
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                self._proc = None
                self._close_log()
                out.unlink(missing_ok=True)
                self.segments.abandon_current()
                lines = _tail(log_path)
                log.warning("⚠️ %s capture did not start: %s", self.plan.backend, " | ".join(lines))
                raise RecordingError(explain_failure(lines))
            time.sleep(POLL_S)

    def _end_segment(self) -> bool:
        """Stop the running ffmpeg: "q", a bounded wait, then terminate. True if a file is left."""
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.stdin.write(b"q")
                proc.stdin.flush()
                proc.stdin.close()
            except OSError:
                pass  # it is already exiting; the wait below decides
            try:
                proc.wait(timeout=STOP_WAIT_S)
            except subprocess.TimeoutExpired:
                log.warning("⚠️ ffmpeg did not stop within %.0f s; terminating it", STOP_WAIT_S)
                proc.terminate()
                try:
                    proc.wait(timeout=KILL_WAIT_S)
                except subprocess.TimeoutExpired:
                    log.error("❌ ffmpeg survived terminate; its segment may be incomplete")
        self._close_log()
        current = self.segments.all_paths[-1]
        return current.exists() and current.stat().st_size > 0

    def _close_log(self) -> None:
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None

    def _cleanup_work_dir(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)
