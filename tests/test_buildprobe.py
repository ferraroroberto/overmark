"""The loopback build probe the restart check reads, and its tie to tray.bat."""

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from overmark import buildprobe
from overmark.buildprobe import VersionServer, read_git_sha, version_payload

ROOT = Path(__file__).resolve().parent.parent


def test_payload_carries_the_sha_and_pid_the_restart_check_reads() -> None:
    assert version_payload("abc123", 42) == {"app": "overmark", "git_sha": "abc123", "pid": 42}


def test_unreadable_git_gives_an_empty_sha_not_a_guess(tmp_path: Path) -> None:
    assert read_git_sha(tmp_path / "missing") == ""


def test_this_checkout_reports_a_full_commit_sha() -> None:
    sha = read_git_sha(ROOT)
    if not sha:
        pytest.skip("git or a repository is not available here")
    assert re.fullmatch(r"[0-9a-f]{40}", sha)


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def test_server_answers_the_version_path_on_loopback_only() -> None:
    server = VersionServer("deadbeef", port=0)
    assert server.start()
    try:
        status, body = _get(f"http://127.0.0.1:{server.port}{buildprobe.VERSION_PATH}")
        assert status == 200
        answer = json.loads(body)
        assert answer["git_sha"] == "deadbeef"
        assert isinstance(answer["pid"], int)
        assert _get(f"http://127.0.0.1:{server.port}/other")[0] == 404
        assert server._server is not None
        assert server._server.server_address[0] == "127.0.0.1"
    finally:
        server.stop()


def test_a_taken_port_is_reported_not_raised() -> None:
    first = VersionServer("a", port=0)
    assert first.start()
    try:
        assert VersionServer("b", port=first.port).start() is False
    finally:
        first.stop()


def test_tray_bat_reclaims_the_probe_port_and_launches_the_package() -> None:
    # ascii: cmd.exe misparses a multi-byte character mid-file
    text = (ROOT / "tray.bat").read_bytes().decode("ascii")
    assert f'set "OWNED_PORTS={buildprobe.VERSION_PORT}"' in text
    assert 'set "TRAY_LAUNCH=-m overmark"' in text
    assert re.search(r'-TrayMatch "-m\\s\+overmark"', text)
    assert "__" not in text.replace("__PLACEHOLDER__", "")
