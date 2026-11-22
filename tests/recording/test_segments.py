"""Pause bookkeeping: segment files, recorded time, and the allowed transitions."""

from pathlib import Path

import pytest

from overmark.recording.segments import Segments, State

FINAL = Path("rec") / "talk.mp4"


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


def test_record_pause_resume_stop_keeps_every_segment_in_order(clock: Clock) -> None:
    seg = Segments(FINAL, clock)
    first = seg.begin()
    clock.now += 10
    seg.pause(produced=True)
    clock.now += 60  # paused time is not recorded time
    second = seg.begin()
    clock.now += 5
    seg.stop(produced=True)
    assert seg.state is State.STOPPED
    assert seg.kept == [first, second]
    assert [p.name for p in seg.kept] == [".talk.part1.mkv", ".talk.part2.mkv"]
    assert seg.elapsed() == pytest.approx(15)


def test_elapsed_runs_while_recording_and_freezes_while_paused(clock: Clock) -> None:
    seg = Segments(FINAL, clock)
    seg.begin()
    clock.now += 3
    assert seg.elapsed() == pytest.approx(3)
    seg.pause(produced=True)
    clock.now += 100
    assert seg.elapsed() == pytest.approx(3)


def test_stop_from_pause_closes_nothing_more(clock: Clock) -> None:
    seg = Segments(FINAL, clock)
    seg.begin()
    clock.now += 4
    seg.pause(produced=True)
    seg.stop()
    assert len(seg.kept) == 1
    assert seg.elapsed() == pytest.approx(4)


def test_a_segment_that_left_no_file_is_not_joined_or_counted(clock: Clock) -> None:
    seg = Segments(FINAL, clock)
    seg.begin()
    clock.now += 2
    seg.pause(produced=False)
    kept = seg.begin()
    clock.now += 3
    seg.stop(produced=True)
    assert seg.kept == [kept]
    assert len(seg.all_paths) == 2, "clean-up still covers the empty segment"
    assert seg.elapsed() == pytest.approx(3)


def test_a_failed_first_start_returns_to_idle(clock: Clock) -> None:
    seg = Segments(FINAL, clock)
    seg.begin()
    seg.abandon_current()
    assert seg.state is State.IDLE
    assert seg.elapsed() == 0


def test_a_failed_resume_stays_paused_with_earlier_segments(clock: Clock) -> None:
    seg = Segments(FINAL, clock)
    seg.begin()
    clock.now += 2
    seg.pause(produced=True)
    seg.begin()
    seg.abandon_current()
    assert seg.state is State.PAUSED
    assert len(seg.kept) == 1


@pytest.mark.parametrize(
    "steps",
    [
        ["pause"],  # nothing running
        ["stop"],  # never started
        ["begin", "begin"],  # already recording
        ["begin", "stop", "begin"],  # finished
        ["begin", "pause", "pause"],
    ],
)
def test_invalid_transitions_raise(clock: Clock, steps: list[str]) -> None:
    seg = Segments(FINAL, clock)
    actions = {
        "begin": seg.begin,
        "pause": lambda: seg.pause(True),
        "stop": lambda: seg.stop(True),
    }
    with pytest.raises(RuntimeError):
        for step in steps:
            actions[step]()
