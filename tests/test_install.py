"""setup.bat on a copy of this app: its [install] table, config top-up and checklist probes."""

import json
import shutil
import subprocess
from pathlib import Path

from scripts import install_check
from src import installer

ROOT = Path(__file__).resolve().parent.parent


def _configured_copy(tmp_path: Path) -> Path:
    """A copy with a stand-in .venv and a config holding one own value and lacking two keys."""
    for name in (".fleet.toml", "config.sample.json", "requirements.txt"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    python = installer.venv_python(tmp_path)
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    cfg = json.loads((ROOT / "config.sample.json").read_text(encoding="utf-8"))
    cfg["fade"] = {"enabled": False}
    del cfg["recording"]
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path


def _succeeds(command, **_kwargs) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(command, 0)


def _files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_top_up_keeps_values_adds_missing_keys_after_a_backup(tmp_path: Path) -> None:
    root = _configured_copy(tmp_path)
    before = (root / "config.json").read_bytes()

    report = installer.run(root, what_if=False, runner=_succeeds)

    assert not report.failed
    cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
    sample = json.loads((root / "config.sample.json").read_text(encoding="utf-8"))
    assert cfg["fade"] == {"enabled": False, "delay_seconds": sample["fade"]["delay_seconds"]}
    assert cfg["recording"] == sample["recording"]
    (backup,) = root.glob("config.json.bak-*")
    assert backup.read_bytes() == before

    topped_up = _files(root)
    second = installer.run(root, what_if=False, runner=_succeeds)
    assert not second.changes
    assert _files(root) == topped_up


def test_what_if_writes_nothing(tmp_path: Path) -> None:
    root = _configured_copy(tmp_path)
    before = _files(root)

    report = installer.run(root, what_if=True, runner=_succeeds)

    assert ("would add", "config.json") in [line[:2] for line in report.lines]
    assert _files(root) == before


def test_ffmpeg_check_reads_the_config_without_creating_it(tmp_path: Path, monkeypatch) -> None:
    # find_ffmpeg binds shutil.which as a default argument, so that default is what to replace.
    monkeypatch.setattr(
        "overmark.recording.devices.find_ffmpeg.__defaults__", (lambda _name: None,)
    )
    config = tmp_path / "config.json"

    assert install_check.main(["ffmpeg"], tmp_path) == install_check.MISSING
    assert not config.exists()

    binary = tmp_path / "ffmpeg.exe"
    binary.write_bytes(b"")
    config.write_text(json.dumps({"recording": {"ffmpeg_path": str(binary)}}), encoding="utf-8")
    assert install_check.main(["ffmpeg"], tmp_path) == install_check.OK

    config.write_text("{", encoding="utf-8")
    assert install_check.main(["ffmpeg"], tmp_path) == install_check.UNKNOWN


def test_restart_helper_check_has_three_states(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert install_check.main(["restart-helper"]) == install_check.MISSING

    helper = tmp_path / ".claude" / "tray" / "tray_lifecycle.ps1"
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"")
    assert install_check.main(["restart-helper"]) == install_check.OK

    monkeypatch.delenv("USERPROFILE")
    assert install_check.main(["restart-helper"]) == install_check.UNKNOWN
