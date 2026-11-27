"""The settings server's routes, on a fake app: what the page reads, saves and is refused."""

import copy
import json
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from overmark.buildprobe import VERSION_PATH
from overmark.config import Settings, settings_to_dict
from overmark.web import server
from overmark.web.server import WebServer, create_app

LOOPBACK = ("127.0.0.1", 50000)
BASE = "http://127.0.0.1:8467"


class FakeApp:
    """Stands in for the tray: holds settings and refuses one hotkey as taken."""

    def __init__(self) -> None:
        self.current = Settings()
        self.applied: list[Settings] = []
        self.taken = "ctrl+alt+t"

    def settings(self) -> Settings:
        return copy.deepcopy(self.current)

    def apply(self, settings: Settings) -> str | None:
        if settings.toggle_hotkey == self.taken:
            return f"{self.taken.upper()} is already used by another application."
        self.applied.append(settings)
        self.current = settings
        return None

    def microphones(self, ffmpeg_path: str) -> list[str]:
        return ["Desk Mic"] if not ffmpeg_path else []

    def system_audio(self) -> list[str]:
        return ["Desk Speakers"]

    def screens(self) -> list[str]:
        return ["Screen 1: 1920×1080 at 0, 0"]

    def pick_folder(self, start: str) -> str | None:
        return start + "\\picked"


@pytest.fixture
def fake() -> FakeApp:
    return FakeApp()


@pytest.fixture
def client(fake: FakeApp, tmp_path: Path) -> TestClient:
    app = create_app(
        fake, git_sha="abc1234", built_at="2026-01-01T09:00:00+00:00", pid=42, restart_dir=tmp_path
    )
    return TestClient(app, base_url=BASE, client=LOOPBACK)


def test_version_carries_what_the_restart_check_and_footer_read(client: TestClient) -> None:
    answer = client.get(VERSION_PATH).json()
    assert answer == {
        "app": "overmark",
        "git_sha": "abc1234",
        "built_at": "2026-01-01T09:00:00+00:00",
        "pid": 42,
    }


def test_the_page_carries_the_inline_icon_sprite(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert server.SPRITE_MARK not in response.text
    assert 'id="i-settings"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/static/app.js").status_code == 200


def test_settings_round_trip_and_apply_live(client: TestClient, fake: FakeApp) -> None:
    body = client.get("/api/settings").json()
    assert body["settings"] == settings_to_dict(Settings())
    assert body["choices"]["frame_rates"]

    body["settings"]["fade"]["delay_seconds"] = 4.0
    response = client.put("/api/settings", json=body["settings"])
    assert response.status_code == 200
    assert response.json()["settings"]["fade"]["delay_seconds"] == 4.0
    assert fake.applied[-1].fade.delay_seconds == 4.0


def test_a_clash_is_refused_before_the_app_sees_it(client: TestClient, fake: FakeApp) -> None:
    raw = settings_to_dict(Settings())
    raw["hotkey"]["record_pause"] = raw["hotkey"]["toggle_draw"]
    response = client.put("/api/settings", json=raw)
    assert response.status_code == 422
    assert response.json()["error"].startswith("Hotkeys clash:")
    assert fake.applied == []


def test_a_hotkey_another_program_holds_changes_nothing(client: TestClient, fake: FakeApp) -> None:
    raw = settings_to_dict(Settings())
    raw["hotkey"]["toggle_draw"] = fake.taken
    response = client.put("/api/settings", json=raw)
    assert response.status_code == 409
    assert "already used" in response.json()["error"]
    assert fake.current.toggle_hotkey == Settings().toggle_hotkey


def test_a_bad_interval_is_refused(client: TestClient) -> None:
    raw = settings_to_dict(Settings())
    raw["keep_awake"]["interval_seconds"] = 1
    response = client.put("/api/settings", json=raw)
    assert response.status_code == 422
    assert response.json()["error"].startswith("Keep-awake: Interval")


def test_devices_and_folder_pick(client: TestClient) -> None:
    assert client.get("/api/devices").json() == {
        "microphones": ["Desk Mic"],
        "system_audio": ["Desk Speakers"],
        "screens": ["Screen 1: 1920×1080 at 0, 0"],
    }
    picked = client.post("/api/pick-folder", json={"start": "D:\\videos"}, headers={"Origin": BASE})
    assert picked.json() == {"folder": "D:\\videos\\picked"}


def test_restart_is_offered_with_update(client: TestClient) -> None:
    body = client.get("/api/restart").json()
    assert [t["id"] for t in body["targets"]] == ["app"]
    assert body["update"] is True


def test_a_request_from_another_machine_is_refused(fake: FakeApp, tmp_path: Path) -> None:
    app = create_app(fake, git_sha="", built_at="", pid=1, restart_dir=tmp_path)
    remote = TestClient(app, base_url=BASE, client=("192.0.2.10", 50000))
    assert remote.get("/api/settings").status_code == 403


def test_a_page_on_another_host_name_is_refused(fake: FakeApp, tmp_path: Path) -> None:
    app = create_app(fake, git_sha="", built_at="", pid=1, restart_dir=tmp_path)
    rebound = TestClient(app, base_url="http://attacker.example:8467", client=LOOPBACK)
    assert rebound.get("/api/settings").status_code == 403


def test_a_write_from_another_site_is_refused(client: TestClient, fake: FakeApp) -> None:
    raw = settings_to_dict(Settings())
    response = client.put("/api/settings", json=raw, headers={"Origin": "http://other.example"})
    assert response.status_code == 403
    assert fake.applied == []


def test_a_stuck_app_answers_503(fake: FakeApp, tmp_path: Path) -> None:
    def stuck() -> Settings:
        raise TimeoutError("the app did not answer within 15 s")

    fake.settings = stuck
    app = create_app(fake, git_sha="", built_at="", pid=1, restart_dir=tmp_path)
    response = TestClient(app, base_url=BASE, client=LOOPBACK).get("/api/settings")
    assert response.status_code == 503
    assert "did not answer" in response.json()["error"]


def _read_version(port: int) -> dict:
    """The served version, retried while the server thread is still starting."""
    url = f"http://127.0.0.1:{port}{VERSION_PATH}"
    deadline = time.monotonic() + 5
    while True:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.loads(response.read())
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)


def test_server_serves_on_loopback_and_a_taken_port_is_reported(fake: FakeApp, tmp_path) -> None:
    app = create_app(fake, git_sha="deadbeef", built_at="x", pid=7, restart_dir=tmp_path)
    first = WebServer(app, port=0)
    assert first.start()
    try:
        assert _read_version(first.port)["git_sha"] == "deadbeef"
        assert WebServer(app, port=first.port).start() is False
    finally:
        first.stop()
