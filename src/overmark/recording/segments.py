"""Pause bookkeeping. ffmpeg cannot pause, so each pause ends a segment and resume
starts the next one with the same settings; stop joins them into one file.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from overmark.recording.naming import segment_path


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPED = "stopped"


class Segments:
    """Segment files and recorded time for one recording. The clock is injected."""

    def __init__(self, final: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.final = final
        self._clock = clock
        self.state = State.IDLE
        self._paths: list[Path] = []
        self._kept: list[Path] = []
        self._done_seconds = 0.0
        self._started_at: float | None = None

    @property
    def kept(self) -> list[Path]:
        """Segments that produced a file, in recording order: what stop joins."""
        return list(self._kept)

    @property
    def all_paths(self) -> list[Path]:
        """Every segment path handed out, kept or not: what clean-up removes."""
        return list(self._paths)

    def begin(self) -> Path:
        """Start the next segment (first start, or resume); return its file path."""
        if self.state not in (State.IDLE, State.PAUSED):
            raise RuntimeError(f"cannot start a segment while {self.state.value}")
        path = segment_path(self.final, len(self._paths) + 1)
        self._paths.append(path)
        self._started_at = self._clock()
        self.state = State.RECORDING
        return path

    def _end(self, produced: bool) -> None:
        if self.state is not State.RECORDING or self._started_at is None:
            raise RuntimeError(f"no running segment while {self.state.value}")
        if produced:
            self._kept.append(self._paths[-1])
            self._done_seconds += self._clock() - self._started_at
        self._started_at = None

    def pause(self, produced: bool) -> None:
        """The running segment ended for a pause; ``produced`` says if it left a file."""
        self._end(produced)
        self.state = State.PAUSED

    def stop(self, produced: bool = True) -> None:
        """Recording ends; from a pause there is no running segment to close."""
        if self.state is State.RECORDING:
            self._end(produced)
        elif self.state is not State.PAUSED:
            raise RuntimeError(f"cannot stop while {self.state.value}")
        self.state = State.STOPPED

    def abandon_current(self) -> None:
        """The segment that was just begun never started (ffmpeg failed to launch)."""
        if self.state is not State.RECORDING:
            raise RuntimeError(f"no running segment while {self.state.value}")
        self._started_at = None
        self.state = State.PAUSED if self._kept else State.IDLE

    def elapsed(self) -> float:
        """Recorded seconds so far: finished segments plus the running one."""
        running = self._clock() - self._started_at if self._started_at is not None else 0.0
        return self._done_seconds + running
