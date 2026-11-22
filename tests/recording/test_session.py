"""The recorder with ffmpeg faked: fallback at start, clean stop, kill on hang, join."""

import subprocess
from pathlib import Path

import pytest

from overmark.recording.command import DDAGRAB, GDIGRAB, CapturePlan
from overmark.recording.loopback import Capture, LoopbackError
from overmark.recording.monitors import Monitor
from overmark.recording.segments import State
from overmark.recording.session import Recorder, RecordingError, explain_failure

SCREEN = Monitor("screen", 0, 0, 1280, 720, dda_index=0)


def plan(backend: str) -> CapturePlan:
    return CapturePlan(
        monitors=(SCREEN,),
        backend=backend,
        frame_rate=30,
        cursor=True,
        encoder="libx264",
        quality="medium",
        container="mp4",
    )


class FakeStdin:
    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes) -> None:
        self.data += data

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class FakeProc:
    """Writes its output file at once; exits at start (``fails``) or on "q" unless ``hangs``."""

    def __init__(self, cmd, fails: str | None, hangs: bool, stderr) -> None:
        self.cmd = cmd
        self.stdin = FakeStdin()
        self.hangs = hangs
        self.terminated = False
        self.returncode = None
        if fails is not None:
            stderr.write(fails.encode())
            stderr.flush()
            self.returncode = 1
        else:
            Path(cmd[-1]).write_bytes(b"video")

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None and (self.hangs or b"q" not in self.stdin.data):
            raise subprocess.TimeoutExpired(self.cmd, timeout)
        self.returncode = self.returncode or 0
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 1


class FakeFfmpeg:
    def __init__(self, fail_backends=(), hangs: bool = False, fail_message: str = "") -> None:
        self.fail_backends = set(fail_backends)
        self.hangs = hangs
        self.fail_message = fail_message
        self.procs: list[FakeProc] = []
        self.joins: list[list[str]] = []

    def popen(self, cmd, **kwargs):
        backend = GDIGRAB if "gdigrab" in cmd else DDAGRAB
        fails = self.fail_message if backend in self.fail_backends else None
        proc = FakeProc(cmd, fails, self.hangs, kwargs["stderr"])
        self.procs.append(proc)
        return proc

    def run(self, cmd, **kwargs):
        if "concat" not in cmd:  # the length probe of one segment
            return subprocess.CompletedProcess(cmd, 1, b"", b"  Duration: 00:00:04.00, start")
        self.joins.append(cmd)
        Path(cmd[-1]).write_bytes(b"joined")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")


def recorder(tmp_path: Path, ffmpeg: FakeFfmpeg, plans=None) -> Recorder:
    return Recorder(
        "ffmpeg",
        plans or [plan(DDAGRAB), plan(GDIGRAB)],
        tmp_path / "talk.mp4",
        popen=ffmpeg.popen,
        run=ffmpeg.run,
        startup_grace_s=0.05,
    )


def test_record_pause_resume_stop_gives_one_file_and_no_part_files(tmp_path: Path) -> None:
    ffmpeg = FakeFfmpeg()
    rec = recorder(tmp_path, ffmpeg)
    rec.start()
    rec.pause()
    assert rec.state is State.PAUSED
    rec.resume()
    outcome = rec.stop()
    assert outcome.path == tmp_path / "talk.mp4"
    assert outcome.path.read_bytes() == b"joined"
    assert outcome.backend == DDAGRAB
    assert [p.stdin.data for p in ffmpeg.procs] == [b"q", b"q"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["talk.mp4"]
    assert not rec.work_dir.exists()


def test_a_failing_ddagrab_falls_back_to_gdigrab_for_every_segment(tmp_path: Path) -> None:
    ffmpeg = FakeFfmpeg(fail_backends={DDAGRAB})
    rec = recorder(tmp_path, ffmpeg)
    rec.start()
    rec.pause()
    rec.resume()
    assert rec.stop().backend == GDIGRAB
    assert ["gdigrab" in p.cmd for p in ffmpeg.procs] == [False, True, True]


def test_when_every_backend_fails_the_reason_is_readable(tmp_path: Path) -> None:
    ffmpeg = FakeFfmpeg(
        fail_backends={DDAGRAB, GDIGRAB},
        fail_message="[dshow @ 0x1] Could not find audio only device with name [Desk Mic]\n",
    )
    rec = recorder(tmp_path, ffmpeg)
    with pytest.raises(RecordingError, match="^the microphone was not found; pick another"):
        rec.start()
    assert list(tmp_path.iterdir()) == []
    assert not rec.work_dir.exists()


def test_a_hung_ffmpeg_is_terminated_and_its_segment_kept(tmp_path: Path) -> None:
    ffmpeg = FakeFfmpeg(hangs=True)
    rec = recorder(tmp_path, ffmpeg)
    rec.start()
    outcome = rec.stop()
    assert ffmpeg.procs[0].terminated
    assert outcome.path.exists()


def test_the_join_uses_the_chosen_container_and_never_overwrites(tmp_path: Path) -> None:
    ffmpeg = FakeFfmpeg()
    rec = recorder(tmp_path, ffmpeg)
    rec.start()
    rec.stop()
    join = ffmpeg.joins[0]
    assert "-n" in join
    assert join[-3:] == ["-f", "mp4", str(tmp_path / ".talk.part.mp4")]


def test_a_failed_join_keeps_the_segments(tmp_path: Path) -> None:
    ffmpeg = FakeFfmpeg()

    def failing_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, b"", b"Invalid data found")

    rec = Recorder(
        "ffmpeg",
        [plan(DDAGRAB)],
        tmp_path / "talk.mp4",
        popen=ffmpeg.popen,
        run=failing_run,
        startup_grace_s=0.05,
    )
    rec.start()
    with pytest.raises(RecordingError, match="part files"):
        rec.stop()
    assert [p.name for p in tmp_path.iterdir()] == [".talk.part1.mkv"]
    assert not (tmp_path / "talk.mp4").exists()


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        ([], "ffmpeg exited at start"),
        (
            ["[x @ 0x1] Failed to enumerate DXGI output 3"],
            "a screen cannot be captured with ddagrab",
        ),
        (["noise", "[out#0 @ 0x2] Something odd happened"], "Something odd happened"),
        (["x" * 400], "x" * 160),
    ],
)
def test_explain_failure(lines: list[str], expected: str) -> None:
    assert explain_failure(lines) == expected


class FakeCapture:
    """Stands in for the loopback capture: writes its WAV on start, origin from a counter."""

    starts: list["FakeCapture"] = []

    def __init__(self, path: Path, device: str, fails: bool = False) -> None:
        self.path, self.device, self.fails = path, device, fails
        self.stopped = False

    def start(self) -> None:
        if self.fails:
            raise LoopbackError("the system-audio device was not found; pick another in Settings")
        self.path.write_bytes(b"wav")
        FakeCapture.starts.append(self)

    def stop(self) -> Capture:
        self.stopped = True
        return Capture(self.path, origin=10.0)


class StampingFfmpeg(FakeFfmpeg):
    """Logs the first-frame stamp: 10.3 s on the wall clock, wall = perf + 0 in these tests."""

    def popen(self, cmd, **kwargs):
        kwargs["stderr"].write(b"[Eval @ 0000001] 10300000.000000\n")
        kwargs["stderr"].flush()
        return super().popen(cmd, **kwargs)


def system_recorder(tmp_path: Path, ffmpeg: FakeFfmpeg, *, mic: bool, fails=False) -> Recorder:
    base = plan(DDAGRAB)
    with_audio = CapturePlan(
        **{**base.__dict__, "system_audio": "", "microphone": "Desk Mic" if mic else None}
    )
    return Recorder(
        "ffmpeg",
        [with_audio],
        tmp_path / "talk.mp4",
        popen=ffmpeg.popen,
        run=ffmpeg.run,
        startup_grace_s=0.05,
        loopback=lambda path, device: FakeCapture(path, device, fails),
        wall_minus_perf=lambda: 0.0,
    )


@pytest.mark.parametrize("mic", [False, True])
def test_system_audio_is_captured_per_segment_and_mixed_on_stop(tmp_path: Path, mic) -> None:
    FakeCapture.starts.clear()
    ffmpeg = StampingFfmpeg()
    rec = system_recorder(tmp_path, ffmpeg, mic=mic)
    rec.start()
    rec.pause()
    rec.resume()
    rec.pause()
    rec.resume()
    rec.stop()
    assert [c.path.name for c in FakeCapture.starts] == [
        ".talk.part1.wav",
        ".talk.part2.wav",
        ".talk.part3.wav",
    ]
    assert all(c.stopped for c in FakeCapture.starts)
    g = ffmpeg.joins[0][ffmpeg.joins[0].index("-filter_complex") + 1]
    assert g.count("atrim=start=0.300000") == 3  # first frame 0.3 s into each WAV
    assert g.count("apad=whole_dur=4.000000") == 3
    assert ("amix" in g) is mic
    assert sorted(p.name for p in tmp_path.iterdir()) == ["talk.mp4"]


def test_a_failed_join_keeps_part_files_and_wavs(tmp_path: Path) -> None:
    class FailingJoin(StampingFfmpeg):
        def run(self, cmd, **kwargs):
            if "concat" in cmd:
                return subprocess.CompletedProcess(cmd, 1, b"", b"Invalid data found")
            return super().run(cmd, **kwargs)

    rec = system_recorder(tmp_path, FailingJoin(), mic=False)
    rec.start()
    with pytest.raises(RecordingError, match="part files"):
        rec.stop()
    assert sorted(p.name for p in tmp_path.iterdir()) == [".talk.part1.mkv", ".talk.part1.wav"]


def test_a_system_audio_failure_stops_the_start_before_ffmpeg(tmp_path: Path) -> None:
    ffmpeg = StampingFfmpeg()
    rec = system_recorder(tmp_path, ffmpeg, mic=False, fails=True)
    with pytest.raises(RecordingError, match="system-audio device was not found"):
        rec.start()
    assert ffmpeg.procs == []
    assert list(tmp_path.iterdir()) == []


def test_a_failed_ffmpeg_start_removes_the_segment_wav(tmp_path: Path) -> None:
    ffmpeg = StampingFfmpeg(fail_backends={DDAGRAB}, fail_message="boom")
    rec = system_recorder(tmp_path, ffmpeg, mic=False)
    with pytest.raises(RecordingError):
        rec.start()
    assert list(tmp_path.iterdir()) == []
