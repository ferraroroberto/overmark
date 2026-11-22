"""System audio: what the computer plays, captured through WASAPI loopback into a WAV.

ffmpeg on Windows has no loopback input, so PyAudioWPatch captures it while each video
segment records; the join mixes the WAVs in. WASAPI delivers nothing while nothing plays,
so every chunk is placed on the clock instead of appended: gaps become silence and the
file keeps the length of the wall-clock time it covers.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SAMPLE_BYTES = 2  # 16-bit PCM
CHUNK_S = 0.01  # WASAPI's own shared-mode period; smaller buys nothing
# How far a chunk may land from where the clock says it belongs before silence is
# inserted or audio dropped: above callback jitter (a few ms), well under the 100 ms
# a viewer notices as lip-sync error.
TOLERANCE_S = 0.03
WRITER_JOIN_S = 5.0
LOOPBACK_SUFFIX = " [Loopback]"  # how PyAudioWPatch names a loopback device


class LoopbackError(RuntimeError):
    """System audio could not be captured; the message says why."""


class Placement:
    """Where each chunk goes in the file. Pure: frames in, (silence, drop) decisions out.

    ``place`` gets the frame position the clock gives a chunk's first sample. Behind the
    file by more than the tolerance means audio arrived early (device clock drift): the
    overlap is dropped. Ahead means a gap (nothing played): silence fills it.
    """

    def __init__(self, rate: int, tolerance_s: float = TOLERANCE_S) -> None:
        self.rate = rate
        self.tolerance = round(rate * tolerance_s)
        self.written = 0

    def place(self, start: int, frames: int) -> tuple[int, int]:
        """Return (silence frames to write first, frames to drop from the chunk start)."""
        silence = drop = 0
        if start - self.written > self.tolerance:
            silence = start - self.written
        elif self.written - start > self.tolerance:
            drop = min(self.written - start, frames)
        self.written += silence + frames - drop
        return silence, drop

    def finish(self, end: int) -> int:
        """Silence frames that pad the file to ``end``; zero when it already reaches it."""
        pad = max(end - self.written, 0)
        self.written += pad
        return pad


@dataclass(frozen=True)
class Capture:
    """One finished WAV: its first sample was at ``origin`` on ``time.perf_counter``."""

    path: Path
    origin: float


def loopback_name(device: dict[str, Any]) -> str:
    """A loopback device's name without PyAudioWPatch's suffix, as the setting stores it."""
    name = str(device["name"])
    return name[: -len(LOOPBACK_SUFFIX)] if name.endswith(LOOPBACK_SUFFIX) else name


def _pyaudio() -> Any:
    try:
        import pyaudiowpatch
    except ImportError:
        raise LoopbackError(
            "system audio needs PyAudioWPatch (pip install PyAudioWPatch)"
        ) from None
    return pyaudiowpatch


def list_loopback_devices() -> list[str]:
    """Loopback device names, or an empty list when WASAPI or the library is unavailable."""
    try:
        pa = _pyaudio()
        audio = pa.PyAudio()
    except (LoopbackError, OSError) as exc:
        log.warning("⚠️ listing system-audio devices failed: %s", exc)
        return []
    try:
        names = []
        for device in audio.get_loopback_device_info_generator():
            name = loopback_name(device)
            if name not in names:
                names.append(name)
        return names
    except OSError as exc:
        log.warning("⚠️ listing system-audio devices failed: %s", exc)
        return []
    finally:
        audio.terminate()


def _find_device(audio: Any, device: str) -> dict[str, Any]:
    if not device:
        try:
            return audio.get_default_wasapi_loopback()
        except (OSError, LookupError):
            raise LoopbackError(
                "no system-audio device: the computer has no audio output"
            ) from None
    for info in audio.get_loopback_device_info_generator():
        if loopback_name(info) == device:
            return info
    raise LoopbackError("the system-audio device was not found; pick another in Settings")


class LoopbackCapture:
    """Captures one segment's system audio into ``path`` from ``start`` to ``stop``.

    PortAudio calls back on its own thread; the chunks go through a queue to a writer
    thread, so neither the audio thread nor the Qt thread ever waits on the disk.
    """

    def __init__(
        self,
        path: Path,
        device: str = "",
        *,
        clock: Callable[[], float] = time.perf_counter,
        backend: Callable[[], Any] = _pyaudio,
    ) -> None:
        self.path = path
        self.device = device
        self._clock = clock
        self._backend = backend
        self._chunks: queue.SimpleQueue = queue.SimpleQueue()
        self._audio: Any = None
        self._stream: Any = None
        self._writer: threading.Thread | None = None
        self._wav: wave.Wave_write | None = None
        self._placement: Placement | None = None
        self._frame_bytes = 0
        self.origin = 0.0

    def start(self) -> None:
        pa = self._backend()
        try:
            self._audio = pa.PyAudio()
            info = _find_device(self._audio, self.device)
            rate = int(info["defaultSampleRate"])
            channels = max(int(info["maxInputChannels"]), 1)
            self._frame_bytes = channels * SAMPLE_BYTES
            self._placement = Placement(rate)
            self._wav = wave.open(str(self.path), "wb")  # noqa: SIM115 (closed in stop)
            self._wav.setnchannels(channels)
            self._wav.setsampwidth(SAMPLE_BYTES)
            self._wav.setframerate(rate)
            self._writer = threading.Thread(
                target=self._write_loop, name="overmark-loopback", daemon=True
            )
            self._writer.start()
            self.origin = self._clock()
            self._stream = self._audio.open(
                format=pa.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=int(info["index"]),
                frames_per_buffer=max(round(rate * CHUNK_S), 1),
                stream_callback=self._on_chunk,
            )
        except LoopbackError:
            self._close()
            raise
        except OSError as exc:
            self._close()
            raise LoopbackError(f"system audio could not be opened ({exc})") from None
        log.info("ℹ️ system audio: %d Hz, %d channel(s) into %s", rate, channels, self.path.name)

    def _on_chunk(self, data: bytes, frames: int, _time_info: Any, _status: int) -> tuple:
        # The chunk ends now, so its first sample was one chunk length ago.
        self._chunks.put((self._clock(), data, frames))
        return (None, 0)  # 0 is PortAudio's paContinue

    def _write_loop(self) -> None:
        placement, wav = self._placement, self._wav
        while True:
            item = self._chunks.get()
            if item is None:
                return
            arrived, data, frames = item
            start = round((arrived - self.origin) * placement.rate) - frames
            silence, drop = placement.place(start, frames)
            if silence or drop:
                log.debug("system audio: %d frames of silence, %d dropped", silence, drop)
            if silence:
                wav.writeframes(bytes(silence * self._frame_bytes))
            wav.writeframes(data[drop * self._frame_bytes :])

    def stop(self) -> Capture:
        """Stop capturing, pad the file with silence up to now, close it."""
        end = self._clock()
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except OSError as exc:
                log.warning("⚠️ closing the system-audio stream failed: %s", exc)
            self._stream = None
        self._join_writer()
        if self._wav is not None and self._placement is not None:
            pad = self._placement.finish(round((end - self.origin) * self._placement.rate))
            self._wav.writeframes(bytes(pad * self._frame_bytes))
        self._close()
        return Capture(self.path, self.origin)

    def _join_writer(self) -> None:
        if self._writer is None:
            return
        self._chunks.put(None)
        self._writer.join(timeout=WRITER_JOIN_S)
        if self._writer.is_alive():
            log.error("❌ system-audio writer did not finish; the WAV may be short")
        self._writer = None

    def _close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None
        self._join_writer()
        if self._wav is not None:
            self._wav.close()
            self._wav = None
        if self._audio is not None:
            self._audio.terminate()
            self._audio = None
