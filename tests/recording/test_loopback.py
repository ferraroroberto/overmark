"""System-audio capture: chunk placement on the clock, and the WAV it writes (backend faked)."""

import wave
from pathlib import Path

import pytest

from overmark.recording.loopback import (
    LoopbackCapture,
    LoopbackError,
    Placement,
    loopback_name,
)

RATE = 1000  # one frame per millisecond keeps the arithmetic readable
TOL = 30  # frames: the 30 ms tolerance at this rate


def test_chunks_on_time_are_written_back_to_back() -> None:
    p = Placement(RATE)
    assert p.place(0, 10) == (0, 0)
    assert p.place(10 + TOL, 10) == (0, 0)  # jitter within the tolerance is ignored
    assert p.written == 20


def test_a_gap_while_nothing_plays_becomes_silence() -> None:
    p = Placement(RATE)
    p.place(0, 10)
    assert p.place(500, 10) == (490, 0)
    assert p.written == 510


def test_audio_running_ahead_of_the_clock_is_dropped() -> None:
    p = Placement(RATE)
    p.place(0, 100)
    assert p.place(100 - TOL - 5, 10) == (0, 10)  # wholly overlapping: dropped entirely
    assert p.place(100 - TOL - 5, 50) == (0, 35)
    assert p.written == 115


def test_finish_pads_to_the_stop_time_and_never_truncates() -> None:
    p = Placement(RATE)
    p.place(0, 10)
    assert p.finish(250) == 240
    assert p.finish(100) == 0
    assert p.written == 250


def test_loopback_name_drops_the_library_suffix() -> None:
    assert loopback_name({"name": "Desk Speakers [Loopback]"}) == "Desk Speakers"
    assert loopback_name({"name": "Desk Speakers"}) == "Desk Speakers"


DEVICES = [
    {
        "index": 3,
        "name": "Desk Speakers [Loopback]",
        "defaultSampleRate": RATE,
        "maxInputChannels": 2,
    },
    {
        "index": 4,
        "name": "Room Display [Loopback]",
        "defaultSampleRate": RATE,
        "maxInputChannels": 2,
    },
]


class FakeStream:
    def __init__(self, callback) -> None:
        self.callback = callback
        self.closed = False

    def stop_stream(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeAudio:
    def __init__(self) -> None:
        self.stream: FakeStream | None = None
        self.opened_index: int | None = None

    def get_default_wasapi_loopback(self) -> dict:
        return DEVICES[0]

    def get_loopback_device_info_generator(self):
        yield from DEVICES

    def open(self, *, input_device_index, stream_callback, **_kwargs) -> FakeStream:
        self.opened_index = input_device_index
        self.stream = FakeStream(stream_callback)
        return self.stream

    def terminate(self) -> None:
        pass


class FakeBackend:
    paInt16 = 8

    def __init__(self) -> None:
        self.audio = FakeAudio()

    def PyAudio(self) -> FakeAudio:  # noqa: N802 (the library's name)
        return self.audio


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def frames(path: Path) -> tuple[int, bytes]:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes(), wav.readframes(wav.getnframes())


def test_capture_places_chunks_and_pads_to_stop(tmp_path: Path) -> None:
    backend, clock = FakeBackend(), Clock()
    capture = LoopbackCapture(
        tmp_path / "a.wav", "Room Display", clock=clock, backend=lambda: backend
    )
    capture.start()
    assert backend.audio.opened_index == 4
    chunk = b"\x01\x00" * 2 * 10  # 10 stereo frames
    clock.now = 100.010
    backend.audio.stream.callback(chunk, 10, {}, 0)
    clock.now = 100.500  # 480 ms with nothing played, then another chunk
    backend.audio.stream.callback(chunk, 10, {}, 0)
    clock.now = 101.000
    result = capture.stop()
    count, data = frames(result.path)
    assert result.origin == 100.0
    assert count == 1000  # exactly the second that passed
    assert data[:40] == chunk
    assert data[40:44] == b"\x00" * 4  # the gap is silence


def test_unknown_device_is_a_readable_error_and_leaves_no_wav(tmp_path: Path) -> None:
    backend = FakeBackend()
    capture = LoopbackCapture(tmp_path / "a.wav", "Missing Device", backend=lambda: backend)
    with pytest.raises(LoopbackError, match="not found"):
        capture.start()
    assert not (tmp_path / "a.wav").exists()
