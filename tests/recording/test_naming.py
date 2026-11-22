"""File names: the template, unsafe characters, never overwriting, in-progress names."""

from datetime import datetime
from pathlib import Path

import pytest

from overmark.recording.naming import (
    DEFAULT_PATTERN,
    joining_path,
    render_name,
    segment_path,
    unique_path,
    validate_pattern,
)

WHEN = datetime(2026, 3, 4, 5, 6, 7)


def test_default_pattern_fills_date_time_and_screen() -> None:
    assert render_name(DEFAULT_PATTERN, WHEN, "all") == "overmark-2026-03-04-05-06-07-all"
    assert render_name(DEFAULT_PATTERN, WHEN, 2) == "overmark-2026-03-04-05-06-07-screen2"


def test_pattern_without_tokens_is_allowed() -> None:
    assert render_name("workshop", WHEN, "all") == "workshop"


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("a/b\\c:d", "a-b-c-d"),
        ('what?"*<>|', "what------"),
        ("  trailing. ", "trailing"),
        ("...", "overmark"),
    ],
)
def test_unsafe_characters_are_replaced(pattern: str, expected: str) -> None:
    assert render_name(pattern, WHEN, "all") == expected


@pytest.mark.parametrize("pattern", ["", "   ", None, 7, "{nope}", "{date", "x{0}"])
def test_bad_patterns_are_rejected(pattern) -> None:
    with pytest.raises(ValueError, match="Name pattern"):
        validate_pattern(pattern)


def test_unique_path_never_reuses_a_taken_name(tmp_path: Path) -> None:
    assert unique_path(tmp_path, "talk", "mp4") == tmp_path / "talk.mp4"
    (tmp_path / "talk.mp4").write_bytes(b"x")
    assert unique_path(tmp_path, "talk", "mp4") == tmp_path / "talk-2.mp4"
    (tmp_path / "talk-2.mp4").write_bytes(b"x")
    assert unique_path(tmp_path, "talk", "mp4") == tmp_path / "talk-3.mp4"


def test_a_running_recording_reserves_its_name(tmp_path: Path) -> None:
    final = tmp_path / "talk.mp4"
    segment_path(final, 1).write_bytes(b"x")
    assert unique_path(tmp_path, "talk", "mp4") == tmp_path / "talk-2.mp4"


def test_glob_characters_in_a_name_do_not_confuse_the_check(tmp_path: Path) -> None:
    final = tmp_path / "a[1].mp4"
    segment_path(final, 1).write_bytes(b"x")
    assert unique_path(tmp_path, "a[1]", "mp4") == tmp_path / "a[1]-2.mp4"
    assert unique_path(tmp_path, "a1", "mp4") == tmp_path / "a1.mp4"


def test_other_extensions_do_not_block_a_name(tmp_path: Path) -> None:
    (tmp_path / "talk.mkv").write_bytes(b"x")
    assert unique_path(tmp_path, "talk", "mp4") == tmp_path / "talk.mp4"


def test_in_progress_names_look_unfinished() -> None:
    final = Path("out") / "talk.mp4"
    assert segment_path(final, 1).name == ".talk.part1.mkv"
    assert segment_path(final, 12).name == ".talk.part12.mkv"
    assert joining_path(final).name == ".talk.part.mp4"
