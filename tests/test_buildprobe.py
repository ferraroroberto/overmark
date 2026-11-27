"""The build identity the restart check reads, and its tie to tray.bat."""

import re
from datetime import datetime
from pathlib import Path

import pytest

from overmark import buildprobe
from overmark.buildprobe import read_git_sha, started_at, version_payload

ROOT = Path(__file__).resolve().parent.parent


def test_payload_carries_the_sha_start_and_pid_the_restart_check_reads() -> None:
    assert version_payload("abc123", 42, "2026-01-01T09:00:00+00:00") == {
        "app": "overmark",
        "git_sha": "abc123",
        "built_at": "2026-01-01T09:00:00+00:00",
        "pid": 42,
    }


def test_start_time_is_iso_with_its_offset() -> None:
    assert datetime.fromisoformat(started_at()).tzinfo is not None


def test_unreadable_git_gives_an_empty_sha_not_a_guess(tmp_path: Path) -> None:
    assert read_git_sha(tmp_path / "missing") == ""


def test_this_checkout_reports_a_full_commit_sha() -> None:
    sha = read_git_sha(ROOT)
    if not sha:
        pytest.skip("git or a repository is not available here")
    assert re.fullmatch(r"[0-9a-f]{40}", sha)


def test_tray_bat_reclaims_the_probe_port_and_launches_the_package() -> None:
    # ascii: cmd.exe misparses a multi-byte character mid-file
    text = (ROOT / "tray.bat").read_bytes().decode("ascii")
    assert f'set "OWNED_PORTS={buildprobe.VERSION_PORT}"' in text
    assert 'set "TRAY_LAUNCH=-m overmark"' in text
    assert 'set "TRAY_MATCH=-m\\s+overmark"' in text
    assert "__" not in text.replace("__PLACEHOLDER__", "")
