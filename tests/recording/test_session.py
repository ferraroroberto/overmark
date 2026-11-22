"""The recorder with ffmpeg faked: fallback at start, clean stop, kill on hang, join."""

import subprocess
from pathlib import Path

import pytest

from overmark.recording.command import DDAGRAB, GDIGRAB, CapturePlan
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
